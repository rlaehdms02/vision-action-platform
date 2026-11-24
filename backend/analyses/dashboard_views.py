"""
10단계: 관리자 대시보드 (staff 계정만).

/dashboard/       → 화면 (Chart.js 막대 + 도넛 + 최근 작업 표)
/dashboard/data/  → 같은 통계를 JSON 으로 (화면이 10초마다 다시 불러와 자동 갱신)

일반 사용자는 자기 작업만 보지만, 대시보드는 전체 사용자의 작업을 집계합니다.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, F, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .models import AnalysisJob, PersonPrediction

RECENT_LIMIT = 15


def staff_required(view):
    """로그인 안 했으면 로그인 화면으로, 로그인했지만 staff 가 아니면 403."""
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied("관리자만 볼 수 있는 화면입니다.")
        return view(request, *args, **kwargs)
    return wrapper


def build_stats() -> dict:
    jobs = AnalysisJob.objects.all()

    # 상태별 작업 수 (도넛) — Meta.ordering 이 GROUP BY 에 끼지 않도록 order_by() 로 비움
    status_counts = dict(jobs.order_by().values_list("status").annotate(n=Count("id")))
    statuses = [{"key": k, "label": label, "count": status_counts.get(k, 0)}
                for k, label in AnalysisJob.Status.choices]

    # 동작별 예측 수 (막대) — 사람 1명 = 예측 1건
    pred_counts = dict(PersonPrediction.objects.order_by().values_list("action_id").annotate(n=Count("id")))
    actions = [{"key": k, "label": label, "count": pred_counts.pop(k, 0)}
               for k, label in AnalysisJob.Action.choices]
    actions += [{"key": k or "?", "label": k or "알 수 없음", "count": n} for k, n in pred_counts.items()]

    # 요약 숫자
    completed = jobs.filter(status=AnalysisJob.Status.COMPLETED)
    match = PersonPrediction.objects.exclude(job__expected_action="").aggregate(
        total=Count("id"), hit=Count("id", filter=Q(action_id=F("job__expected_action"))))
    summary = {
        "total_jobs": jobs.count(),
        "completed": status_counts.get(AnalysisJob.Status.COMPLETED, 0),
        "failed": status_counts.get(AnalysisJob.Status.FAILED, 0),
        "running": status_counts.get(AnalysisJob.Status.PENDING, 0) + status_counts.get(AnalysisJob.Status.PROCESSING, 0),
        "people": PersonPrediction.objects.count(),
        "users": jobs.order_by().values("user").distinct().count(),
        "avg_sec": round(completed.aggregate(v=Avg("processing_sec"))["v"] or 0, 1),
        "match_total": match["total"],
        "match_rate": round(match["hit"] / match["total"] * 100) if match["total"] else None,
    }

    # 최근 작업 (전체 사용자)
    recent = []
    for j in jobs.select_related("user").prefetch_related("predictions")[:RECENT_LIMIT]:
        preds = list(j.predictions.all())
        top = max(preds, key=lambda p: p.confidence, default=None)
        recent.append({
            "id": j.id,
            "user": j.user.username,
            "title": j.title,
            "input": j.get_input_type_display(),
            "status": j.status,
            "status_display": j.get_status_display(),
            "stage_display": j.get_stage_display() if j.stage else "",
            "people": len(preds),
            "top": f"{top.action_id} {top.action_label}" if top else "",
            "top_conf": round(top.confidence * 100) if top else None,
            "expected": j.expected_action,
            "match": (top.action_id == j.expected_action) if (top and j.expected_action) else None,
            "processing_sec": j.processing_sec,
            "error": j.error_message[:80],
            "created_at": timezone.localtime(j.created_at).strftime("%m/%d %H:%M"),
            "admin_url": reverse("admin:analyses_analysisjob_change", args=[j.id]),
        })

    return {
        "summary": summary,
        "statuses": statuses,
        "actions": actions,
        "recent": recent,
        "updated_at": timezone.localtime().strftime("%H:%M:%S"),
    }


@staff_required
def dashboard(request):
    return render(request, "analyses/dashboard.html", {"stats": build_stats()})


@staff_required
def dashboard_data(request):
    return JsonResponse(build_stats())
