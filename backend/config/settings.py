"""
Django 설정 (3단계: PostgreSQL + analyses 앱 + Admin).

비밀번호·DB 주소 같은 값은 코드에 쓰지 않고 프로젝트 최상위 .env 에서 읽습니다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
load_dotenv(BASE_DIR.parent / ".env", override=True)                       # vision_action_platform/.env

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
    "analyses",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL (값은 .env)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "vision_action"),
        "USER": os.getenv("POSTGRES_USER", "vision"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

# 업로드 영상 저장 위치 (DB에는 경로만 저장)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# 로그인·로그아웃 이동 주소
LOGIN_URL = "login"                   # 로그인이 필요한 페이지 → /accounts/login/
LOGIN_REDIRECT_URL = "analysis_home"  # 로그인 성공 → /analyses/
LOGOUT_REDIRECT_URL = "login"         # 로그아웃 → 로그인 화면

# DRF: 기본은 "로그인한 사용자만"
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",   # 브라우저 로그인
        "rest_framework.authentication.BasicAuthentication",     # curl -u 아이디:비번
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

# 분석 입력 제한 (.env)
ALLOWED_CAMERA_URLS = [u.strip() for u in os.getenv("ALLOWED_CAMERA_URLS", "").split(",") if u.strip()]
CAMERA_CAPTURE_SECONDS = int(os.getenv("CAMERA_CAPTURE_SECONDS", "8"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))
ALLOWED_VIDEO_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv"]

# Celery + Redis (6단계)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL                 # 작업 대기열
CELERY_RESULT_BACKEND = REDIS_URL             # 작업 실행 결과(보조). 영구 결과는 PostgreSQL
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE = True                  # Worker가 처리 중 죽으면 작업이 사라지지 않게
CELERY_WORKER_PREFETCH_MULTIPLIER = 1         # 무거운 작업은 하나씩
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
FAKE_ANALYSIS_SECONDS = float(os.getenv("FAKE_ANALYSIS_SECONDS", "5"))   # 6단계 가짜 처리 시간

# FastAPI AI 서버 (7단계)
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8001").rstrip("/")
AI_REQUEST_TIMEOUT = float(os.getenv("AI_REQUEST_TIMEOUT", "900"))    # heavy 추론은 오래 걸림 (초)

# IP Webcam 수집 (8단계)
CAMERA_OPEN_TIMEOUT = float(os.getenv("CAMERA_OPEN_TIMEOUT", "10"))   # 카메라 연결 대기 (초)
CAMERA_READ_TIMEOUT = float(os.getenv("CAMERA_READ_TIMEOUT", "5"))    # 프레임이 이 시간 동안 안 오면 끊김
CAMERA_MAX_WIDTH = int(os.getenv("CAMERA_MAX_WIDTH", "960"))         # 저장 영상 가로 최대 크기
CAMERA_MIN_FRAMES = int(os.getenv("CAMERA_MIN_FRAMES", "30"))        # 이보다 적게 모이면 실패
