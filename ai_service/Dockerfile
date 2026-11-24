# FastAPI 추론 서버 (MediaPipe heavy + YOLO11n-pose + RandomForest)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    YOLO_CONFIG_DIR=/tmp/Ultralytics

# OpenCV / MediaPipe 실행에 필요한 시스템 라이브러리
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 libegl1 libgles2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch 는 CPU 버전으로 먼저 설치 (GPU 버전은 수 GB 라서 이미지가 너무 커짐)
COPY requirements.txt .
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

COPY . .
# models/ 는 docker-compose 에서 볼륨으로 연결 (이미지에 넣지 않음)

EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
