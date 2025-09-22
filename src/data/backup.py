"""SQLite 데이터베이스 백업 헬퍼."""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ..config import get_settings
from .database import resolve_database_url


def _resolve_sqlite_file() -> Path:
    url = resolve_database_url()
    if url.get_backend_name() != "sqlite" or not url.database:
        raise RuntimeError("현재 백업 헬퍼는 SQLite 데이터베이스만 지원합니다.")
    return Path(url.database)


def backup_database(*, retention_days: int = 7, now: Optional[datetime] = None) -> Path:
    """데이터베이스 파일을 백업 디렉터리에 복제하고 보관 기간을 관리한다."""

    settings = get_settings()
    db_file = _resolve_sqlite_file()
    if not db_file.exists():
        raise FileNotFoundError(f"데이터베이스 파일을 찾을 수 없습니다: {db_file}")

    backup_dir = settings.ensure_data_dir() / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
    backup_path = backup_dir / f"app-{timestamp}.db"
    shutil.copy2(db_file, backup_path)

    if retention_days >= 0:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
        for file in backup_dir.glob("app-*.db"):
            try:
                created = datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if created < cutoff:
                file.unlink(missing_ok=True)

    return backup_path


__all__ = ["backup_database"]

