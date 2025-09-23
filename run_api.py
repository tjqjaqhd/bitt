#!/usr/bin/env python3
"""API 서버 실행 스크립트."""

import uvicorn
import sys
from pathlib import Path

# 프로젝트 루트를 파이썬 경로에 추가
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )