"""설정 API 라우터."""

from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...core.parameters import StrategyParameters, StrategyParameterStore
from ...utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

class StrategyConfig(BaseModel):
    """전략 설정."""
    ema_short_period: int = 20
    ema_long_period: int = 60
    rsi_period: int = 14
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    atr_period: int = 14
    position_size_percent: float = 5.0
    max_positions: int = 5
    stop_loss_percent: float = 3.0

class RiskConfig(BaseModel):
    """리스크 설정."""
    max_daily_loss_percent: float = 5.0
    max_position_size_percent: float = 10.0
    max_open_positions: int = 5
    stop_loss_percent: float = 3.0
    take_profit_percent: float = 10.0
    trailing_stop_percent: float = 2.0

class NotificationConfig(BaseModel):
    """알림 설정."""
    email_enabled: bool = True
    email_address: str = ""
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    slack_enabled: bool = False
    slack_webhook_url: str = ""

@router.get("/strategy")
async def get_strategy_config():
    """전략 설정 조회."""
    try:
        # 실제로는 DB나 설정 파일에서 로드
        return StrategyConfig(
            ema_short_period=20,
            ema_long_period=60,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            atr_period=14,
            position_size_percent=5.0,
            max_positions=5,
            stop_loss_percent=3.0
        )

    except Exception as e:
        logger.error(f"전략 설정 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/strategy")
async def update_strategy_config(config: StrategyConfig):
    """전략 설정 업데이트."""
    try:
        # 설정 유효성 검증
        if config.ema_short_period >= config.ema_long_period:
            raise HTTPException(
                status_code=400,
                detail="단기 EMA 기간은 장기 EMA 기간보다 작아야 합니다"
            )

        if not (1 <= config.rsi_period <= 50):
            raise HTTPException(
                status_code=400,
                detail="RSI 기간은 1-50 사이여야 합니다"
            )

        if not (0.1 <= config.position_size_percent <= 20.0):
            raise HTTPException(
                status_code=400,
                detail="포지션 크기는 0.1%-20% 사이여야 합니다"
            )

        # 실제로는 DB나 설정 파일에 저장
        logger.info(f"전략 설정 업데이트: {config}")

        return {"message": "전략 설정이 업데이트되었습니다", "config": config}

    except Exception as e:
        logger.error(f"전략 설정 업데이트 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/risk")
async def get_risk_config():
    """리스크 설정 조회."""
    try:
        return RiskConfig(
            max_daily_loss_percent=5.0,
            max_position_size_percent=10.0,
            max_open_positions=5,
            stop_loss_percent=3.0,
            take_profit_percent=10.0,
            trailing_stop_percent=2.0
        )

    except Exception as e:
        logger.error(f"리스크 설정 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/risk")
async def update_risk_config(config: RiskConfig):
    """리스크 설정 업데이트."""
    try:
        # 설정 유효성 검증
        if not (1.0 <= config.max_daily_loss_percent <= 20.0):
            raise HTTPException(
                status_code=400,
                detail="일일 최대 손실은 1%-20% 사이여야 합니다"
            )

        if not (1 <= config.max_open_positions <= 20):
            raise HTTPException(
                status_code=400,
                detail="최대 보유 포지션은 1-20개 사이여야 합니다"
            )

        logger.info(f"리스크 설정 업데이트: {config}")

        return {"message": "리스크 설정이 업데이트되었습니다", "config": config}

    except Exception as e:
        logger.error(f"리스크 설정 업데이트 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/notifications")
async def get_notification_config():
    """알림 설정 조회."""
    try:
        return NotificationConfig(
            email_enabled=True,
            email_address="user@example.com",
            telegram_enabled=False,
            telegram_bot_token="",
            telegram_chat_id="",
            slack_enabled=False,
            slack_webhook_url=""
        )

    except Exception as e:
        logger.error(f"알림 설정 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/notifications")
async def update_notification_config(config: NotificationConfig):
    """알림 설정 업데이트."""
    try:
        # 이메일 설정 검증
        if config.email_enabled and not config.email_address:
            raise HTTPException(
                status_code=400,
                detail="이메일 알림을 활성화하려면 이메일 주소가 필요합니다"
            )

        # 텔레그램 설정 검증
        if config.telegram_enabled and (not config.telegram_bot_token or not config.telegram_chat_id):
            raise HTTPException(
                status_code=400,
                detail="텔레그램 알림을 활성화하려면 봇 토큰과 채팅 ID가 필요합니다"
            )

        # Slack 설정 검증
        if config.slack_enabled and not config.slack_webhook_url:
            raise HTTPException(
                status_code=400,
                detail="Slack 알림을 활성화하려면 웹훅 URL이 필요합니다"
            )

        logger.info(f"알림 설정 업데이트: {config}")

        return {"message": "알림 설정이 업데이트되었습니다", "config": config}

    except Exception as e:
        logger.error(f"알림 설정 업데이트 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/system/restart")
async def restart_system():
    """시스템 재시작."""
    try:
        logger.info("시스템 재시작 요청")

        # 실제로는 시스템 재시작 로직 구현
        return {"message": "시스템 재시작이 예약되었습니다"}

    except Exception as e:
        logger.error(f"시스템 재시작 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/system/stop")
async def stop_system():
    """시스템 정지."""
    try:
        logger.info("시스템 정지 요청")

        # 실제로는 시스템 정지 로직 구현
        return {"message": "시스템이 안전하게 정지됩니다"}

    except Exception as e:
        logger.error(f"시스템 정지 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))