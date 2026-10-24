# 🌐 Render.com 클라우드 웹사이트 배포 완벽 가이드

> **AI-STEAM 악보 인식 & 인터랙티브 에디터**를 인터넷 어디서나 접속할 수 있는 공개 웹사이트로 배포하는 가이드입니다.  
> GitHub 저장소(`yjchoi101222/ai_steam`)와 연동되어 코드 푸시 시 자동으로 무중단 배포됩니다.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/yjchoi101222/ai_steam)

---

## 📌 목차
1. [배포 준비 완료된 구성 요소](#1-배포-준비-완료된-구성-요소)
2. [방법 1: Blueprint 원클릭 자동 배포 (가장 추천)](#2-방법-1-blueprint-원클릭-자동-배포-가장-추천)
3. [방법 2: Render 대시보드 수동 배포](#3-방법-2-render-대시보드-수동-배포)
4. [방법 3: Docker 컨테이너 배포](#4-방법-3-docker-컨테이너-배포)
5. [Render 무료 플랜 운영 팁 & 주의사항](#5-render-무료-플랜-운영-팁--주의사항)
6. [대안 무료 호스팅 플랫폼 안내 (HuggingFace 등)](#6-대안-무료-호스팅-플랫폼-안내)

---

## 1. 배포 준비 완료된 구성 요소

본 프로젝트에는 Render 배포를 위한 모든 핵심 설정 파일이 사전에 준비되어 있습니다:

| 파일명 | 역할 |
| :--- | :--- |
| `render.yaml` | Render Blueprint 선언형 설정 (빌드, 실행, 포트, 헬스체크 자동 감지) |
| `build.sh` | Linux 클라우드 환경 패키지 빌드 스크립트 (`onnxruntime` CPU 바이너리 최적화 포함) |
| `Dockerfile` | Ubuntu 기반 완벽 격리 컨테이너 빌드 (Render, HuggingFace, Fly.io 호환) |
| `.dockerignore` | 불필요한 캐시/임시 파일 업로드 방지 |
| `requirements.txt` | `opencv-python-headless`, `onnxruntime`, `python-multipart` 등 클라우드 호환 최신화 |
| `main.py` | `$PORT` 환경변수 자동 바인딩 및 `/healthz` 모니터링 엔드포인트 제공 |

---

## 2. 방법 1: Blueprint 원클릭 자동 배포 (가장 추천)

프로젝트에 포함된 `render.yaml` 덕분에 복잡한 설정 없이 2~3번의 클릭만으로 배포됩니다.

### 1단계: GitHub에 최신 코드 푸시
로컬 터미널에서 변경 사항을 저장소에 푸시합니다:
```bash
git add .
git commit -m "feat: Add Render deployment configuration and Dockerfile"
git push origin main
```

### 2단계: Render.com 접속 및 Blueprint 생성
1. [Render.com](https://render.com)에 접속하여 **GitHub 계정으로 로그인**합니다.
2. 상단 네비게이션에서 **[Blueprints]** 탭을 클릭합니다.
3. **[New Blueprint Instance]** 버튼을 클릭합니다.
4. 본인의 GitHub 저장소(`ai_steam` 또는 `ai-sheet-music-editor`)를 선택합니다.
5. 저장소 안의 `render.yaml`이 자동으로 인식되며, 아래와 같은 화면이 나타납니다:
   - **Service Name**: `ai-sheet-music-editor`
   - **Environment**: `Python`
   - **Plan**: `Free`
   - **Region**: `Oregon` (또는 `Singapore`)
6. **[Apply]** 버튼을 누르면 빌드가 시작됩니다!

---

## 3. 방법 2: Render 대시보드 수동 배포

대시보드에서 직접 웹 서비스를 구성하고 싶을 때 사용합니다.

### 1단계: 새 Web Service 생성
1. Render 대시보드 우측 상단 **[New +]** → **[Web Service]** 클릭
2. **Build and deploy from a Git repository** 선택 후 [Next]
3. 본인의 저장소(`yjchoi101222/ai_steam`) 선택 후 [Connect]

### 2단계: 서비스 환경 설정
아래 표의 항목을 입력합니다:

| 설정 항목 | 입력값 | 설명 |
| :--- | :--- | :--- |
| **Name** | `ai-steam-omr` (원하는 영문 이름) | 서비스의 기본 도메인이 됨 (`*.onrender.com`) |
| **Region** | `Singapore` 또는 `Oregon` | 한국과 지연시간이 적은 싱가포르 권장 |
| **Branch** | `main` | 배포할 기본 브랜치 |
| **Runtime** | `Python` | Python 런타임 선택 |
| **Build Command** | `bash build.sh` | 빌드 스크립트 실행 (`download_models.py` 자동 호출) |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` | Uvicorn 서버 기동 |
| **Instance Type** | `Free` (0.1 CPU, 512 MB RAM) | 무료 인스턴스 |

### 3단계: 환경 변수(Environment Variables) 설정 (선택 사항)
- `PYTHON_VERSION`: `3.11.9`
- `PORT`: `10000` (Render 기본값)

### 4단계: 배포 시작
- 맨 아래 **[Create Web Service]** 버튼을 클릭합니다.
- 콘솔 로그에 빌드 진행 상황이 표시되며, 약 2~4분 후 `Your service is live 🎉` 메시지와 함께 **접속 가능한 공개 URL**이 생성됩니다.
  - 예: `https://ai-steam-omr.onrender.com`

---

## 4. 방법 3: Docker 컨테이너 배포

서버 환경의 일관성을 100% 보장하고 싶거나, 시스템 라이브러리(`libgl1`, `ffmpeg` 등)를 온전히 격리하고 싶을 때 사용합니다.

1. Render에서 **[New +]** → **[Web Service]** 클릭
2. 저장소 연결 후 **Runtime**을 `Python` 대신 **`Docker`**로 선택
3. 저장소 루트에 있는 `Dockerfile`이 자동으로 감지됩니다.
4. **[Create Web Service]** 클릭 시 Docker 이미지를 빌드하여 배포합니다.

---

## 5. Render 무료 플랜 운영 팁 & 주의사항

> [!NOTE]
> **15분 미접속 시 슬립(Sleep) 모드 전환**
> Render 무료 웹 서비스는 15분 동안 방문자가 없으면 인스턴스가 절전(Spin down) 상태로 전환됩니다.  
> 이후 누군가 URL에 접속하면 다시 깨어나는 데(Cold Start) 약 **30초 ~ 50초**가 소요됩니다.  
> 이는 장애가 아니며 무료 플랜의 정상 동작입니다.

> [!TIP]
> **슬립 모드 방지 꿀팁 (무료 Uptime 모니터링)**
> [UptimeRobot](https://uptimerobot.com) 또는 [cron-job.org](https://cron-job.org) 같은 무료 서비스에 가입한 후,  
> 생성된 사이트의 헬스체크 주소(`https://내서비스.onrender.com/healthz`)를 **10분 주기 HTTP GET 요청**으로 등록해 두면 서버가 잠들지 않고 24시간 즉시 반응합니다!

> [!WARNING]
> **512MB RAM 메모리 제약 & OMR 파일 처리 주의**
> 무료 플랜은 RAM이 512MB로 제한됩니다. 초고해상도(4000px 이상) 악보 이미지를 Deep 모드로 OMR 실행할 경우 메모리 스파이크로 서버가 재부팅될 수 있습니다.  
> - **권장**: 웹 인터페이스에서 **`⚡ 빠른 추출 (Fast)`** 모드를 사용하세요. 시스템이 자동으로 1350px로 안전하게 리사이징하여 메모리를 300MB 이내로 유지합니다.

> [!IMPORTANT]
> **파일 스토리지 (Ephemeral Disk) & 상시 에디터 동작**
> Render 무료 플랜은 임시 디스크를 사용합니다. 사용자가 업로드하여 변환한 임시 캐시 파일은 서버 재시작 시 초기화될 수 있으나,  
> 언제든지 웹 상단 **[➕ 새 악보 만들기]**를 통해 데모 파일 없이 새로운 악보를 즉시 생성하여 편집할 수 있습니다.

---

## 6. Render.com 자주 발생하는 오류 및 해결법 (Troubleshooting)

| 증상 및 오류 메시지 | 근본 원인 | 해결 방법 |
| :--- | :--- | :--- |
| **`urllib.error.HTTPError: HTTP Error 404`** (빌드 실패) | 이전 `build.sh`에서 존재하지 않는 `.pkl` 가중치 URL 요청 | ✅ 신규 `download_models.py` 스크립트로 실제 ONNX 모델만 직접 다운로드하도록 수정 완료 |
| **`bash: ./build.sh: Permission denied`** | Git 체크아웃 시 실행 권한 누락 | Build Command를 `./build.sh` 대신 **`bash build.sh`**로 설정 |
| **`Exited with status 137` / 서버 급작스러운 재시작** | Render 무료 플랜의 **512MB RAM 초과 (OOM Crash)** | 1. 변환 시 **Fast 모드** 사용<br>2. 또는 RAM 16GB 무료인 **Hugging Face Spaces** 사용 |
| **`Bad Gateway (502)` 또는 첫 접속 지연** | 무료 플랜 15분 미접속 후 슬립 모드(Spin Down) | UptimeRobot으로 10분 주기 `/healthz` 핑 설정 또는 50초 대기 후 새로고침 |
| **`Health Check Failed`** | 포트 바인딩 불일치 또는 헬스체크 타임아웃 | Render가 주입하는 `$PORT` 자동 수신 및 `/healthz` 엔드포인트 제공으로 해결됨 |

---

## 7. 대안 무료 호스팅 플랫폼 안내

만약 OMR AI 연산에 더 큰 메모리가 필요하거나 다른 무료 플랫폼을 함께 쓰고 싶다면 다음 옵션을 고려할 수 있습니다:

### 1) Hugging Face Spaces (추천: 무료 16GB RAM / 2 vCPU)
- AI 모델 구동에 특화된 세계 최대 머신러닝 플랫폼.
- 저장소에 포함된 `Dockerfile`을 그대로 Hugging Face Space(Docker 타입)로 가져오면 **무료로 16GB RAM** 환경에서 oemer를 쾌속 구동할 수 있습니다.

### 2) Railway.app / Fly.io
- Docker 컨테이너 기반 초고속 배포 및 낮은 대기 시간 지원.

