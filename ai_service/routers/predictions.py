"""
POST /api/v1/predict/ : 영상 파일 하나를 받아 사람별 동작을 JSON으로 돌려줍니다.

- 잘못된 확장자 / 빈 파일 / 너무 큰 파일 / 읽을 수 없는 영상 → 4xx 오류와 사유
- 영상은 정상인데 사람이 없음 → 200, predictions=[] 와 message
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool

from services.action_inference import predict_tracks
from services.pose_pipeline import VideoReadError, extract_tracks

router = APIRouter(prefix="/api/v1", tags=["predict"])

ALLOWED_EXT = {".mp4", ".mov", ".avi", ".mkv"}
MAX_MB = float(os.getenv("MAX_UPLOAD_MB", "200"))
UNCERTAIN_THRESHOLD = float(os.getenv("UNCERTAIN_THRESHOLD", "0.5"))
FRAME_STRIDE = int(os.getenv("FRAME_STRIDE", "1"))
MAX_PEOPLE = int(os.getenv("MAX_PEOPLE", "5"))


@router.post("/predict/")
async def predict_video(request: Request, file: UploadFile = File(..., description="분석할 영상 (mp4 등)")):
    bundle = request.app.state.bundle
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"지원하지 않는 형식입니다: '{ext or '없음'}'. 허용: {sorted(ALLOWED_EXT)}")

    tmp_dir = tempfile.mkdtemp(prefix="predict_")
    tmp_path = Path(tmp_dir) / f"input{ext}"
    try:
        with tmp_path.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        size_mb = tmp_path.stat().st_size / 1024 / 1024
        if size_mb == 0:
            raise HTTPException(400, "빈 파일입니다.")
        if size_mb > MAX_MB:
            raise HTTPException(413, f"파일이 너무 큽니다: {size_mb:.1f}MB (최대 {MAX_MB:.0f}MB)")

        t0 = time.perf_counter()
        try:
            # 무거운 추론은 별도 스레드에서 (서버가 멈추지 않게)
            pose = await run_in_threadpool(extract_tracks, tmp_path, FRAME_STRIDE, MAX_PEOPLE)
        except VideoReadError as e:
            raise HTTPException(400, str(e))

        if pose.video.frames < bundle.min_valid_frames:
            raise HTTPException(422, f"영상이 너무 짧습니다: {pose.video.frames} frames "
                                     f"(최소 {bundle.min_valid_frames} frames 필요)")

        predictions, skipped = predict_tracks(pose.tracks, bundle, UNCERTAIN_THRESHOLD)
        elapsed = round(time.perf_counter() - t0, 2)

        if not pose.tracks:
            message = "영상에서 사람을 찾지 못했습니다."
        elif not predictions:
            message = "사람은 찾았지만 관절이 잡힌 프레임이 부족해 동작을 예측하지 못했습니다."
        else:
            message = f"{len(predictions)}명의 동작을 예측했습니다."

        return {
            "filename": file.filename,
            "video": {"fps": round(pose.video.fps, 2), "frames": pose.video.frames,
                      "width": pose.video.width, "height": pose.video.height,
                      "duration_sec": pose.video.duration_sec},
            "model": {"name": "rf_action_team", "pose": "yolo11n+bytetrack / mediapipe heavy",
                      "classes": bundle.classes},
            "people_detected": len(pose.tracks),
            "predictions": predictions,
            "skipped_tracks": skipped,
            "heavy": {"ok": pose.heavy_ok, "miss": pose.heavy_miss},
            "processing_sec": elapsed,
            "message": message,
        }
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
