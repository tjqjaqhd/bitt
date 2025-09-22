"""FastAPI 메인 애플리케이션."""

import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routers import dashboard, settings, analysis
# from .routers import trading, markets  # 임시로 주석 처리
# from .websocket import websocket_manager  # 임시로 주석 처리
from ..utils.logger import get_logger

# 로깅 설정
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행될 로직."""
    logger.info("🚀 빗썸 자동매매 대시보드 API 서버 시작")
    try:
        yield
    finally:
        logger.info("🔽 빗썸 자동매매 대시보드 API 서버 종료")

# FastAPI 앱 생성
app = FastAPI(
    title="빗썸 자동매매 대시보드",
    description="실시간 암호화폐 자동매매 모니터링 및 제어 시스템",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],  # React 개발 서버
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["대시보드"])
# app.include_router(trading.router, prefix="/api/trading", tags=["거래"])  # 임시로 주석 처리
# app.include_router(markets.router, prefix="/api/markets", tags=["종목"])  # 임시로 주석 처리
app.include_router(settings.router, prefix="/api/settings", tags=["설정"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["분석"])

# WebSocket 연결 (임시로 주석 처리)
# app.mount("/ws", websocket_manager.app)

@app.get("/")
async def root():
    """기본 엔드포인트."""
    return {
        "message": "빗썸 자동매매 대시보드 API",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/api/health")
async def health_check():
    """헬스체크 엔드포인트."""
    try:
        # DB 연결 체크, API 연결 체크 등
        return {
            "status": "healthy",
            "timestamp": "2025-09-22T13:40:00Z",
            "services": {
                "database": "connected",
                "bithumb_api": "connected",
                "websocket": "running"
            }
        }
    except Exception as e:
        logger.error(f"헬스체크 실패: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """전역 예외 처리."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )