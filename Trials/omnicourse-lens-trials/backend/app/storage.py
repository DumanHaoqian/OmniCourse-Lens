from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

from .config import ensure_directories, settings
from .schemas import Course


ensure_directories()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def course_path(course_id: str) -> Path:
    return settings.courses_dir / f"{course_id}.json"


def load_course(course_id: str) -> Course:
    data = read_json(course_path(course_id))
    if data is None:
        raise FileNotFoundError(f"Course not found: {course_id}")
    return Course.model_validate(data)


def save_course(course: Course) -> Path:
    return write_json(course_path(course.course_id), course.model_dump(mode="json"))


def list_courses() -> list[Course]:
    courses = []
    for path in sorted(settings.courses_dir.glob("*.json")):
        courses.append(Course.model_validate(read_json(path)))
    return courses


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
