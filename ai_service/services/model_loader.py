"""
학습된 모델 묶음(heavy 팀 RF)을 서버 시작 시 한 번만 불러옵니다.

- rf_action_team.joblib      : Random Forest (동작 3개)
- rf_feature_columns.json    : 1,140개 Feature 이름과 순서
- rf_training_info.json      : sequence_steps(30), min_valid_frames 등
- configs/action_classes_heavy.csv : action_label → action_id (A001·A002·A006)
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parents[1]          # ai_service/
MODEL_DIR = ROOT / "models"
CONFIG_DIR = ROOT / "configs"


@dataclass
class ModelBundle:
    model: object
    columns: list[str]
    info: dict
    classes: list[str]
    action_ids: dict[str, str]        # label → A00x
    sequence_steps: int
    min_valid_frames: int

    @property
    def feature_count(self) -> int:
        return len(self.columns)


def load_model_bundle() -> ModelBundle:
    model = joblib.load(MODEL_DIR / "rf_action_team.joblib")
    columns = json.loads((MODEL_DIR / "rf_feature_columns.json").read_text(encoding="utf-8"))
    info = json.loads((MODEL_DIR / "rf_training_info.json").read_text(encoding="utf-8"))
    with (CONFIG_DIR / "action_classes_heavy.csv").open(encoding="utf-8-sig") as f:
        action_ids = {r["action_label"].strip(): r["action_id"].strip() for r in csv.DictReader(f)}

    steps = int(info["sequence_steps"])
    classes = [str(c) for c in model.classes_]

    # 학습 규격 검사: 하나라도 어긋나면 서버를 띄우지 않음
    if model.n_features_in_ != len(columns) or len(columns) != steps * 38:
        raise RuntimeError(
            f"Feature 수 불일치: model={model.n_features_in_}, json={len(columns)}, steps×38={steps * 38}"
        )
    missing = [c for c in classes if c not in action_ids]
    if missing:
        raise RuntimeError(f"action_classes_heavy.csv에 없는 클래스: {missing}")

    return ModelBundle(
        model=model,
        columns=columns,
        info=info,
        classes=classes,
        action_ids=action_ids,
        sequence_steps=steps,
        min_valid_frames=int(info.get("min_valid_frames", 10)),
    )
