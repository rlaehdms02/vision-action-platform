"""
사람별 관절 기록 → 30 Step × 38 = 1,140 Feature → Random Forest → 동작·신뢰도.

학습(team_train_mediapipe.py)과 똑같이
  build_frame_feature_matrix → resample_sequence(30) → flatten_sequence
를 사용하므로 Feature 순서가 그대로 유지됩니다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from services.model_loader import ModelBundle
from src.sequence_utils import build_frame_feature_matrix, flatten_sequence, resample_sequence


def predict_tracks(tracks: dict[int, list[dict]], bundle: ModelBundle,
                   uncertain_threshold: float = 0.5) -> tuple[list[dict], list[dict]]:
    """반환: (predictions, skipped). skipped 는 유효 프레임이 부족해 예측하지 않은 Track."""
    predictions, skipped = [], []

    for tid in sorted(tracks):
        rows = tracks[tid]
        matrix, frame_ids = build_frame_feature_matrix(pd.DataFrame(rows))
        if len(matrix) < bundle.min_valid_frames:
            skipped.append({"track_id": tid, "valid_frames": int(len(matrix)),
                            "reason": f"유효 프레임 {len(matrix)}개 < 최소 {bundle.min_valid_frames}개"})
            continue

        seq = resample_sequence(matrix, frame_ids, target_steps=bundle.sequence_steps)
        x = pd.DataFrame([flatten_sequence(seq)], columns=bundle.columns).to_numpy(float)
        proba = bundle.model.predict_proba(x)[0]
        best = int(np.argmax(proba))
        label = bundle.classes[best]
        conf = float(proba[best])

        predictions.append({
            "track_id": int(tid),
            "action_id": bundle.action_ids.get(label, ""),
            "action_label": label,
            "confidence": round(conf, 4),
            "uncertain": conf < uncertain_threshold,
            "valid_frames": int(len(matrix)),
            "first_frame": int(frame_ids[0]),
            "last_frame": int(frame_ids[-1]),
            "probabilities": {c: round(float(p), 4) for c, p in zip(bundle.classes, proba)},
        })

    return predictions, skipped
