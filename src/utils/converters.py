"""데이터 변환 관련 헬퍼 함수."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Union

NumberLike = Union[str, int, float, Decimal]


def to_decimal(value: NumberLike, quantize: Optional[str] = None) -> Decimal:
    """숫자형 또는 문자열 값을 Decimal로 변환한다."""
    if isinstance(value, Decimal):
        decimal_value = value
    else:
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"Decimal 변환 실패: {value}") from exc
    if quantize is not None:
        decimal_value = decimal_value.quantize(Decimal(quantize), rounding=ROUND_HALF_UP)
    return decimal_value


def decimal_to_float(value: NumberLike, precision: Optional[int] = None) -> float:
    """Decimal 혹은 숫자 값을 float으로 변환한다."""
    decimal_value = to_decimal(value)
    if precision is not None:
        quantizer = Decimal(10) ** (-precision)
        decimal_value = decimal_value.quantize(quantizer, rounding=ROUND_HALF_UP)
    return float(decimal_value)


def format_decimal(value: NumberLike, precision: int = 2) -> str:
    """지정된 소수점 자리수로 문자열을 생성한다."""
    quantizer = Decimal(10) ** (-precision)
    decimal_value = to_decimal(value).quantize(quantizer, rounding=ROUND_HALF_UP)
    return f"{decimal_value:f}"


def str_to_bool(value: Union[str, bool, int, None], default: bool = False) -> bool:
    """문자열 혹은 기타 값을 불리언으로 해석한다."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, int):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


__all__ = [
    "NumberLike",
    "decimal_to_float",
    "format_decimal",
    "str_to_bool",
    "to_decimal",
]
