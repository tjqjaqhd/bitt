#!/usr/bin/env python3
"""SQLite 데이터베이스 백업 스크립트."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from src.data import backup_database


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SQLite 데이터베이스 백업")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=7,
        help="백업 파일 보관 일수(기본값: 7)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    backup_path = backup_database(retention_days=args.retention_days, now=datetime.now(timezone.utc))
    print(f"백업 생성: {backup_path}")


if __name__ == "__main__":
    main()

