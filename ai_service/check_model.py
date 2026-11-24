"""1단계 검증 (heavy 팀 모델): 모델·Feature 순서·학습 정보·heavy 로드 확인."""
import csv
import json
import sys
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
M = ROOT / "models"

model = joblib.load(M / "rf_action_team.joblib")
columns = json.loads((M / "rf_feature_columns.json").read_text(encoding="utf-8"))
info = json.loads((M / "rf_training_info.json").read_text(encoding="utf-8"))
steps = int(info["sequence_steps"])
with (ROOT / "configs" / "action_classes_heavy.csv").open(encoding="utf-8-sig") as f:
    actions = {r["action_label"]: r["action_id"] for r in csv.DictReader(f)}

print("모델 종류        :", type(model).__name__)
print("클래스           :", list(model.classes_))
print("동작 ID 매핑     :", {c: actions.get(c, "?") for c in model.classes_})
print("모델 입력 Feature:", model.n_features_in_)
print("Feature JSON 개수:", len(columns))
print("Sequence Step    :", steps, "→", steps, "× 38 =", steps * 38)
print("학습 Pose 모델   :", info.get("pose_model", "-"))

from src.sequence_utils import sequence_feature_names
same_order = sequence_feature_names(steps) == columns
print("Feature 순서 일치:", same_order)

has_task = (M / "pose_landmarker_heavy.task").exists()
has_yolo = (M / "yolo11n-pose.pt").exists()
print("heavy .task      :", has_task)
print("YOLO .pt         :", has_yolo)

heavy_ok = False
try:
    from src.heavy_pose import HeavyPose
    hp = HeavyPose()          # models/pose_landmarker_heavy.task 로드
    hp.close()
    heavy_ok = True
except Exception as e:
    print("heavy 로드 오류  :", e)
print("heavy 로드       :", heavy_ok)

ok = (len(model.classes_) == 3 and set(model.classes_) <= set(actions)
      and model.n_features_in_ == len(columns) == steps * 38
      and same_order and has_task and has_yolo and heavy_ok)
print("\n1단계 결과:", "PASS" if ok else "FAIL")
