from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import camera_views, page_views
from .views import AnalysisJobViewSet

# 화면 (HTML)  →  config/urls.py 에서 /analyses/ 로 연결
urlpatterns = [
    path("", page_views.analysis_home, name="analysis_home"),
    path("camera/facing/", camera_views.camera_facing, name="camera_facing"),   # 전면/후면 전환
]

# API (JSON)   →  config/urls.py 에서 /api/v1/ 로 연결
router = DefaultRouter()
router.register("analyses", AnalysisJobViewSet, basename="analysis")
api_urlpatterns = [
    path("", include(router.urls)),
]
