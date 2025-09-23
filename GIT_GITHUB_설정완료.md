# Git & GitHub 설정 완료 안내

## ✅ 완료된 Git 설정

### 1. Git 사용자 정보 설정
```bash
git config --global user.name "tjqjaqhd"
git config --global user.email "dlsnrj@gmail.com"
git config --global init.defaultBranch main
git config --global core.autocrlf false
git config --global core.fileMode false
```

### 2. 로컬 Git 저장소 초기화
- 위치: `/home/tjqjaqhd/projects/bithumb-trading-system/`
- 첫 번째 커밋 완료: `4d93ec0`
- 커밋 메시지: "🚀 Initial commit: Bithumb KRW Trading System"

## 🔗 GitHub 연결 방법

### 단계 1: GitHub에서 새 레포지토리 생성
1. https://github.com 에 로그인
2. 우측 상단 "+" 버튼 클릭 → "New repository"
3. Repository name: `bithumb-trading-system` (또는 원하는 이름)
4. Description: `Bithumb KRW market cryptocurrency trading system`
5. **⚠️ "Add a README file" 체크 해제** (이미 로컬에 파일이 있음)
6. "Create repository" 클릭

### 단계 2: 로컬 저장소와 GitHub 연결
레포지토리 생성 후 GitHub에서 제공하는 명령어를 사용하거나, 다음 명령어로 연결:

```bash
cd ~/projects/bithumb-trading-system

# GitHub 원격 저장소 추가
git remote add origin https://github.com/tjqjaqhd/bithumb-trading-system.git

# 메인 브랜치로 푸시
git branch -M main
git push -u origin main
```

### 단계 3: GitHub 인증
HTTPS 방식 사용 시:
- Username: `tjqjaqhd`
- Password: GitHub Personal Access Token 필요
  - GitHub → Settings → Developer settings → Personal access tokens → Generate new token
  - repo 권한 체크 후 생성

## 📁 현재 프로젝트 구조

```
bithumb-trading-system/
├── src/                 # 메인 소스 코드
│   ├── api/            # FastAPI 백엔드
│   ├── core/           # 전략 엔진
│   ├── data/           # 데이터베이스 모델
│   ├── exchange/       # 빗썸 API 클라이언트
│   └── backtest/       # 백테스트 시스템
├── tests/              # 테스트 코드
├── dashboard.html      # 웹 대시보드
├── api_simple.py       # 간단한 API 서버
├── requirements.txt    # 의존성 패키지
└── README.md          # 프로젝트 문서
```

## 🔄 WSL-Windows 동기화

현재 프로젝트는 두 위치에 있습니다:
- **WSL**: `/home/tjqjaqhd/projects/bithumb-trading-system/` (Git 저장소)
- **Windows**: `/mnt/c/Users/SEOBEOMBONG/gogo/` (개발 작업 위치)

### 동기화 방법:
```bash
# WSL에서 Windows로 복사
cp -r ~/projects/bithumb-trading-system/* /mnt/c/Users/SEOBEOMBONG/gogo/

# Windows에서 WSL로 복사 (변경사항 반영 시)
cp -r /mnt/c/Users/SEOBEOMBONG/gogo/* ~/projects/bithumb-trading-system/
```

## 📋 다음 단계

1. **GitHub 레포지토리 생성** (수동으로 진행)
2. **원격 저장소 연결** (위 명령어 사용)
3. **첫 번째 푸시 완료**
4. **Phase 7: 테스트 및 안정화 진행**

---

**설정 완료일**: 2025-09-22
**Git 사용자**: tjqjaqhd (dlsnrj@gmail.com)
**로컬 저장소**: `/home/tjqjaqhd/projects/bithumb-trading-system/`