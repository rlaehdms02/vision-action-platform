from django.contrib import admin

from .models import AnalysisJob, PersonPrediction


class PersonPredictionInline(admin.TabularInline):
    """분석 작업 화면 아래에 사람별 예측을 표로 함께 보여 줌."""
    model = PersonPrediction
    extra = 0
    fields = ("track_id", "action_id", "action_label", "confidence", "uncertain", "valid_frames")


@admin.register(AnalysisJob)
class AnalysisJobAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "input_type", "status", "expected_action",
                    "prediction_count", "processing_sec", "created_at")
    list_filter = ("status", "input_type", "expected_action", "created_at")
    search_fields = ("user__username", "title", "memo", "celery_task_id")
    readonly_fields = ("created_at", "started_at", "completed_at", "processing_sec", "result_message", "error_message")
    inlines = [PersonPredictionInline]
    date_hierarchy = "created_at"

    @admin.display(description="예측 수")
    def prediction_count(self, obj):
        return obj.predictions.count()


@admin.register(PersonPrediction)
class PersonPredictionAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "track_id", "action_id", "action_label", "confidence", "uncertain", "created_at")
    list_filter = ("action_label", "uncertain")
    search_fields = ("job__user__username", "action_label")
