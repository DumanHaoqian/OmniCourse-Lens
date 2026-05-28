from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parents[1]


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    repo_root: Path = REPO_ROOT
    data_dir: Path = PROJECT_ROOT / "backend" / "app" / "data"
    static_dir: Path = PROJECT_ROOT / "backend" / "app" / "static"
    courses_dir: Path = PROJECT_ROOT / "backend" / "app" / "data" / "courses"
    indexes_dir: Path = PROJECT_ROOT / "backend" / "app" / "data" / "indexes"
    uploads_dir: Path = PROJECT_ROOT / "backend" / "app" / "data" / "uploads"
    generated_dir: Path = PROJECT_ROOT / "backend" / "app" / "data" / "generated"
    audio_dir: Path = PROJECT_ROOT / "backend" / "app" / "data" / "audio"
    frames_dir: Path = PROJECT_ROOT / "backend" / "app" / "static" / "frames"
    clips_dir: Path = PROJECT_ROOT / "backend" / "app" / "static" / "clips"
    credential_file: Path = REPO_ROOT / "openai_keys.txt"
    legacy_internvideo3_path: Path = REPO_ROOT / "Trials" / "checkpoints" / "InternVideo3-8B-Instruct"

    @property
    def demo_mode(self) -> bool:
        return os.getenv("OMNICOURSE_DEMO_MODE", "true").lower() not in {"0", "false", "no"}


settings = Settings()


def ensure_directories() -> None:
    for path in [
        settings.data_dir,
        settings.static_dir,
        settings.courses_dir,
        settings.indexes_dir,
        settings.uploads_dir,
        settings.generated_dir / "cheatsheets",
        settings.generated_dir / "graphs",
        settings.generated_dir / "qa",
        settings.generated_dir / "evals",
        settings.audio_dir,
        settings.frames_dir,
        settings.clips_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
