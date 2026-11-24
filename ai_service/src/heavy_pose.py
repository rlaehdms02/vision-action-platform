"""
MediaPipe Pose heavy를 Ultralytics YOLO Pose 결과처럼 쓰게 해 주는 어댑터.

scripts/heavy/42, 44 는 `from src.heavy_pose import HeavyPose as YOLO` 로 바꿔서
기존 코드(realtime_utils.frame_feature_from_pose, result.plot())를 그대로 사용합니다.

- 33개 MediaPipe 관절 → COCO 17개 순서로 변환
- result.boxes.conf / result.keypoints.xy 는 .detach().cpu().numpy() 호출이 가능
- result.plot() 은 COCO 17 스켈레톤을 그린 이미지를 반환
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / "models" / "pose_landmarker_heavy.task"

# MediaPipe 33점 → COCO 17점 (src/pose_utils.COCO_KEYPOINT_NAMES 순서)
MP_TO_COCO = [0, 2, 5, 7, 8, 11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]

COCO_SKELETON = [
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12), (11, 12),
    (11, 13), (13, 15), (12, 14), (14, 16), (0, 1), (0, 2), (1, 3), (2, 4),
]
LEFT_IDS = {1, 3, 5, 7, 9, 11, 13, 15}


class _Arr:
    """torch Tensor처럼 .detach().cpu().numpy() 를 지원하는 얇은 래퍼."""

    def __init__(self, array):
        self._a = np.asarray(array, dtype=np.float32)

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self._a

    def __len__(self):
        return len(self._a)

    def __getitem__(self, idx):
        return _Arr(self._a[idx])


class _Boxes:
    def __init__(self, xyxy, conf):
        self.xyxy = _Arr(xyxy.reshape(-1, 4))
        self.conf = _Arr(conf.reshape(-1))
        self.id = None

    def __len__(self):
        return len(self.conf)


class _Keypoints:
    def __init__(self, xy, conf):
        self.xy = _Arr(xy.reshape(-1, 17, 2))
        self.conf = _Arr(conf.reshape(-1, 17))


class HeavyResult:
    def __init__(self, frame, xy, conf):
        self.orig_img = frame
        n = len(xy)
        if n:
            boxes = np.stack([
                [p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()] for p in xy
            ])
            box_conf = conf.mean(axis=1)
        else:
            boxes = np.zeros((0, 4), np.float32)
            box_conf = np.zeros((0,), np.float32)
        self.boxes = _Boxes(boxes, box_conf)
        self.keypoints = _Keypoints(
            xy if n else np.zeros((0, 17, 2), np.float32),
            conf if n else np.zeros((0, 17), np.float32),
        )

    def plot(self):
        img = self.orig_img.copy()
        xy = self.keypoints.xy.numpy()
        for pts in xy:
            p = pts.astype(int)
            for a, b in COCO_SKELETON:
                cv2.line(img, tuple(p[a]), tuple(p[b]), (0, 255, 0), 3)
            for i, (x, y) in enumerate(p):
                color = (0, 255, 255) if i in LEFT_IDS else (255, 0, 255)
                cv2.circle(img, (int(x), int(y)), 5, color, -1)
        for x1, y1, x2, y2 in self.boxes.xyxy.numpy().astype(int):
            cv2.rectangle(img, (x1, y1), (x2, y2), (255, 128, 0), 2)
        cv2.putText(img, "MediaPipe heavy", (img.shape[1] - 260, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        return img


class HeavyPose:
    """YOLO(...) 자리에 넣어 쓰는 MediaPipe heavy Pose. 인자로 받은 YOLO 모델명은 무시합니다."""

    def __init__(self, *_, model_path: str | Path | None = None,
                 num_poses: int = 1, min_conf: float = 0.3, **__):
        import mediapipe as mp
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision

        path = Path(model_path) if model_path else DEFAULT_MODEL
        if not path.exists():
            raise FileNotFoundError(f"heavy 모델이 없습니다: {path}")
        self._mp = mp
        opts = vision.PoseLandmarkerOptions(
            base_options=mpt.BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=num_poses,
            min_pose_detection_confidence=min_conf,
            min_pose_presence_confidence=min_conf,
            min_tracking_confidence=min_conf,
        )
        self._lm = vision.PoseLandmarker.create_from_options(opts)
        self._last_ts = -1

    def _timestamp(self) -> int:
        # VIDEO 모드는 timestamp가 반드시 증가해야 함
        ts = int(time.monotonic() * 1000)
        if ts <= self._last_ts:
            ts = self._last_ts + 1
        self._last_ts = ts
        return ts

    def predict(self, source, **_):
        frame = source
        h, w = frame.shape[:2]
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                               data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        res = self._lm.detect_for_video(image, self._timestamp())
        xy, conf = [], []
        for person in res.pose_landmarks or []:
            xy.append([[person[i].x * w, person[i].y * h] for i in MP_TO_COCO])
            conf.append([float(getattr(person[i], "visibility", 1.0) or 0.0) for i in MP_TO_COCO])
        xy = np.asarray(xy, np.float32).reshape(-1, 17, 2)
        conf = np.asarray(conf, np.float32).reshape(-1, 17)
        return [HeavyResult(frame, xy, conf)]

    __call__ = predict

    def close(self):
        self._lm.close()


class HeavyTrackYOLO:
    """
    8일차(46~48)용: 사람 박스·Track ID는 YOLO + ByteTrack이 만들고,
    각 사람 박스 안의 관절만 MediaPipe heavy로 다시 추출해 바꿔 넣습니다.
    (MediaPipe에는 사람별 ID 추적 기능이 없기 때문)

    heavy가 그 사람을 못 잡으면 YOLO 관절을 그대로 둡니다. → fallback_count 로 확인
    """

    def __init__(self, model_name="yolo11n-pose.pt", *_, model_path=None, min_conf: float = 0.3, **__):
        import mediapipe as mp
        from mediapipe.tasks import python as mpt
        from mediapipe.tasks.python import vision
        from ultralytics import YOLO as _UltraYOLO

        path = Path(model_path) if model_path else DEFAULT_MODEL
        if not path.exists():
            raise FileNotFoundError(f"heavy 모델이 없습니다: {path}")
        self._yolo = _UltraYOLO(model_name)
        self._mp = mp
        opts = vision.PoseLandmarkerOptions(
            base_options=mpt.BaseOptions(model_asset_path=str(path)),
            running_mode=vision.RunningMode.IMAGE,   # 사람마다 잘라서 한 장씩 처리
            num_poses=1,
            min_pose_detection_confidence=min_conf,
            min_pose_presence_confidence=min_conf,
        )
        self._lm = vision.PoseLandmarker.create_from_options(opts)
        self.heavy_count = 0
        self.fallback_count = 0

    def __getattr__(self, name):
        return getattr(self._yolo, name)

    def _refine(self, result, pad: float = 0.15):
        if result.boxes is None or result.keypoints is None or len(result.boxes) == 0:
            return result
        img = result.orig_img
        H, W = img.shape[:2]
        data = result.keypoints.data.clone()
        for i, (x1, y1, x2, y2) in enumerate(result.boxes.xyxy.detach().cpu().numpy()):
            bw, bh = x2 - x1, y2 - y1
            cx1, cy1 = int(max(0, x1 - bw * pad)), int(max(0, y1 - bh * pad))
            cx2, cy2 = int(min(W, x2 + bw * pad)), int(min(H, y2 + bh * pad))
            crop = img[cy1:cy2, cx1:cx2]
            if crop.size == 0:
                self.fallback_count += 1
                continue
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                                   data=cv2.cvtColor(np.ascontiguousarray(crop), cv2.COLOR_BGR2RGB))
            res = self._lm.detect(image)
            if not res.pose_landmarks:
                self.fallback_count += 1
                continue
            pts = res.pose_landmarks[0]
            cw, ch = cx2 - cx1, cy2 - cy1
            for j, idx in enumerate(MP_TO_COCO):
                data[i, j, 0] = cx1 + pts[idx].x * cw
                data[i, j, 1] = cy1 + pts[idx].y * ch
                if data.shape[-1] > 2:
                    data[i, j, 2] = float(getattr(pts[idx], "visibility", 1.0) or 0.0)
            self.heavy_count += 1
        result.keypoints.data = data
        return result

    def track(self, *args, **kwargs):
        return [self._refine(r) for r in self._yolo.track(*args, **kwargs)]

    def predict(self, *args, **kwargs):
        return [self._refine(r) for r in self._yolo.predict(*args, **kwargs)]

    __call__ = predict
