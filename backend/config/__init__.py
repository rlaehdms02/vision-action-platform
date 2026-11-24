# Django가 시작될 때 Celery 앱도 함께 불러와서, views.py 의 .delay() 가 이 앱을 사용하게 함
from .celery import app as celery_app

__all__ = ("celery_app",)
