"""Central, environment-configured image storage with safe relative paths."""

from pathlib import Path, PurePosixPath
import re

from fastapi import HTTPException

from .database import settings


ALLOWED_IMAGE_SUFFIXES = {'.gif', '.jpeg', '.jpg', '.png', '.svg', '.webp'}
SAFE_SEGMENT = re.compile(r'^[A-Za-z0-9._-]+$')


def data_root() -> Path:
    return Path(settings.brewbill_data_path).expanduser().resolve()


def normalise_media_path(value: str) -> str:
    candidate = value.strip().replace('\\', '/')
    pure = PurePosixPath(candidate)
    if (
        not candidate
        or pure.is_absolute()
        or any(part in {'', '.', '..'} or not SAFE_SEGMENT.fullmatch(part) for part in pure.parts)
        or pure.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES
    ):
        raise HTTPException(404, 'Image not found.')
    return pure.as_posix()


def media_file_path(relative_path: str) -> Path:
    normalised = normalise_media_path(relative_path)
    root = data_root()
    target = (root / Path(*PurePosixPath(normalised).parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(404, 'Image not found.') from exc
    return target


def relative_media_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(data_root()).as_posix()
    except ValueError as exc:
        raise RuntimeError('Media file must be stored under BREWBILL_DATA_PATH.') from exc
