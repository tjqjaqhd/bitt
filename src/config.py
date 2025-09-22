"""환경변수 기반 애플리케이션 설정 로더."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"
load_dotenv(ENV_FILE)


def _to_bool(value: str | bool | None, default: bool = False) -> bool:
    """문자열 값을 불리언으로 변환한다."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _to_int(value: str | int | None, default: int) -> int:
    """문자열 값을 정수로 변환한다."""
    if isinstance(value, int):
        return value
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class DatabaseSettings(BaseModel):
    """데이터베이스 연결 설정."""

    model_config = ConfigDict(populate_by_name=True)

    url: str = Field(default="sqlite:///data/app.db")
    echo: bool = Field(default=False)
    pool_size: int = Field(default=5, ge=1)

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        """환경변수에서 데이터베이스 설정을 생성한다."""
        return cls(
            url=os.getenv("DATABASE_URL", "sqlite:///data/app.db"),
            echo=_to_bool(os.getenv("DATABASE_ECHO"), False),
            pool_size=_to_int(os.getenv("DATABASE_POOL_SIZE"), 5),
        )


class LoggingSettings(BaseModel):
    """로깅 관련 설정."""

    model_config = ConfigDict(populate_by_name=True)

    level: str = Field(default="INFO")
    log_dir: Path = Field(default=Path("logs"))
    file_name: str = Field(default="app.log")
    rotation_when: str = Field(default="midnight")
    rotation_interval: int = Field(default=1, ge=1)
    backup_count: int = Field(default=7, ge=0)

    @classmethod
    def from_env(cls) -> "LoggingSettings":
        """환경변수에서 로깅 설정을 생성한다."""
        log_dir_value = os.getenv("LOG_DIR", "logs")
        return cls(
            level=os.getenv("LOG_LEVEL", "INFO"),
            log_dir=Path(log_dir_value).expanduser(),
            file_name=os.getenv("LOG_FILE_NAME", "app.log"),
            rotation_when=os.getenv("LOG_ROTATION_WHEN", "midnight"),
            rotation_interval=_to_int(os.getenv("LOG_ROTATION_INTERVAL"), 1),
            backup_count=_to_int(os.getenv("LOG_BACKUP_COUNT"), 7),
        )

    @property
    def normalized_level(self) -> str:
        """대문자로 정규화된 로그 레벨."""
        return self.level.upper()

    def resolve_log_dir(self, root_dir: Path) -> Path:
        """루트 경로 기준 로그 디렉터리를 반환한다."""
        if self.log_dir.is_absolute():
            return self.log_dir
        return (root_dir / self.log_dir).resolve()

    def resolve_log_path(self, root_dir: Path) -> Path:
        """루트 경로 기준 로그 파일 전체 경로."""
        return self.resolve_log_dir(root_dir) / self.file_name


class BithumbSettings(BaseModel):
    """빗썸 API 관련 설정."""

    model_config = ConfigDict(populate_by_name=True)

    api_key: Optional[SecretStr] = Field(default=None)
    api_secret: Optional[SecretStr] = Field(default=None)
    rest_base_url: str = Field(default="https://api.bithumb.com")
    websocket_public_url: str = Field(default="wss://pubwss.bithumb.com/pub/ws")

    @classmethod
    def from_env(cls) -> "BithumbSettings":
        """환경변수에서 빗썸 API 설정을 생성한다."""
        api_key = os.getenv("BITHUMB_API_KEY")
        api_secret = os.getenv("BITHUMB_API_SECRET")
        return cls(
            api_key=SecretStr(api_key) if api_key else None,
            api_secret=SecretStr(api_secret) if api_secret else None,
            rest_base_url=os.getenv("BITHUMB_REST_BASE_URL", "https://api.bithumb.com"),
            websocket_public_url=os.getenv(
                "BITHUMB_WEBSOCKET_PUBLIC_URL", "wss://pubwss.bithumb.com/pub/ws"
            ),
        )


class AppSettings(BaseModel):
    """애플리케이션 전반에 사용되는 설정 묶음."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    root_dir: Path = Field(default=ROOT_DIR)
    environment: str = Field(default="development")
    timezone: str = Field(default="Asia/Seoul")
    data_dir: Path = Field(default=ROOT_DIR / "data")
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    bithumb: BithumbSettings = Field(default_factory=BithumbSettings)

    @classmethod
    def load(cls) -> "AppSettings":
        """환경변수 및 기본값을 반영하여 설정 인스턴스를 생성한다."""
        data_dir_value = os.getenv("DATA_DIR")
        data_dir = Path(data_dir_value).expanduser() if data_dir_value else ROOT_DIR / "data"
        return cls(
            root_dir=ROOT_DIR,
            environment=os.getenv("APP_ENV", "development"),
            timezone=os.getenv("APP_TIMEZONE", "Asia/Seoul"),
            data_dir=data_dir,
            database=DatabaseSettings.from_env(),
            logging=LoggingSettings.from_env(),
            bithumb=BithumbSettings.from_env(),
        )

    def resolve_path(self, path: str | Path) -> Path:
        """루트 디렉터리를 기준으로 경로를 절대경로로 변환한다."""
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate
        return (self.root_dir / candidate).resolve()

    def ensure_data_dir(self) -> Path:
        """데이터 디렉터리를 생성하고 경로를 반환한다."""
        resolved = self.resolve_path(self.data_dir)
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """애플리케이션 전역 설정을 캐시하여 반환한다."""
    settings = AppSettings.load()
    settings.ensure_data_dir()
    return settings


__all__ = [
    "AppSettings",
    "BithumbSettings",
    "DatabaseSettings",
    "LoggingSettings",
    "get_settings",
]
