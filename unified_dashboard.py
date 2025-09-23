#!/usr/bin/env python3
"""
통합 대시보드 서버 - 실제 데이터 연동
FastAPI + 빗썸 API 2.0 + 실시간 WebSocket
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

# 프로젝트 루트를 Python 경로에 추가
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# 환경변수 로드
from src.utils.dotenv_simple import load_dotenv
env_file = PROJECT_ROOT / '.env'
load_dotenv(env_file)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import logging

# 프로젝트 모듈 import
from src.config import get_settings
from src.exchange.bithumb_client import BithumbClient
from src.data.database import get_session
from src.utils.logger import setup_logging


class UnifiedDashboard:
    """통합 대시보드"""

    def __init__(self):
        self.app = FastAPI(title="빗썸 자동매매 대시보드", version="2.0")
        self.settings = get_settings()
        self.logger = setup_logging()
        self.bithumb = BithumbClient()

        # WebSocket 연결 관리
        self.websocket_connections: List[WebSocket] = []

        # CORS 설정
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        self.setup_routes()

    def setup_routes(self):
        """라우트 설정"""

        @self.app.get("/")
        async def serve_dashboard():
            """대시보드 페이지 제공"""
            dashboard_file = PROJECT_ROOT / "dashboard.html"
            if dashboard_file.exists():
                return FileResponse(str(dashboard_file))
            else:
                return {"message": "Dashboard HTML not found"}

        @self.app.get("/api/dashboard/summary")
        async def get_dashboard_summary():
            """대시보드 요약 정보"""
            try:
                # 실제 계좌 정보 조회
                balance_data = await self.get_real_balance()
                market_data = await self.get_market_overview()

                return {
                    "totalKrw": balance_data.get("total_krw", 0),
                    "totalCrypto": balance_data.get("total_crypto_krw", 0),
                    "totalAssets": balance_data.get("total_assets", 0),
                    "todayPnl": balance_data.get("today_pnl", 0),
                    "todayPnlPercent": balance_data.get("today_pnl_percent", 0),
                    "activePositions": len(balance_data.get("positions", [])),
                    "marketData": market_data,
                    "lastUpdated": datetime.now().isoformat()
                }
            except Exception as e:
                self.logger.error(f"대시보드 요약 정보 조회 실패: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/dashboard/positions")
        async def get_positions():
            """현재 포지션 정보"""
            try:
                balance_data = await self.get_real_balance()
                positions = []

                for coin, info in balance_data.get("balances", {}).items():
                    if coin != "KRW" and float(info.get("available", 0)) > 0:
                        # 현재 시세 조회
                        ticker = await self.get_ticker_data(coin)
                        current_price = float(ticker.get("closing_price", 0)) if ticker else 0

                        quantity = float(info.get("available", 0))
                        value_krw = quantity * current_price

                        positions.append({
                            "symbol": coin,
                            "quantity": quantity,
                            "averagePrice": 0,  # 평균매입가는 별도 계산 필요
                            "currentPrice": current_price,
                            "valueKrw": value_krw,
                            "pnl": 0,  # 손익은 별도 계산 필요
                            "pnlPercent": 0
                        })

                return {"positions": positions}
            except Exception as e:
                self.logger.error(f"포지션 정보 조회 실패: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/dashboard/recent-trades")
        async def get_recent_trades():
            """최근 거래 내역"""
            try:
                # 여러 주요 코인의 거래 내역 조회
                all_trades = []
                symbols = ["BTC", "ETH", "XRP", "ADA", "DOT"]

                for symbol in symbols[:3]:  # API 호출 제한으로 3개만
                    try:
                        trades = self.bithumb.get_user_transactions(
                            order_currency=symbol,
                            count=10
                        )

                        if trades and trades.get("status") == "0000":
                            for trade in trades.get("data", []):
                                all_trades.append({
                                    "symbol": symbol,
                                    "side": "buy" if trade.get("type") == "bid" else "sell",
                                    "quantity": float(trade.get("units", 0)),
                                    "price": float(trade.get("price", 0)),
                                    "total": float(trade.get("total", 0)),
                                    "timestamp": trade.get("transfer_date", ""),
                                    "status": "completed"
                                })
                    except Exception as e:
                        self.logger.warning(f"{symbol} 거래내역 조회 실패: {e}")

                # 시간순 정렬
                all_trades.sort(key=lambda x: x["timestamp"], reverse=True)

                return {"trades": all_trades[:20]}
            except Exception as e:
                self.logger.error(f"거래 내역 조회 실패: {e}")
                return {"trades": []}

        @self.app.get("/api/dashboard/performance")
        async def get_performance():
            """성과 분석"""
            try:
                # 성과 데이터는 DB에서 조회하거나 계산
                return {
                    "totalReturn": 0,
                    "totalReturnPercent": 0,
                    "maxDrawdown": 0,
                    "winRate": 0,
                    "profitFactor": 0,
                    "avgHoldingPeriod": 0,
                    "totalTrades": 0,
                    "winningTrades": 0,
                    "losingTrades": 0,
                    "dailyReturns": []
                }
            except Exception as e:
                self.logger.error(f"성과 분석 조회 실패: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket 실시간 데이터"""
            await websocket.accept()
            self.websocket_connections.append(websocket)

            try:
                while True:
                    # 실시간 데이터 전송
                    data = await self.get_realtime_data()
                    await websocket.send_text(json.dumps(data))
                    await asyncio.sleep(5)  # 5초마다 업데이트

            except WebSocketDisconnect:
                self.websocket_connections.remove(websocket)
            except Exception as e:
                self.logger.error(f"WebSocket 오류: {e}")
                if websocket in self.websocket_connections:
                    self.websocket_connections.remove(websocket)

    async def get_real_balance(self) -> Dict[str, Any]:
        """실제 계좌 잔고 조회"""
        try:
            # 빗썸 API 2.0 사용
            balance_data = self.bithumb.get_accounts()

            if balance_data and balance_data.get("status") == "0000":
                data = balance_data.get("data", {})

                # 데이터 가공
                balances = {}
                total_krw = 0
                total_crypto_krw = 0

                for currency, info in data.items():
                    if currency != "date":
                        available = float(info.get("available", 0))
                        in_use = float(info.get("in_use", 0))
                        total = available + in_use

                        balances[currency] = {
                            "available": available,
                            "in_use": in_use,
                            "total": total
                        }

                        if currency == "KRW":
                            total_krw = total
                        elif total > 0:
                            # 암호화폐 가치를 KRW로 환산
                            ticker = await self.get_ticker_data(currency)
                            if ticker:
                                price = float(ticker.get("closing_price", 0))
                                total_crypto_krw += total * price

                return {
                    "balances": balances,
                    "total_krw": total_krw,
                    "total_crypto_krw": total_crypto_krw,
                    "total_assets": total_krw + total_crypto_krw,
                    "today_pnl": 0,  # 별도 계산 필요
                    "today_pnl_percent": 0,
                    "positions": [k for k, v in balances.items() if k != "KRW" and v["total"] > 0]
                }
            else:
                self.logger.error(f"잔고 조회 실패: {balance_data}")
                return {}

        except Exception as e:
            self.logger.error(f"실제 잔고 조회 중 오류: {e}")
            return {}

    async def get_ticker_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """시세 데이터 조회"""
        try:
            ticker_data = self.bithumb.get_ticker(symbol)

            if ticker_data and ticker_data.get("status") == "0000":
                return ticker_data.get("data")
            return None

        except Exception as e:
            self.logger.error(f"{symbol} 시세 조회 중 오류: {e}")
            return None

    async def get_market_overview(self) -> Dict[str, Any]:
        """시장 개요"""
        try:
            # 주요 코인 시세 조회
            symbols = ["BTC", "ETH", "XRP", "ADA", "DOT"]
            market_data = {}

            for symbol in symbols:
                ticker = await self.get_ticker_data(symbol)
                if ticker:
                    market_data[symbol] = {
                        "price": float(ticker.get("closing_price", 0)),
                        "change": float(ticker.get("fluctate_rate_24H", 0)),
                        "volume": float(ticker.get("acc_trade_value_24H", 0))
                    }

            return market_data

        except Exception as e:
            self.logger.error(f"시장 개요 조회 실패: {e}")
            return {}

    async def get_realtime_data(self) -> Dict[str, Any]:
        """실시간 데이터"""
        try:
            balance_data = await self.get_real_balance()
            market_data = await self.get_market_overview()

            return {
                "type": "realtime_update",
                "timestamp": datetime.now().isoformat(),
                "balance": balance_data,
                "market": market_data
            }

        except Exception as e:
            self.logger.error(f"실시간 데이터 조회 실패: {e}")
            return {"type": "error", "message": str(e)}

    async def broadcast_to_websockets(self, data: Dict[str, Any]):
        """WebSocket 브로드캐스트"""
        if self.websocket_connections:
            message = json.dumps(data)
            for websocket in self.websocket_connections.copy():
                try:
                    await websocket.send_text(message)
                except Exception as e:
                    self.logger.error(f"WebSocket 전송 실패: {e}")
                    self.websocket_connections.remove(websocket)

    def run(self, host: str = "0.0.0.0", port: int = 8000):
        """대시보드 서버 실행"""
        self.logger.info(f"🚀 통합 대시보드 서버 시작: http://{host}:{port}")
        uvicorn.run(self.app, host=host, port=port, log_level="info")


def main():
    """메인 함수"""
    dashboard = UnifiedDashboard()
    dashboard.run()


if __name__ == "__main__":
    main()