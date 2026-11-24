"""
IP Webcam 카메라 제어 (화면에서 전면/후면 카메라 전환).

GET  /analyses/camera/facing/?camera_url=...           → 지금 어느 카메라인지
POST /analyses/camera/facing/  camera_url, facing      → front(전면) / back(후면) 으로 전환

브라우저가 휴대폰에 직접 요청하지 않고 Django 가 대신 요청합니다.
(허용 목록의 카메라만 제어 · 로그인한 사용자만)
IP Webcam 앱 API:  /settings/ffc?set=on|off  (ffc = front facing camera),  /status.json
"""
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

TIMEOUT = 5


def _camera_base(camera_url: str) -> str:
    """http://192.168.40.149:8080/video → http://192.168.40.149:8080"""
    p = urlsplit(camera_url)
    return f"{p.scheme}://{p.netloc}"


def _current_facing(base: str) -> str:
    curvals = requests.get(f"{base}/status.json", timeout=TIMEOUT).json().get("curvals", {})
    return {"on": "front", "off": "back"}.get(curvals.get("ffc"), "unknown")


@login_required
@require_http_methods(["GET", "POST"])
def camera_facing(request):
    data = request.POST if request.method == "POST" else request.GET
    camera_url = (data.get("camera_url") or "").strip()
    if camera_url not in settings.ALLOWED_CAMERA_URLS:
        return JsonResponse({"error": "허용되지 않은 카메라 주소입니다."}, status=400)
    if not camera_url.startswith(("http://", "https://")):
        return JsonResponse({"error": "IP Webcam 주소에서만 카메라를 전환할 수 있습니다."}, status=400)

    base = _camera_base(camera_url)
    try:
        if request.method == "POST":
            facing = data.get("facing")
            if facing not in ("front", "back"):
                return JsonResponse({"error": "facing 은 front 또는 back 이어야 합니다."}, status=400)
            r = requests.get(f"{base}/settings/ffc", params={"set": "on" if facing == "front" else "off"},
                             timeout=TIMEOUT)
            r.raise_for_status()
        return JsonResponse({"facing": _current_facing(base)})
    except (requests.RequestException, ValueError):
        return JsonResponse({"error": "카메라에 연결할 수 없습니다. 휴대폰 IP Webcam 앱이 켜져 있는지 확인하세요."},
                            status=502)
