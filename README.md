# 빗썸 원화마켓 자동매매 시스템 (Phase 3)

## 프로젝트 개요
- **목표**: 빗썸(KRW) 마켓 전용 단일 전략 자동매매 시스템 구축
- **전략 개요**: EMA 크로스오버 + RSI 필터 + ATR 리스크 관리 조합
- **운영 환경**: 24/7 상시 구동 가능한 클라우드 PC 환경, 실거래 데이터만 사용
- **현재 단계**: Phase 3 – 전략 엔진, 리스크 관리, 신호 로깅 구축 완료

## 디렉터리 구조
```
├── src/
│   ├── core/          # 전략 및 리스크 관리 모듈 자리
│   ├── exchange/      # 빗썸 API 연동 래퍼
│   ├── data/          # 데이터베이스/ETL 관련 모듈
│   ├── backtest/      # 백테스트 엔진 및 리포트 구성 요소
│   ├── ui/            # 웹/데스크톱/TUI 등 인터페이스 모듈
│   ├── jobs/          # 스케줄러 및 주기적 작업
│   └── utils/         # 공통 유틸리티 (로깅, 예외, 시간 등)
├── configs/           # 환경 설정 및 전략 파라미터 파일 저장 위치
├── tests/             # 단위/통합 테스트 코드
├── scripts/           # 배포, 유지보수, 데이터 유틸 스크립트
├── docs/              # 설계/운영 문서
├── data/              # 런타임 생성 데이터 (Git 미추적)
├── logs/              # 로그 파일 (Git 미추적)
├── requirements.txt   # Phase 0 필수 패키지 목록
├── README.md          # 프로젝트 개요 및 가이드 (현재 문서)
└── LICENSE            # 오픈소스 라이선스 (MIT)
```

## 개발 환경 준비 절차
1. **Python 버전 확인**
   ```bash
   python --version  # 3.11 이상 권장
   ```
2. **가상환경 생성 및 활성화**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```
3. **pip 업그레이드 및 필수 패키지 설치**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
4. **환경변수 파일 구성**
   - `.env.example`을 복사하여 `.env` 파일을 생성합니다.
   - 실거래용 빗썸 API 키/시크릿, 데이터베이스 경로 등을 입력합니다.

## 환경변수 가이드
| 항목 | 키 | 설명 | 기본값 |
| --- | --- | --- | --- |
| 애플리케이션 환경 | `APP_ENV` | 운영 단계 구분 (`development`, `production` 등) | `development` |
| 표준 시간대 | `APP_TIMEZONE` | 시스템 기준 시간대 | `Asia/Seoul` |
| 로그 레벨 | `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` 중 선택 | `INFO` |
| 로그 디렉터리 | `LOG_DIR` | 로그 파일 저장 경로 | `logs` |
| 로그 보관 개수 | `LOG_BACKUP_COUNT` | 순환 로그 최대 보관 파일 수 | `7` |
| 빗썸 API 키 | `BITHUMB_API_KEY` | 실거래 전용 API 키 | 없음 |
| 빗썸 API 시크릿 | `BITHUMB_API_SECRET` | 실거래 전용 API 시크릿 | 없음 |
| 데이터베이스 URL | `DATABASE_URL` | SQLAlchemy 연결 문자열 | `sqlite:///data/app.db` |

> ⚠️ `.env` 파일은 Git에 커밋되지 않으며, 빗썸 API 자격 증명은 외부 유출을 방지하기 위해 반드시 안전하게 관리해야 합니다.

## 로깅 구성 개요
- `src/utils/logger.py`에서 콘솔 및 파일 로그를 동시에 처리하도록 설정했습니다.
- 기본값은 자정 기준 일별 순환(TimedRotating) 로그와 7개 파일 보관입니다.
- 로그 디렉터리가 존재하지 않는 경우 자동으로 생성합니다.
- `get_logger(__name__)` 형태로 사용하면 공통 포맷과 핸들러를 재사용할 수 있습니다.

