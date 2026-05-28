from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from .config import ensure_directories, settings
from .schemas import Course


ensure_directories()

_JSON_CACHE: dict[Path, tuple[float, Any]] = {}
_COURSE_CACHE: dict[str, tuple[float, Course]] = {}
_COURSE_LIST_CACHE: tuple[tuple[tuple[str, float], ...], list[Course]] | None = None


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else -1.0


def clear_storage_cache() -> None:
    global _COURSE_LIST_CACHE
    _JSON_CACHE.clear()
    _COURSE_CACHE.clear()
    _COURSE_LIST_CACHE = None


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    resolved = path.resolve()
    mtime = _mtime(resolved)
    cached = _JSON_CACHE.get(resolved)
    if cached and cached[0] == mtime:
        return cached[1]
    data = json.loads(resolved.read_text(encoding="utf-8"))
    _JSON_CACHE[resolved] = (mtime, data)
    return data


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    resolved = path.resolve()
    _JSON_CACHE[resolved] = (_mtime(resolved), data)
    try:
        resolved.relative_to(settings.courses_dir.resolve())
        _COURSE_CACHE.pop(path.stem, None)
        global _COURSE_LIST_CACHE
        _COURSE_LIST_CACHE = None
    except ValueError:
        pass
    return path


def course_path(course_id: str) -> Path:
    return settings.courses_dir / f"{course_id}.json"


def load_course(course_id: str) -> Course:
    path = course_path(course_id)
    mtime = _mtime(path)
    cached = _COURSE_CACHE.get(course_id)
    if cached and cached[0] == mtime:
        return cached[1].model_copy(deep=True)
    data = read_json(path)
    if data is None:
        raise FileNotFoundError(f"Course not found: {course_id}")
    course = Course.model_validate(data)
    _COURSE_CACHE[course_id] = (mtime, course)
    return course.model_copy(deep=True)


def save_course(course: Course) -> Path:
    return write_json(course_path(course.course_id), course.model_dump(mode="json"))


def list_courses() -> list[Course]:
    global _COURSE_LIST_CACHE
    signature = tuple((path.name, _mtime(path)) for path in sorted(settings.courses_dir.glob("*.json")))
    if _COURSE_LIST_CACHE and _COURSE_LIST_CACHE[0] == signature:
        return [course.model_copy(deep=True) for course in _COURSE_LIST_CACHE[1]]
    courses = []
    for path in sorted(settings.courses_dir.glob("*.json")):
        course_id = path.stem
        cached = _COURSE_CACHE.get(course_id)
        mtime = _mtime(path)
        if cached and cached[0] == mtime:
            course = cached[1]
        else:
            course = Course.model_validate(read_json(path))
            _COURSE_CACHE[course_id] = (mtime, course)
        courses.append(course)
    _COURSE_LIST_CACHE = (signature, courses)
    return [course.model_copy(deep=True) for course in courses]


def static_url(path: str | Path | None) -> str | None:
    if not path:
        return None
    path = Path(path)
    try:
        rel = path.resolve().relative_to(settings.static_dir.resolve())
        return f"/static/{rel.as_posix()}"
    except Exception:
        return str(path)


def generated_url(kind: str, filename: str) -> str:
    return f"/api/generated/{kind}/{filename}"


def save_upload(filename: str, source_path: Path) -> Path:
    target = settings.uploads_dir / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target)
    return target


def save_eval_log(feature_name: str, payload: dict[str, Any]) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = settings.generated_dir / "evals" / f"{stamp}_{feature_name}.json"
    return write_json(path, payload)
