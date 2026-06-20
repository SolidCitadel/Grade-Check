# Playwright 공식 이미지 (Chromium + 시스템 의존성 사전 설치, playwright 1.60.0 일치)
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

# Poetry 설치
RUN pip install --no-cache-dir poetry

# 의존성 파일 복사 및 설치 (도커 내부이므로 가상환경 미생성)
COPY pyproject.toml poetry.lock* /app/
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# 소스 코드 복사
COPY . /app

# 헤드리스로 동작
ENV HEADLESS=true

CMD ["python", "-u", "grade_checker.py"]
