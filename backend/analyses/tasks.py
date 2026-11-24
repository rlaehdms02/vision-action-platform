"""
Celery 작업 (Worker 에서 실행).

  PENDING → PROCESSING ─┬─ (IP Webcam) stage=CAPTURING: 카메라에서 N초 수집 → mp4 저장
                        └─ stage=ANALYZING: FastAPI 추론 → PersonPrediction 저장
          → COMPLETED (사람별 결과)  /  FAILED (카메라·영상·FastAPI 오류 + 사유)

영상 업로드와 IP Webcam 은 "영상 파일 확보" 방법만 다르고, 분석·저장은 같은 경로를 사용합니다.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .camera_capture import CameraError, capture_clip
from .models import AnalysisJob, PersonPrediction
from .services import AIServiceError, request_prediction

logger = logging.getLogger(__name__)


def _set_stage(job: AnalysisJob, stage: str) -> None:
    job.stage = stage
    AnalysisJob.objects.filter(pk=job.pk).update(stage=stage)


def _get_video_path(job: AnalysisJob) -> tuple[str, str]:
    """반환: (영상 경로, 안내 메시지)."""
    if job.input_type == AnalysisJob.InputType.UPLOAD:
        if not job.video:
            raise AIServiceError("업로드된 영상이 없습니다.")
        return job.video.path, ""

    # IP Webcam: 카메라에서 정해진 시간만큼 녹화 → media/captures/ 에 저장 → job.video 로 연결
    _set_stage(job, AnalysisJob.Stage.CAPTURING)
    seconds = settings.CAMERA_CAPTURE_SECONDS
    rel = f"captures/{timezone.localtime():%Y/%m/%d}/job_{job.pk}.mp4"
    logger.info("job #%s 카메라 수집 시작 (%ss): %s", job.pk, seconds, job.camera_url)
    result = capture_clip(job.camera_url, seconds, settings.MEDIA_ROOT / rel, rotation=job.rotation)
    job.video.name = rel
    job.save(update_fields=["video"])
    logger.info("job #%s %s", job.pk, result.summary)
    return str(result.path), result.summary


@shared_task(bind=True)
def run_analysis(self, job_id: int):
    # 1) 대기 중인 작업만 가져가서 "처리 중"으로 바꿈 (같은 작업을 두 번 처리하지 않게)
    started = timezone.now()
    updated = AnalysisJob.objects.filter(pk=job_id, status=AnalysisJob.Status.PENDING).update(
        status=AnalysisJob.Status.PROCESSING, started_at=started, celery_task_id=self.request.id or "",
    )
    if not updated:
        logger.warning("job #%s: 대기 상태가 아니거나 없는 작업이라 건너뜀", job_id)
        return {"job_id": job_id, "skipped": True}

    job = AnalysisJob.objects.get(pk=job_id)
    logger.info("job #%s 처리 시작 (%s)", job_id, job.get_input_type_display())

    try:
        # 2) 영상 확보 (업로드 파일 또는 카메라 수집)
        video_path, capture_note = _get_video_path(job)

        # 3) FastAPI 추론
        _set_stage(job, AnalysisJob.Stage.ANALYZING)
        result = request_prediction(video_path)
        preds = result.get("predictions", [])

        # 4) 결과 저장: 사람별 예측 + 작업 완료 (한 번에 저장, 중간에 실패하면 둘 다 취소)
        done = timezone.now()
        message = str(result.get("message", ""))
        if capture_note:
            message = f"{message} ({capture_note})"
        with transaction.atomic():
            job.predictions.all().delete()
            PersonPrediction.objects.bulk_create([
                PersonPrediction(
                    job=job,
                    track_id=p["track_id"],
                    action_id=p.get("action_id", ""),
                    action_label=p["action_label"],
                    confidence=p["confidence"],
                    uncertain=p.get("uncertain", False),
                    valid_frames=p.get("valid_frames", 0),
                )
                for p in preds
            ])
            job.status = AnalysisJob.Status.COMPLETED
            job.stage = AnalysisJob.Stage.NONE
            job.completed_at = done
            job.processing_sec = round((done - started).total_seconds(), 2)
            job.error_message = ""
            job.result_message = message[:255]
            job.save(update_fields=["status", "stage", "completed_at", "processing_sec",
                                    "error_message", "result_message"])

        logger.info("job #%s 완료: %d명, %.1fs, %s", job_id, len(preds), job.processing_sec, job.result_message)
        return {"job_id": job_id, "status": job.status, "people": len(preds)}

    except Exception as exc:                                   # 어떤 오류든 FAILED + 사유 기록
        kind = "카메라" if isinstance(exc, CameraError) else "분석"
        logger.error("job #%s 실패(%s): %s", job_id, kind, exc)
        AnalysisJob.objects.filter(pk=job_id).update(
            status=AnalysisJob.Status.FAILED, stage=AnalysisJob.Stage.NONE,
            completed_at=timezone.now(), error_message=str(exc)[:1000],
        )
        return {"job_id": job_id, "status": AnalysisJob.Status.FAILED, "error": str(exc)}