## Phase 3 주요 산출물
- **전략 신호 엔진 고도화**: `src/core/indicators.py`에서 캔들 자료구조와 EMA/RSI/ATR/거래량 지표를 계산하고, `src/core/signals.py`의 `SignalGenerator`가 실데이터 기반으로 BUY/SELL/HOLD 신호를 산출합니다.
- **리스크 관리 & 파라미터 스토어**: `src/core/parameters.py`의 `StrategyParameterStore`가 DB에 전략 파라미터를 유지·검증하며, `src/core/risk.py`의 `RiskManager`가 Kelly 비율, ATR 손절, 트레일링 스탑을 활용해 포지션 사이즈와 손익 한도를 계산합니다.
- **전략 실행 파이프라인**: `src/core/strategy.py`의 `StrategyEngine`이 파라미터-신호-리스크를 연결하여 실행하고, `PerformanceTracker`로 신호 누적 통계를 제공합니다.
- **신호 이력 저장소 추가**: 새로운 `strategy_signals` 테이블과 `StrategySignalRepository`로 모든 실시간 신호와 리스크 지표를 DB에 기록하며, Alembic 마이그레이션 `20240924_0002_add_strategy_signals.py`가 스키마를 확장합니다.
- **실거래 데이터 기반 테스트**: `tests/fixtures/bithumb_candles_btc_krw_1h.json`에 수집한 빗썸 1시간봉 데이터를 활용해 `tests/core/` 단위 테스트에서 지표 정확도와 신호 로직, 엔진 통합 동작을 검증합니다.

## 데이터베이스 스키마 개요
| 테이블 | 설명 | 주요 컬럼 |
| --- | --- | --- |
| `markets` | 빗썸 종목 기본 정보 | `symbol`, `korean_name`, `english_name`, `warning_level`, `is_active` |
| `trades` | 체결 내역 저장 | `order_id`, `symbol`, `side`, `price`, `quantity`, `fee`, `executed_at` |
| `positions` | 현재 보유 포지션 | `symbol`, `quantity`, `avg_price`, `entry_time`, `status` |
| `pnl_daily` | 일별 손익 지표 | `date`, `realized_pnl`, `unrealized_pnl`, `total_equity`, `return_rate` |
| `configs` | 전략/시스템 설정 | `key`, `value`, `description` |
| `order_history` | 주문 이력 추적 | `order_id`, `symbol`, `order_type`, `status` |
| `strategy_signals` | 전략 신호 이력 | `symbol`, `signal_type`, `price`, `strength`, `rsi`, `atr`, `risk_amount`, `created_at` |

### 마이그레이션 사용법
```bash
# 최신 스키마 적용
alembic upgrade head

# 새로운 변경 사항 기록 (예시)
alembic revision -m "add new column" --autogenerate
```

## 마켓 동기화 & 스케줄러
```python
from src.data import MarketSynchronizer, SessionLocal
from src.exchange import BithumbClient
from src.jobs import MarketSyncJob

client = BithumbClient()
synchronizer = MarketSynchronizer(client, SessionLocal)
job = MarketSyncJob(synchronizer)

# 즉시 한 번 실행
dashboard = job.run()
print(dashboard)
```
- `MarketSynchronizer`는 `/public/ticker/ALL_KRW`와 `/public/assetsstatus/ALL_KRW`를 조회해 신규 상장 종목을 추가하고, 더 이상 제공되지 않는 심볼을 자동으로 비활성화합니다.
- `MarketSyncJob.run_pending()`을 주기적으로 호출하면 10분 간격으로 동기화 작업이 실행됩니다.

## 데이터 백업
- 명령형 스크립트: `python scripts/backup_database.py --retention-days 7`
- 내부 함수: `src.data.backup_database(retention_days=7)`
- 백업 파일은 `<DATA_DIR>/backups/app-YYYYMMDDHHMMSS.db` 형태로 저장되며, 보관 기한을 초과한 파일은 자동으로 삭제됩니다.

## 공통 유틸리티
- `src/utils/exceptions.py`: 애플리케이션에서 공통적으로 사용하는 예외 계층 정의
- `src/utils/time_utils.py`: KST/UTC 기준 시간 처리, ISO8601 파싱 등 시간 관련 도우미
- `src/utils/converters.py`: 문자열·숫자·Decimal 간 변환 및 불리언 파싱 도우미

---

### 문의 및 기여
프로젝트 구조나 환경 설정에 대한 추가 요청 사항이 있다면 이슈로 등록하거나 Pull Request를 통해 기여해주세요.
