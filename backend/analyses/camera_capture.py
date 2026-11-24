"""
IP Webcam 에서 정해진 시간만큼 프레임을 모아 mp4 로 저장합니다. (Worker 에서 실행)

- 허용 목록(settings.ALLOWED_CAMERA_URLS)에 있는 주소만 접속
- 연결 실패 / 중간에 끊김 / 프레임 부족 → CameraError (한글 사유)
- 중간에 끊겨도 이미 충분히 모였으면(CAMERA_MIN_FRAMES 이상) 그만큼으로 분석 진행
- rotation(0/90/180/270): 휴대폰을 세로로 세워도 사람이 똑바로 서 있게 프레임을 돌려서 저장
"""
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
from django.conf import settings


ROTATE_CODES = {                       # 화면의 회전 버튼과 같은 방향 (CSS rotate 는 시계 방향)
    90: cv2.ROTATE_90_CLOCKWISE,
    180: cv2.ROTATE_180,
    270: cv2.ROTATE_90_COUNTERCLOCKWISE,
}


class CameraError(Exception):
    """카메라 연결·수집 실패."""


@dataclass
class CaptureResult:
    path: Path
    frames: int
    seconds: float
    fps: float
    interrupted: bool          # 정해진 시간 전에 끊겼는지
    rotation: int = 0

    @property
    def summary(self) -> str:
        s = f"IP Webcam {self.seconds:.1f}초 수집 ({self.frames} frames, {self.fps:.1f} fps)"
        if self.rotation:
            s += f" · 회전 {self.rotation}°"
        return s + " · 수집 중 연결이 끊겨 모인 구간만 분석" if self.interrupted else s


def capture_clip(camera_url: str, seconds: float, out_path: Path, rotation: int = 0) -> CaptureResult:
    if camera_url not in settings.ALLOWED_CAMERA_URLS:          # Worker 에서도 한 번 더 확인
        raise CameraError("허용되지 않은 카메라 주소입니다.")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(camera_url, cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(settings.CAMERA_OPEN_TIMEOUT * 1000),
        cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(settings.CAMERA_READ_TIMEOUT * 1000),
    ])
    if not cap.isOpened():
        raise CameraError(f"카메라에 연결할 수 없습니다. 휴대폰 IP Webcam 앱이 켜져 있고 같은 와이파이인지 확인하세요: {camera_url}")

    writer = None
    frames = 0
    interrupted = False
    start = time.monotonic()
    last_ok = start
    nominal_fps = cap.get(cv2.CAP_PROP_FPS) or 0
    if not (1 <= nominal_fps <= 60):
        nominal_fps = 15.0

    try:
        while time.monotonic() - start < seconds:
            ok, frame = cap.read()
            now = time.monotonic()
            if not ok or frame is None:
                if now - last_ok > settings.CAMERA_READ_TIMEOUT:
                    interrupted = True
                    break
                time.sleep(0.05)
                continue
            last_ok = now

            if rotation in ROTATE_CODES:                       # 회전 먼저 → 그 다음 크기 조절
                frame = cv2.rotate(frame, ROTATE_CODES[rotation])
            h, w = frame.shape[:2]
            if w > settings.CAMERA_MAX_WIDTH:                    # 너무 큰 영상은 줄여서 저장
                scale = settings.CAMERA_MAX_WIDTH / w
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
            if writer is None:
                h, w = frame.shape[:2]
                writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), nominal_fps, (w, h))
            writer.write(frame)
            frames += 1
    finally:
        cap.release()
        if writer is not None:
            writer.release()

    elapsed = time.monotonic() - start
    if frames < settings.CAMERA_MIN_FRAMES:
        out_path.unlink(missing_ok=True)
        reason = "카메라 연결이 끊겼습니다" if interrupted else "수집된 프레임이 부족합니다"
        raise CameraError(f"{reason} ({frames} frames, 최소 {settings.CAMERA_MIN_FRAMES} frames 필요)")

    return CaptureResult(path=out_path, frames=frames, seconds=elapsed,
                         fps=frames / elapsed if elapsed else 0.0, interrupted=interrupted,
                         rotation=rotation if rotation in ROTATE_CODES else 0)
