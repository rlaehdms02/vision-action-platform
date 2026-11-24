"""
FastAPI AI 추론 서버 (2단계).

실행: uvicorn main:app --host 0.0.0.0 --port 8001 --reload
문서: http://localhost:8001/docs
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))          # src/, services/, routers/ import 용

from routers.predictions import router as predictions_router  # noqa: E402
from services.model_loader import load_model_bundle  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서버 시작 시 1번만 모델 로드 → 모든 요청에서 재사용
    app.state.bundle = load_model_bundle()
    print(f"[model] classes={app.state.bundle.classes}, features={app.state.bundle.feature_count}")
    yield


app = FastAPI(title="Vision Action AI Service", version="0.2.0", lifespan=lifespan)
app.include_router(predictions_router)


@app.get("/health", tags=["health"])
def health():
    b = getattr(app.state, "bundle", None)
    return {
        "status": "ok",
        "model_loaded": b is not None,
        "classes": b.classes if b else [],
        "feature_count": b.feature_count if b else 0,
        "sequence_steps": b.sequence_steps if b else 0,
        "heavy_task": (ROOT / "models" / "pose_landmarker_heavy.task").exists(),
        "yolo_weights": (ROOT / "models" / "yolo11n-pose.pt").exists(),
    }
