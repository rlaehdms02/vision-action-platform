"""
DRF API: 분석 작업 CRUD + 상태 조회.

POST   /api/v1/analyses/              작업 생성 (PENDING) + Celery 작업 등록 → 작업 ID 즉시 반환
GET    /api/v1/analyses/              내 작업 목록
GET    /api/v1/analyses/{id}/         상세 (사람별 결과 포함)
PATCH  /api/v1/analyses/{id}/         제목·메모 수정
DELETE /api/v1/analyses/{id}/         삭제 (사람별 결과·업로드 영상도 함께 삭제)
GET    /api/v1/analyses/{id}/status/  상태만

조회 범위: 일반 회원은 자기 작업만, 관리자(is_staff)는 전체.
다른 사람 작업은 "없는 작업"처럼 404로 응답 (존재 여부도 숨김).
"""
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AnalysisJob
from .tasks import run_analysis
from .serializers import (
    AnalysisJobCreateSerializer,
    AnalysisJobSerializer,
    AnalysisJobStatusSerializer,
    AnalysisJobUpdateSerializer,
)


logger = logging.getLogger(__name__)


def enqueue_analysis(job_id: int) -> None:
    """DB 저장이 끝난 뒤 호출: Redis 대기열에 작업 등록. Redis 가 꺼져 있으면 FAILED 로 기록."""
    try:
        result = run_analysis.delay(job_id)
        AnalysisJob.objects.filter(pk=job_id, celery_task_id="").update(celery_task_id=result.id)
    except Exception as exc:
        logger.exception("job #%s 작업 등록 실패", job_id)
        AnalysisJob.objects.filter(pk=job_id).update(
            status=AnalysisJob.Status.FAILED, completed_at=timezone.now(),
            error_message=f"작업 대기열(Redis) 연결 실패: {exc}"[:1000],
        )


class AnalysisJobViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]   # PUT(전체 덮어쓰기) 막음

    def get_queryset(self):
        qs = AnalysisJob.objects.select_related("user").prefetch_related("predictions")
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)

    def get_serializer_class(self):
        if self.action == "create":
            return AnalysisJobCreateSerializer
        if self.action == "partial_update":
            return AnalysisJobUpdateSerializer
        if self.action == "status":
            return AnalysisJobStatusSerializer
        return AnalysisJobSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = serializer.save(user=request.user, status=AnalysisJob.Status.PENDING)
        # DB 저장(commit)이 끝난 "뒤에" 작업 등록 → Worker 가 아직 없는 작업을 찾는 일이 없음
        transaction.on_commit(lambda: enqueue_analysis(job.pk))
        job.refresh_from_db()
        return Response(AnalysisJobSerializer(job, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        super().partial_update(request, *args, **kwargs)
        return Response(AnalysisJobSerializer(self.get_object(), context={"request": request}).data)

    def perform_destroy(self, instance):
        if instance.video:
            instance.video.delete(save=False)      # 업로드 영상 파일도 삭제
        instance.delete()                          # PersonPrediction 은 CASCADE 로 함께 삭제

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)
