"""
분석 HTML 화면 (9단계).

화면은 틀(HTML)만 내려주고, 실제 작업 생성·상태 확인·결과 조회는
브라우저(static/js/analysis.js)가 DRF API(/api/v1/analyses/)를 호출해서 처리합니다.
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import AnalysisJob


@login_required
def analysis_home(request):
    page_config = {                                   # JS 가 쓰는 설정값 (json_script 로 전달)
        "apiUrl": "/api/v1/analyses/",
        "cameraUrls": settings.ALLOWED_CAMERA_URLS,
        "captureSeconds": settings.CAMERA_CAPTURE_SECONDS,
        "maxUploadMb": settings.MAX_UPLOAD_MB,
        "allowedExt": settings.ALLOWED_VIDEO_EXTENSIONS,
        "actions": dict(AnalysisJob.Action.choices),
    }
    return render(request, "analyses/index.html", {
        "page_config": page_config,
        "actions": AnalysisJob.Action.choices,
        "camera_urls": settings.ALLOWED_CAMERA_URLS,
        "capture_seconds": settings.CAMERA_CAPTURE_SECONDS,
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        "allowed_ext": ", ".join(settings.ALLOWED_VIDEO_EXTENSIONS),
    })
