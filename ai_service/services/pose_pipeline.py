"""
영상 → 사람별(Track ID) 관절 기록.

1) YOLO11n-pose + ByteTrack : 사람 박스와 Track ID
2) 박스를 잘라 MediaPipe heavy : 그 사람의 관절 (학습과 같은 heavy 관절)
3) 33점 → COCO 17점으로 바꿔 frame별로 저장

heavy가 그 사람을 못 잡은 프레임은 "관절 없음"으로 두고 Feature 계산에서 빠집니다.
(학습 때도 heavy가 못 잡은 프레임은 빠졌기 때문)
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from src.heavy_pose import MP_TO_COCO
from src.pose_utils import COCO_KEYPOINT_NAMES

ROOT = Path(__file__).resolve().parents[1]
YOLO_WEIGHTS = ROOT / "models" / "yolo11n-pose.pt"
HEAVY_TASK = ROOT / "models" / "pose_landmarker_heavy.task"
TRACKER = ROOT / "configs" / "bytetrack_live.yaml"


class VideoReadError(Exception):
    """영상을 열 수 없거나 프레임이 없을 때."""


@dataclass
class VideoInfo:
    fps: float
    frames: int
    width: int
    height: int

    @property
    def duration_sec(self) -> float:
        return round(self.frames / self.fps, 2) if self.fps else 0.0


@dataclass
class PoseResult:
    video: VideoInfo
    # track_id → [{"frame_id":…, "pose_detected":1, "<joint>_x_px":…, "<joint>_y_px":…}, …]
    tracks: dict[int, list[dict]] = field(default_factory=dict)
    heavy_ok: int = 0
    heavy_miss: int = 0


def _make_landmarker():
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision

    opts = vision.PoseLandmarkerOptions(
        base_options=mpt.BaseOptions(model_asset_path=str(HEAVY_TASK)),
        running_mode=vision.RunningMode.IMAGE,      # 사람마다 잘라서 한 장씩
        num_poses=1,
        min_pose_detection_confidence=0.3,
        min_pose_presence_confidence=0.3,
    )
    return vision.PoseLandmarker.create_from_options(opts)


def _heavy_keypoints(landmarker, frame, box, pad: float = 0.15):
    """박스 영역을 잘라 heavy로 관절을 뽑고, 원본 좌표 (17,2)로 돌려줌. 실패 시 None."""
    import mediapipe as mp

    H, W = frame.shape[:2]
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    cx1, cy1 = int(max(0, x1 - bw * pad)), int(max(0, y1 - bh * pad))
    cx2, cy2 = int(min(W, x2 + bw * pad)), int(min(H, y2 + bh * pad))
    crop = frame[cy1:cy2, cx1:cx2]
    if crop.size == 0:
        return None
    image = mp.Image(image_format=mp.ImageFormat.SRGB,
                     data=cv2.cvtColor(np.ascontiguousarray(crop), cv2.COLOR_BGR2RGB))
    res = landmarker.detect(image)
    if not res.pose_landmarks:
        return None
    pts = res.pose_landmarks[0]
    cw, ch = cx2 - cx1, cy2 - cy1
    return np.asarray([[cx1 + pts[i].x * cw, cy1 + pts[i].y * ch] for i in MP_TO_COCO], dtype=np.float32)


def extract_tracks(video_path: str | Path, frame_stride: int = 1, max_people: int = 5) -> PoseResult:
    from ultralytics import YOLO

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise VideoReadError("영상을 열 수 없습니다. 손상되었거나 지원하지 않는 형식입니다.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # 요청마다 새로 만들어 Track ID가 이전 영상과 섞이지 않게 함
    yolo = YOLO(str(YOLO_WEIGHTS))
    tracker = str(TRACKER) if TRACKER.exists() else "bytetrack.yaml"
    tracks: dict[int, list[dict]] = defaultdict(list)
    heavy_ok = heavy_miss = 0
    frame_id = 0

    with _make_landmarker() as landmarker:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_id % frame_stride == 0:
                r = yolo.track(frame, persist=True, tracker=tracker, conf=0.25, verbose=False)[0]
                if r.boxes is not None and r.boxes.id is not None and len(r.boxes):
                    ids = r.boxes.id.int().cpu().tolist()[:max_people]
                    boxes = r.boxes.xyxy.cpu().numpy()[:max_people]
                    for tid, box in zip(ids, boxes):
                        kp = _heavy_keypoints(landmarker, frame, box)
                        row = {"frame_id": frame_id, "pose_detected": 0}
                        if kp is not None:
                            row["pose_detected"] = 1
                            for name, (x, y) in zip(COCO_KEYPOINT_NAMES, kp):
                                row[f"{name}_x_px"] = float(x)
                                row[f"{name}_y_px"] = float(y)
                            heavy_ok += 1
                        else:
                            heavy_miss += 1
                        tracks[int(tid)].append(row)
            frame_id += 1
    cap.release()

    if frame_id == 0:
        raise VideoReadError("영상에서 프레임을 하나도 읽지 못했습니다.")

    return PoseResult(
        video=VideoInfo(fps=float(fps), frames=frame_id, width=width, height=height),
        tracks=dict(tracks),
        heavy_ok=heavy_ok,
        heavy_miss=heavy_miss,
    )
