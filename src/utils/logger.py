"""프로젝트 전역에서 사용하는 로깅 설정 유틸리티."""

from __future__ import annotations

import logging
from logging import Logger
from logging.config import dictConfig
from pathlib import Path
from typing import Any, Dict

from ..config import get_settings

_LOG_CONFIGURED = False


def _ensure_directory(path: Path) -> None:
    """필요한 디렉터리를 생성한다."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _build_logging_config() -> Dict[str, Any]:
    """dictConfig에 사용할 로깅 설정을 생성한다."""
    settings = get_settings()
    logging_settings = settings.logging
    log_path = logging_settings.resolve_log_path(settings.root_dir)
    _ensure_directory(log_path)

    formatter = {
        "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        "datefmt": "%Y-%m-%d %H:%M:%S",
    }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"standard": formatter},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": logging_settings.normalized_level,
            },
            "file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "formatter": "standard",
                "level": logging_settings.normalized_level,
                "filename": str(log_path),
                "when": logging_settings.rotation_when,
                "interval": logging_settings.rotation_interval,
                "backupCount": logging_settings.backup_count,
                "encoding": "utf-8",
            },
        },
        "root": {
            "level": logging_settings.normalized_level,
            "handlers": ["console", "file"],
        },
    }


def configure_logging(force: bool = False) -> None:
    """로깅 설정을 초기화한다."""
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED and not force:
        return
    dictConfig(_build_logging_config())
    _LOG_CONFIGURED = True


def get_logger(name: str) -> Logger:
    """지정된 이름의 로거를 반환한다."""
    configure_logging()
    return logging.getLogger(name)


def setup_logging() -> Logger:
    """로깅을 설정하고 기본 로거를 반환한다."""
    configure_logging()
    return logging.getLogger(__name__)


__all__ = ["configure_logging", "get_logger", "setup_logging"]
