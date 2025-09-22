"""SQLAlchemy 데이터베이스 초기화 및 세션 헬퍼."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool

from ..config import AppSettings, get_settings


class Base(DeclarativeBase):
    """모든 ORM 모델이 상속하는 기본 베이스 클래스."""


def _resolve_sqlite_path(url: URL, settings: AppSettings) -> URL:
    """SQLite 경로를 절대 경로로 변환하고 상위 디렉터리를 생성한다."""

    if url.database and url.database != ":memory:":
        database_path = Path(url.database)
        if not database_path.is_absolute():
            database_path = settings.root_dir / database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        url = url.set(database=str(database_path))
    return url


def resolve_database_url(raw_url: Optional[str] = None) -> URL:
    """환경 설정을 반영한 SQLAlchemy URL 객체를 생성한다."""

    settings = get_settings()
    configured_url = raw_url or settings.database.url
    url = make_url(configured_url)
    if url.get_backend_name() == "sqlite":
        url = _resolve_sqlite_path(url, settings)
    return url


def create_db_engine(
    *,
    url: Optional[str] = None,
    echo: Optional[bool] = None,
    pool_size: Optional[int] = None,
) -> Engine:
    """설정 값 기반으로 SQLAlchemy 엔진을 생성한다."""

    settings = get_settings()
    resolved_url = resolve_database_url(url)
    db_settings = settings.database
    effective_echo = db_settings.echo if echo is None else echo
    effective_pool_size = db_settings.pool_size if pool_size is None else pool_size

    engine_kwargs: dict[str, object] = {
        "echo": effective_echo,
        "future": True,
        "pool_pre_ping": True,
    }

    if resolved_url.get_backend_name() == "sqlite":
        engine_kwargs.update(
            {
                "connect_args": {"check_same_thread": False},
                "poolclass": QueuePool,
                "pool_size": effective_pool_size,
            }
        )
    else:
        engine_kwargs.update({"poolclass": QueuePool, "pool_size": effective_pool_size})

    return create_engine(resolved_url, **engine_kwargs)


ENGINE: Engine = create_db_engine()

SessionLocal = sessionmaker(
    bind=ENGINE,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


@contextmanager
def session_scope() -> Iterator[Session]:
    """트랜잭션 범위를 관리하는 컨텍스트 매니저."""

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_session() -> Iterator[Session]:
    """세션 생명주기를 관리하는 컨텍스트 매니저."""

    with session_scope() as session:
        yield session


__all__ = [
    "Base",
    "ENGINE",
    "SessionLocal",
    "create_db_engine",
    "get_session",
    "resolve_database_url",
    "session_scope",
]

