"""애플리케이션 공통 예외 계층."""

from __future__ import annotations


class AppError(Exception):
    """프로젝트 전반에서 사용하는 기본 예외 클래스."""


class ConfigurationError(AppError):
    """환경 설정이나 필수 값이 누락된 경우 발생."""


class DependencyError(AppError):
    """외부 시스템 또는 라이브러리 의존성 문제."""


class DataValidationError(AppError):
    """데이터 검증 실패를 표현."""


class ExchangeError(AppError):
    """거래소 API 호출 중 발생한 예외."""


class WebSocketError(ExchangeError):
    """WebSocket 통신 중 발생하는 예외."""


class RetryableError(AppError):
    """재시도가 가능한 일시적 오류."""


__all__ = [
    "AppError",
    "ConfigurationError",
    "DataValidationError",
    "DependencyError",
    "ExchangeError",
    "WebSocketError",
    "RetryableError",
]
