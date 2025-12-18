# 🎓 경희대학교 성적 확인 알림 봇

Info21 포털을 주기적으로 모니터링하여 **성적 변동(미입력 -> 입력, 등급 변경)** 발생 시 **Discord**로 알림을 보내주는 봇입니다.

## ✨ 주요 기능
- **자동 로그인**: Info21 포털에 자동 접속 (Headless 모드 지원)
- **실시간 감지**: 성적 입력/수정 즉시 감지 (A+ 등급 확인 가능)
- **Discord 알림**: 변동 사항 발생 시 즉시 푸시 알림 전송
- **Docker 지원**: 서버에 쉽게 배포하여 24시간 가동 가능

---

## 🚀 빠른 시작 (Docker, 권장)

서버(EC2, NAS 등)에서 가장 간편하게 실행하는 방법입니다.

1. **설정 파일 준비**
   `.env.example`을 `.env`로 복사하고 학번, 비밀번호, 웹훅 URL을 입력하세요.
   ```bash
   cp .env.example .env
   vi .env
   ```

2. **실행**
   ```bash
   docker-compose up -d
   ```

3. **로그 확인**
   ```bash
   docker-compose logs -f
   ```

---

## 💻 로컬에서 실행 (개발용)

**필수 요구사항**: Python 3.9+, Chrome 브라우저

1. **설치**
   ```bash
   git clone [REPO_URL]
   cd Grade-Check
   poetry install  # 또는 pip install -r requirements.txt
   ```

2. **설정**
   `.env` 파일을 생성하고 정보를 입력하세요. (위 Docker 방식과 동일)

3. **실행**
   ```bash
   poetry run python grade_checker.py
   ```

---

## ⚙️ 설정 (`.env`)

| 변수명 | 설명 | 비고 |
|:---:|:---|:---|
| `LOGIN_URL` | Info21 로그인 주소 | 변경 X |
| `GRADE_URL` | 금학기 성적 조회 주소 | 변경 X |
| `PORTAL_ID` | 학번 | 필수 |
| `PASSWORD` | 포털 비밀번호 | 필수 |
| `DISCORD_WEBHOOK_URL` | 디스코드 웹훅 주소 | 필수 (알림용) |
| `CHECK_INTERVAL` | 확인 주기 (분) | 기본 30분 |

## ❓ 문제 해결

- **로그인 실패**: 비밀번호가 맞는지, 2차 인증이 필요한 계정이 아닌지 확인하세요.
- **성적 테이블 미감지**: 인터넷 속도가 느린 경우 `grade_checker.py`의 `WebDriverWait` 시간을 늘려보세요.
- **headless 모드**: 서버 환경에서는 `headless=True`로 동작합니다. 로컬 디버깅 시 `False`로 변경하면 브라우저 화면을 볼 수 있습니다.

## License
MIT License
