"""
DRF Serializer: 들어오는 입력을 검사하고, 나가는 JSON 모양을 정합니다.

- AnalysisJobCreateSerializer : 작업 생성 (영상 업로드 / IP Webcam 입력 검사)
- AnalysisJobSerializer       : 목록·상세 조회 (사람별 결과 포함)
- AnalysisJobUpdateSerializer : 수정은 제목·메모만 허용
- AnalysisJobStatusSerializer : 상태만 가볍게 조회
"""
from pathlib import Path

from django.conf import settings
from rest_framework import serializers

from .models import AnalysisJob, PersonPrediction


class PersonPredictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonPrediction
        fields = ["track_id", "action_id", "action_label", "confidence", "uncertain", "valid_frames"]
        read_only_fields = fields


class AnalysisJobSerializer(serializers.ModelSerializer):
    """조회용: 사용자는 이 응답의 어떤 값도 직접 바꿀 수 없음."""
    user = serializers.CharField(source="user.username", read_only=True)
    input_type_display = serializers.CharField(source="get_input_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    expected_action_display = serializers.CharField(source="get_expected_action_display", read_only=True)
    predictions = PersonPredictionSerializer(many=True, read_only=True)

    class Meta:
        model = AnalysisJob
        fields = [
            "id", "user", "title", "memo",
            "input_type", "input_type_display", "video", "camera_url", "rotation",
            "expected_action", "expected_action_display",
            "status", "status_display", "stage", "celery_task_id", "error_message", "result_message", "processing_sec",
            "created_at", "started_at", "completed_at",
            "predictions",
        ]
        read_only_fields = fields


class AnalysisJobCreateSerializer(serializers.ModelSerializer):
    """생성용: 입력 방식에 맞는 값만 받음. 상태·결과는 서버가 정함."""

    class Meta:
        model = AnalysisJob
        fields = ["id", "title", "memo", "input_type", "video", "camera_url", "rotation", "expected_action"]
        read_only_fields = ["id"]

    def validate_video(self, video):
        if video is None:
            return video
        ext = Path(video.name).suffix.lower()
        if ext not in settings.ALLOWED_VIDEO_EXTENSIONS:
            raise serializers.ValidationError(
                f"지원하지 않는 영상 형식입니다: '{ext or '없음'}'. 허용: {settings.ALLOWED_VIDEO_EXTENSIONS}")
        if video.size == 0:
            raise serializers.ValidationError("빈 파일입니다.")
        if video.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise serializers.ValidationError(f"파일이 너무 큽니다. 최대 {settings.MAX_UPLOAD_MB}MB")
        return video

    def validate(self, attrs):
        input_type = attrs.get("input_type")
        video = attrs.get("video")
        camera_url = (attrs.get("camera_url") or "").strip()

        if input_type == AnalysisJob.InputType.UPLOAD:
            if not video:
                raise serializers.ValidationError({"video": "영상 업로드 방식은 영상 파일이 필요합니다."})
            if camera_url:
                raise serializers.ValidationError({"camera_url": "영상 업로드 방식에서는 카메라 주소를 넣지 않습니다."})
            attrs["rotation"] = 0                      # 회전은 IP Webcam 에만 적용
        elif input_type == AnalysisJob.InputType.IP_WEBCAM:
            if video:
                raise serializers.ValidationError({"video": "IP Webcam 방식에서는 영상 파일을 넣지 않습니다."})
            if not camera_url:
                raise serializers.ValidationError({"camera_url": "IP Webcam 방식은 카메라 주소가 필요합니다."})
            if camera_url not in settings.ALLOWED_CAMERA_URLS:
                raise serializers.ValidationError({"camera_url": "허용되지 않은 카메라 주소입니다."})
            attrs["camera_url"] = camera_url
        return attrs


class AnalysisJobUpdateSerializer(serializers.ModelSerializer):
    """수정용: 제목·메모만. status·예측 결과 등을 보내면 거부."""

    class Meta:
        model = AnalysisJob
        fields = ["title", "memo"]

    def validate(self, attrs):
        extra = set(self.initial_data) - set(self.fields)
        if extra:
            raise serializers.ValidationError(f"수정할 수 없는 항목입니다: {sorted(extra)} (제목·메모만 수정 가능)")
        return attrs


class AnalysisJobStatusSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_finished = serializers.SerializerMethodField()
    prediction_count = serializers.IntegerField(source="predictions.count", read_only=True)

    class Meta:
        model = AnalysisJob
        fields = ["id", "status", "status_display", "stage", "is_finished", "error_message", "result_message",
                  "prediction_count", "started_at", "completed_at"]
        read_only_fields = fields

    def get_is_finished(self, obj):
        return obj.status in (AnalysisJob.Status.COMPLETED, AnalysisJob.Status.FAILED)
