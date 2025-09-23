#!/usr/bin/env python3
"""
통합 시스템 실행 스크립트
자동매매 엔진 + 대시보드를 동시 실행
"""

import asyncio
import signal
import sys
import os
import subprocess
from pathlib import Path
from typing import List
import time

# 프로젝트 루트 설정
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

class UnifiedSystemLauncher:
    """통합 시스템 런처"""

    def __init__(self):
        self.processes: List[subprocess.Popen] = []
        self.running = False

    def signal_handler(self, signum, frame):
        """시그널 핸들러"""
        print(f"\n🛑 종료 시그널 수신: {signum}")
        self.stop_all_processes()
        sys.exit(0)

    def stop_all_processes(self):
        """모든 프로세스 종료"""
        print("🔄 모든 프로세스 종료 중...")

        for process in self.processes:
            try:
                if process.poll() is None:  # 프로세스가 아직 실행 중인 경우
                    process.terminate()
                    # 5초 후에도 종료되지 않으면 강제 종료
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            except Exception as e:
                print(f"프로세스 종료 중 오류: {e}")

        self.processes.clear()
        print("✅ 모든 프로세스 종료 완료")

    def start_trading_engine(self):
        """자동매매 엔진 시작"""
        print("🚀 자동매매 엔진 시작...")

        try:
            # 가상환경 활성화 명령
            if os.name == 'nt':  # Windows
                activate_cmd = "venv\\Scripts\\activate"
            else:  # Linux/Mac
                activate_cmd = "source venv/bin/activate"

            # 자동매매 엔진 실행
            if os.name == 'nt':
                cmd = f"{activate_cmd} && python unified_trading_engine.py"
                process = subprocess.Popen(cmd, shell=True, cwd=PROJECT_ROOT)
            else:
                cmd = ["bash", "-c", f"{activate_cmd} && python unified_trading_engine.py"]
                process = subprocess.Popen(cmd, cwd=PROJECT_ROOT)

            self.processes.append(process)
            print("✅ 자동매매 엔진 시작됨")
            return True

        except Exception as e:
            print(f"❌ 자동매매 엔진 시작 실패: {e}")
            return False

    def start_dashboard(self):
        """대시보드 시작"""
        print("🖥️  대시보드 서버 시작...")

        try:
            # 가상환경 활성화 명령
            if os.name == 'nt':  # Windows
                activate_cmd = "venv\\Scripts\\activate"
            else:  # Linux/Mac
                activate_cmd = "source venv/bin/activate"

            # 대시보드 실행
            if os.name == 'nt':
                cmd = f"{activate_cmd} && python unified_dashboard.py"
                process = subprocess.Popen(cmd, shell=True, cwd=PROJECT_ROOT)
            else:
                cmd = ["bash", "-c", f"{activate_cmd} && python unified_dashboard.py"]
                process = subprocess.Popen(cmd, cwd=PROJECT_ROOT)

            self.processes.append(process)
            print("✅ 대시보드 서버 시작됨")
            return True

        except Exception as e:
            print(f"❌ 대시보드 시작 실패: {e}")
            return False

    def check_prerequisites(self):
        """사전 요구사항 확인"""
        print("🔍 사전 요구사항 확인 중...")

        # .env 파일 확인
        env_file = PROJECT_ROOT / ".env"
        if not env_file.exists():
            print("❌ .env 파일이 없습니다!")
            return False

        # API 키 확인
        from src.utils.dotenv_simple import load_dotenv
        load_dotenv(env_file)

        api_key = os.getenv("BITHUMB_API_KEY")
        secret_key = os.getenv("BITHUMB_SECRET_KEY")

        if not api_key or not secret_key:
            print("❌ 빗썸 API 키가 설정되지 않았습니다!")
            return False

        # 의존성 확인
        try:
            import requests
            import jwt
            import fastapi
            import uvicorn
            print("✅ 모든 의존성 확인됨")
            return True
        except ImportError as e:
            print(f"❌ 필요한 패키지가 설치되지 않았습니다: {e}")
            print("pip install -r requirements.txt 를 실행하세요.")
            return False

    def start_system(self):
        """통합 시스템 시작"""
        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        print("=" * 80)
        print("🚀 빗썸 자동매매 통합 시스템 시작")
        print("=" * 80)

        # 사전 요구사항 확인
        if not self.check_prerequisites():
            return False

        # 자동매매 엔진 시작
        if not self.start_trading_engine():
            return False

        # 잠시 대기
        time.sleep(3)

        # 대시보드 시작
        if not self.start_dashboard():
            self.stop_all_processes()
            return False

        print("\n" + "=" * 80)
        print("✅ 통합 시스템 시작 완료!")
        print("📊 대시보드: http://localhost:8000")
        print("🔄 자동매매 엔진: 백그라운드에서 실행 중")
        print("⚠️  종료하려면 Ctrl+C 를 누르세요")
        print("=" * 80)

        self.running = True

        try:
            # 프로세스 상태 모니터링
            while self.running:
                time.sleep(10)

                # 죽은 프로세스 확인
                for i, process in enumerate(self.processes):
                    if process.poll() is not None:
                        print(f"⚠️ 프로세스 {i+1}이 종료되었습니다 (exit code: {process.returncode})")

                # 모든 프로세스가 종료되면 시스템 종료
                if all(p.poll() is not None for p in self.processes):
                    print("❌ 모든 프로세스가 종료되었습니다. 시스템을 종료합니다.")
                    break

        except KeyboardInterrupt:
            print("\n🛑 사용자에 의해 중단됨")
        finally:
            self.stop_all_processes()

        return True

    def show_menu(self):
        """메뉴 표시"""
        print("\n" + "=" * 50)
        print("빗썸 자동매매 통합 시스템")
        print("=" * 50)
        print("1. 전체 시스템 시작 (엔진 + 대시보드)")
        print("2. 자동매매 엔진만 시작")
        print("3. 대시보드만 시작")
        print("4. 시스템 상태 확인")
        print("0. 종료")
        print("=" * 50)

        choice = input("선택하세요 (0-4): ").strip()
        return choice

    def run_interactive(self):
        """대화형 모드 실행"""
        while True:
            choice = self.show_menu()

            if choice == "0":
                print("👋 시스템을 종료합니다.")
                self.stop_all_processes()
                break

            elif choice == "1":
                if self.start_system():
                    print("✅ 시스템이 정상적으로 종료되었습니다.")
                else:
                    print("❌ 시스템 시작에 실패했습니다.")

            elif choice == "2":
                if self.check_prerequisites():
                    self.start_trading_engine()
                    print("⚠️ 자동매매 엔진이 백그라운드에서 실행 중입니다.")
                    print("종료하려면 메뉴에서 '0'을 선택하세요.")

            elif choice == "3":
                if self.check_prerequisites():
                    self.start_dashboard()
                    print("📊 대시보드: http://localhost:8000")
                    print("종료하려면 메뉴에서 '0'을 선택하세요.")

            elif choice == "4":
                print(f"실행 중인 프로세스: {len(self.processes)}개")
                for i, process in enumerate(self.processes):
                    status = "실행 중" if process.poll() is None else f"종료됨 (코드: {process.returncode})"
                    print(f"  프로세스 {i+1}: {status}")

            else:
                print("잘못된 선택입니다.")

            input("\n계속하려면 Enter를 누르세요...")


def main():
    """메인 함수"""
    launcher = UnifiedSystemLauncher()

    # 명령행 인수 확인
    if len(sys.argv) > 1:
        if sys.argv[1] == "auto":
            # 자동 모드 (전체 시스템 시작)
            launcher.start_system()
        elif sys.argv[1] == "engine":
            # 엔진만 시작
            if launcher.check_prerequisites():
                launcher.start_trading_engine()
                try:
                    while launcher.processes and launcher.processes[0].poll() is None:
                        time.sleep(1)
                except KeyboardInterrupt:
                    launcher.stop_all_processes()
        elif sys.argv[1] == "dashboard":
            # 대시보드만 시작
            if launcher.check_prerequisites():
                launcher.start_dashboard()
                try:
                    while launcher.processes and launcher.processes[0].poll() is None:
                        time.sleep(1)
                except KeyboardInterrupt:
                    launcher.stop_all_processes()
        else:
            print("사용법: python start_unified_system.py [auto|engine|dashboard]")
    else:
        # 대화형 모드
        launcher.run_interactive()


if __name__ == "__main__":
    main()