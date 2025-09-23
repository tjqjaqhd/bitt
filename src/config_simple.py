"""간단한 환경변수 기반 설정 로더."""

import os
from pathlib import Path
from typing import Optional

# 간단한 dotenv 기능
def load_dotenv_simple(dotenv_path: Optional[Path] = None) -> bool:
    """
    .env 파일에서 환경변수를 읽어서 os.environ에 설정한다.
    """
    if dotenv_path is None:
        dotenv_path = Path(".env")
    elif isinstance(dotenv_path, str):
        dotenv_path = Path(dotenv_path)

    if not dotenv_path.exists():
        return False

    try:
        with open(dotenv_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # 빈 줄이나 주석 제외
                if not line or line.startswith('#'):
                    continue

                # = 기호로 분할
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()

                    # 따옴표 제거
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]

                    # 이미 환경변수에 설정되어 있지 않은 경우에만 설정
                    if key not in os.environ:
                        os.environ[key] = value

        return True

    except Exception:
        return False


ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"
load_dotenv_simple(ENV_FILE)


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


class AppSettings:
    """간단한 애플리케이션 설정 클래스."""

    def __init__(self):
        self.root_dir = ROOT_DIR
        self.environment = os.getenv("APP_ENV", "development")
        self.timezone = os.getenv("APP_TIMEZONE", "Asia/Seoul")

        # 데이터베이스 설정
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///data/app.db")
        self.database_echo = _to_bool(os.getenv("DATABASE_ECHO"), False)

        # 로깅 설정
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        self.log_dir = Path(os.getenv("LOG_DIR", "logs"))

        # 빗썸 API 설정
        self.bithumb_api_key = os.getenv("BITHUMB_API_KEY")
        self.bithumb_secret_key = os.getenv("BITHUMB_SECRET_KEY")
        self.bithumb_rest_base_url = os.getenv("BITHUMB_REST_BASE_URL", "https://api.bithumb.com")
        self.bithumb_websocket_public_url = os.getenv("BITHUMB_WEBSOCKET_PUBLIC_URL", "wss://pubwss.bithumb.com/pub/ws")

        # 데이터 디렉터리 설정
        data_dir_value = os.getenv("DATA_DIR")
        self.data_dir = Path(data_dir_value).expanduser() if data_dir_value else ROOT_DIR / "data"

        # 데이터 디렉터리 생성
        self.ensure_data_dir()

    def ensure_data_dir(self) -> Path:
        """데이터 디렉터리를 생성하고 경로를 반환한다."""
        resolved = self.resolve_path(self.data_dir)
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    def resolve_path(self, path: str | Path) -> Path:
        """루트 디렉터리를 기준으로 경로를 절대경로로 변환한다."""
        candidate = Path(path).expanduser()
        if candidate.is_absolute():
            return candidate
        return (self.root_dir / candidate).resolve()


# 전역 설정 인스턴스
_settings = None


def get_settings() -> AppSettings:
    """애플리케이션 전역 설정을 캐시하여 반환한다."""
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings