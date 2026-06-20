# Playwright 공식 이미지 (Chromium + 시스템 의존성 사전 설치, playwright 1.60.0 일치)
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

# uv 설치 (공식 이미지에서 바이너리만 복사)
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /uvx /bin/

# 의존성 파일 복사 및 설치 (lock 고정, 프로젝트 루트·dev 제외)
COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-install-project --no-dev

# uv가 생성한 가상환경을 PATH에 등록
ENV PATH="/app/.venv/bin:$PATH"

# 소스 코드 복사
COPY . /app

# 헤드리스로 동작
ENV HEADLESS=true

CMD ["python", "-u", "grade_checker.py"]
