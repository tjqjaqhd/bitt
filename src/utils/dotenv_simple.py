"""간단한 dotenv 대체 모듈."""

import os
from pathlib import Path
from typing import Optional


def load_dotenv(dotenv_path: Optional[Path] = None) -> bool:
    """
    .env 파일에서 환경변수를 읽어서 os.environ에 설정한다.

    Args:
        dotenv_path: .env 파일 경로. None이면 현재 디렉토리의 .env 파일 사용

    Returns:
        성공적으로 로드했으면 True, 그렇지 않으면 False
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