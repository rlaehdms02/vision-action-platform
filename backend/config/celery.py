"""
Celery 앱: Django 설정을 읽고, 각 앱의 tasks.py 를 자동으로 찾습니다.

Worker 실행 (backend 폴더):
    celery -A config worker -l info --concurrency=1
"""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")   # settings 의 CELERY_* 값 사용
app.autodiscover_tasks()                                             # analyses/tasks.py 자동 등록
