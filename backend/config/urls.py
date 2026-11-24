from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from analyses import dashboard_views
from analyses.urls import api_urlpatterns

admin.site.site_header = "Vision AI 관리자"
admin.site.site_title = "Vision AI 관리자"
admin.site.index_title = "동작 분석 관리"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="analysis_home", permanent=False)),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),               # /accounts/signup/
    path("accounts/", include("django.contrib.auth.urls")),    # /accounts/login/, /accounts/logout/
    path("analyses/", include("analyses.urls")),               # /analyses/ (로그인 필요 화면)
    path("dashboard/", dashboard_views.dashboard, name="dashboard"),           # 관리자 대시보드 (staff)
    path("dashboard/data/", dashboard_views.dashboard_data, name="dashboard_data"),
    path("api/v1/", include(api_urlpatterns)),                 # /api/v1/analyses/ (DRF API)
    path("api-auth/", include("rest_framework.urls")),         # DRF 화면의 로그인/로그아웃
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
