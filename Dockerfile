# Python 3.9 Slim 기반 이미지 사용
FROM python:3.9-slim

# 필수 패키지 설치 및 Chrome 설치를 위한 준비
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Google Chrome Stable 설치 (직접 다운로드 방식)
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# Poetry 설치
RUN pip install poetry

# 의존성 파일 복사 및 설치
COPY pyproject.toml poetry.lock* /app/

# 가상환경 생성하지 않고 패키지 설치 (도커 내부이므로)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# 소스 코드 복사
COPY . /app

# 실행 명령어
CMD ["python", "-u", "grade_checker.py"]
