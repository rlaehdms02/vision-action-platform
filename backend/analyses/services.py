"""
FastAPI AI 서버 호출 (Worker 가 사용).

POST {AI_SERVICE_URL}/api/v1/predict/  (multipart, file=영상)
→ {"predictions":[{track_id, action_id, action_label, confidence, uncertain, valid_frames, ...}],
   "message": "...", "processing_sec": ...}

오류는 모두 AIServiceError 로 바꿔서, tasks.py 가 사용자에게 보여 줄 한글 사유로 저장하게 합니다.
"""
from pathlib import Path

import requests
from django.conf import settings


class AIServiceError(Exception):
    """AI 서버 연결 실패·시간 초과·오류 응답."""


def request_prediction(video_path: str | Path) -> dict:
    url = f"{settings.AI_SERVICE_URL}/api/v1/predict/"
    video_path = Path(video_path)
    if not video_path.exists():
        raise AIServiceError(f"분석할 영상 파일이 없습니다: {video_path.name}")

    try:
        with video_path.open("rb") as f:
            resp = requests.post(
                url,
                files={"file": (video_path.name, f, "video/mp4")},
                timeout=(5, settings.AI_REQUEST_TIMEOUT),      # (연결 5초, 응답 최대 N초)
            )
    except requests.ConnectionError:
        raise AIServiceError(f"AI 서버(FastAPI)에 연결할 수 없습니다: {settings.AI_SERVICE_URL}")
    except requests.Timeout:
        raise AIServiceError(f"AI 분석 시간이 {settings.AI_REQUEST_TIMEOUT:.0f}초를 넘었습니다.")

    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise AIServiceError(f"AI 서버 오류 ({resp.status_code}): {detail}"[:1000])

    data = resp.json()
    if "predictions" not in data:
        raise AIServiceError("AI 서버 응답 형식이 올바르지 않습니다 (predictions 없음).")
    return data
