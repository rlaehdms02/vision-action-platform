"""
분석 DB 모델 2개.

auth_user (Django 기본)
   │ 1 : N
AnalysisJob        ← 분석 요청 1건 (누가, 어떤 입력으로, 지금 상태는?)
   │ 1 : N
PersonPrediction   ← 그 영상 속 사람 1명의 예측 결과 (Track ID, 동작, 신뢰도)
"""
from django.conf import settings
from django.db import models


class AnalysisJob(models.Model):
    class InputType(models.TextChoices):
        UPLOAD = "UPLOAD", "영상 업로드"
        IP_WEBCAM = "IP_WEBCAM", "IP Webcam"

    class Status(models.TextChoices):
        PENDING = "PENDING", "대기"
        PROCESSING = "PROCESSING", "처리 중"
        COMPLETED = "COMPLETED", "완료"
        FAILED = "FAILED", "실패"

    class Action(models.TextChoices):           # 사용자가 고르는 "예상 동작" (선택)
        A001 = "A001", "A001 앉아서 다리 앞으로 뻗기"
        A002 = "A002", "A002 팔 위아래로 뻗기"
        A006 = "A006", "A006 옆으로 누워 다리 들기"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="analysis_jobs", verbose_name="요청 사용자")
    title = models.CharField("제목", max_length=100, blank=True)
    memo = models.TextField("메모", blank=True)

    input_type = models.CharField("입력 방식", max_length=20, choices=InputType.choices)
    video = models.FileField("영상 파일", upload_to="uploads/%Y/%m/%d/", blank=True)
    camera_url = models.CharField("카메라 주소", max_length=255, blank=True)

    class Rotation(models.IntegerChoices):     # IP Webcam 영상 회전 (휴대폰을 세로로 세웠을 때)
        R0 = 0, "회전 없음"
        R90 = 90, "시계 방향 90°"
        R180 = 180, "180°"
        R270 = 270, "반시계 방향 90°"

    rotation = models.PositiveSmallIntegerField("카메라 회전", choices=Rotation.choices, default=0)
    expected_action = models.CharField("예상 동작", max_length=10, choices=Action.choices, blank=True)

    class Stage(models.TextChoices):            # 처리 중일 때 세부 단계 (화면 안내용)
        NONE = "", "-"
        CAPTURING = "CAPTURING", "영상 수집"
        ANALYZING = "ANALYZING", "AI 분석"

    status = models.CharField("상태", max_length=20, choices=Status.choices,
                              default=Status.PENDING, db_index=True)
    stage = models.CharField("세부 단계", max_length=20, choices=Stage.choices, blank=True, default="")
    celery_task_id = models.CharField("Celery 작업 ID", max_length=255, blank=True)
    error_message = models.TextField("오류 내용", blank=True)
    result_message = models.CharField("결과 메시지", max_length=255, blank=True)   # 예: "영상에서 사람을 찾지 못했습니다."
    processing_sec = models.FloatField("처리 시간(초)", null=True, blank=True)

    created_at = models.DateTimeField("생성 시각", auto_now_add=True)
    started_at = models.DateTimeField("시작 시각", null=True, blank=True)
    completed_at = models.DateTimeField("완료 시각", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "분석 작업"
        verbose_name_plural = "분석 작업"

    def __str__(self):
        return f"#{self.pk} {self.get_input_type_display()} {self.get_status_display()} ({self.user})"


class PersonPrediction(models.Model):
    job = models.ForeignKey(AnalysisJob, on_delete=models.CASCADE,
                            related_name="predictions", verbose_name="분석 작업")
    track_id = models.PositiveIntegerField("Track ID")          # 이 영상 안에서만 쓰는 사람 번호
    action_id = models.CharField("동작 ID", max_length=10)       # A001 / A002 / A006
    action_label = models.CharField("예측 동작", max_length=50)
    confidence = models.FloatField("신뢰도")
    uncertain = models.BooleanField("판단 불확실", default=False)
    valid_frames = models.PositiveIntegerField("유효 프레임 수", default=0)
    created_at = models.DateTimeField("저장 시각", auto_now_add=True)

    class Meta:
        ordering = ["job", "track_id"]
        constraints = [
            models.UniqueConstraint(fields=["job", "track_id"], name="unique_track_per_job"),
        ]
        verbose_name = "사람별 예측"
        verbose_name_plural = "사람별 예측"

    def __str__(self):
        return f"job#{self.job_id} track{self.track_id} {self.action_label} ({self.confidence:.2f})"
