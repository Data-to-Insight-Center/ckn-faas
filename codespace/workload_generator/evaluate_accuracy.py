# #!/usr/bin/env python3
# import json
# import re
# from pathlib import Path
# from typing import Dict, Set, List
# import pandas as pd
#
# # ==========================
# # 🔧 CONFIGURATION
# # ==========================
# CSV_PATH = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/ensemble_and _model_wise_accuracy.csv")
# LABELS_PATH = Path("Labels.json")  # or absolute path
# OUT_ROW_ANNOTATED = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/evaluation_rows_M2.csv")
# OUT_SUMMARY = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/evaluation_summary_M2.csv")
#
# # Fixed model list in the order you log them
# MODEL_LIST: List[str] = [
#     "vit_b_16", "resnet101", "mobilenet_v3_small", "resnet50", "resnet34", "resnet18"
# ]
#
# def model_label_col(m: str) -> str: return f"{m}_label"
# def model_prob_col(m: str) -> str:  return f"{m}_prob"
# def model_wait_col(m: str) -> str:  return f"{m}_wait"
#
# # Build header EXACTLY matching your row order (no selected_image)
# BASE_COLS = [
#     "ID","Deadline","IAR","RespTime","RunTime","selected_models",
#     "label","Accuracy","combiner_policy","e2e_time_ms","Success",
#     "selected_folder"
# ]
# PER_MODEL_LABEL_COLS = [model_label_col(m) for m in MODEL_LIST]
# PER_MODEL_PROB_COLS  = [model_prob_col(m) for m in MODEL_LIST]
# PER_MODEL_WAIT_COLS  = [model_wait_col(m) for m in MODEL_LIST]
# LOG_HEADER = BASE_COLS + PER_MODEL_LABEL_COLS + PER_MODEL_PROB_COLS + PER_MODEL_WAIT_COLS
# # ==========================
#
#
# # Keep for display if needed (not used in strict match)
# def normalize_label(s: str) -> str:
#     s = (s or "").strip().lower()
#     s = s.replace("_"," ").replace("-"," ")
#     s = re.sub(r"\s+"," ", s)
#     return s
#
# def tokenize_alpha(s: str):
#     """Return lowercase alphabetic tokens (drop digits/punct)."""
#     return re.findall(r"[a-z]+", (s or "").lower())
#
# def build_synset_map(label_json_path: Path) -> Dict[str, Set[str]]:
#     with open(label_json_path, "r") as f:
#         raw = json.load(f)
#     m: Dict[str, Set[str]] = {}
#     for wnid, names in raw.items():
#         # split synonyms by comma, normalize, but we will tokenize per comparison
#         parts = [normalize_label(x) for x in str(names).split(",")]
#         parts = [p for p in (x.strip() for x in parts) if p]
#         m[wnid] = set(parts)
#     return m
#
# def row_is_correct(wnid_map: Dict[str, Set[str]], wnid: str, pred_raw: str) -> bool:
#     """
#     Token-based matching:
#       - exact token match, OR
#       - predicted tokens ⊆ synonym tokens (e.g., 'nautilus' vs 'chambered nautilus')
#     Digits/junk like '1ww' are ignored as tokens (filtered out), which prevents false positives.
#     """
#     if not wnid or not pred_raw:
#         return False
#
#     pred_tokens = tokenize_alpha(pred_raw)
#     if not pred_tokens:
#         return False
#
#     syns = wnid_map.get(wnid, set())
#     if not syns:
#         return False
#
#     for syn in syns:
#         syn_tokens = tokenize_alpha(syn)
#
#         # exact token match
#         if pred_tokens == syn_tokens:
#             return True
#
#         # subset: allow shorter correct names (e.g., "nautilus") to match longer synonyms
#         if set(pred_tokens).issubset(set(syn_tokens)) and len(pred_tokens) >= 1:
#             return True
#
#     return False
#
#
# def main():
#     if not CSV_PATH.exists():
#         raise FileNotFoundError(f"CSV not found: {CSV_PATH}")
#     if not LABELS_PATH.exists():
#         raise FileNotFoundError(f"Labels.json not found: {LABELS_PATH}")
#
#     wnid_map = build_synset_map(LABELS_PATH)
#
#     # Your file has NO header → read with our explicit header
#     df = pd.read_csv(CSV_PATH, header=None, names=LOG_HEADER)
#
#     # ---- Ensemble correctness (using final 'label') ----
#     df["ensemble_correct"] = [
#         row_is_correct(
#             wnid_map,
#             str(wnid) if pd.notna(wnid) else "",
#             str(pred) if pd.notna(pred) else "",
#         )
#         for wnid, pred in zip(df["selected_folder"], df["label"])
#     ]
#
#     # ---- Per-model correctness (for each *_label column present) ----
#     for m in MODEL_LIST:
#         col = model_label_col(m)
#         if col in df.columns:
#             df[f"{m}_correct"] = [
#                 row_is_correct(
#                     wnid_map,
#                     str(wnid) if pd.notna(wnid) else "",
#                     str(pred) if pd.notna(pred) else "",
#                 )
#                 for wnid, pred in zip(df["selected_folder"], df[col])
#             ]
#         else:
#             df[f"{m}_correct"] = pd.NA
#
#     # ---- Accuracies (as average accuracy) ----
#     evaluable_ens = df[df["selected_folder"].notna() & df["label"].notna()]
#     ens_total = len(evaluable_ens)
#     ens_acc = float(evaluable_ens["ensemble_correct"].mean()) if ens_total > 0 else 0.0
#
#     per_model_acc_rows = []
#     for m in MODEL_LIST:
#         col_label = model_label_col(m)
#         col_corr  = f"{m}_correct"
#         if col_label in df.columns:
#             evaluable_m = df[df["selected_folder"].notna() & df[col_label].notna()]
#             total_m = len(evaluable_m)
#             acc_m = float(evaluable_m[col_corr].mean()) if total_m > 0 else float("nan")
#             per_model_acc_rows.append({"model": m, "total": total_m, "avg_accuracy": acc_m})
#         else:
#             per_model_acc_rows.append({"model": m, "total": 0, "avg_accuracy": float("nan")})
#
#     summary_rows = [{"model": "ensemble", "total": ens_total, "avg_accuracy": ens_acc}] + per_model_acc_rows
#     summary_df = pd.DataFrame(summary_rows)
#
#     # ---- Save per-row annotated (keep useful cols if present) ----
#     keep_cols = [
#         "ID","Deadline","IAR","RespTime","RunTime","selected_models",
#         "selected_folder","label","Accuracy",
#         "combiner_policy","e2e_time_ms","Success","ensemble_correct",
#     ]
#     for m in MODEL_LIST:
#         if model_label_col(m) in df.columns: keep_cols += [model_label_col(m)]
#         if model_prob_col(m)  in df.columns: keep_cols += [model_prob_col(m)]
#         if model_wait_col(m)  in df.columns: keep_cols += [model_wait_col(m)]
#         if f"{m}_correct"     in df.columns: keep_cols += [f"{m}_correct"]
#
#     keep_cols = [c for c in keep_cols if c in df.columns]
#     df[keep_cols].to_csv(OUT_ROW_ANNOTATED, index=False)
#     summary_df.to_csv(OUT_SUMMARY, index=False)
#
#     # ---- Console summary ----
#     print("=== Evaluation Summary ===")
#     print(f"CSV file:          {CSV_PATH}")
#     print(f"Labels (json):     {LABELS_PATH}")
#     print(f"Ensemble support:  {ens_total}")
#     print(f"Ensemble Avg Acc:  {ens_acc:.4f}\n")
#     print("Per-model Avg Acc:")
#     for r in per_model_acc_rows:
#         acc_str = "nan" if pd.isna(r['avg_accuracy']) else f"{r['avg_accuracy']:.4f}"
#         print(f"  - {r['model']:<20} total={r['total']:<5} acc={acc_str}")
#     print(f"\nPer-row annotated: {OUT_ROW_ANNOTATED}")
#     print(f"Summary for plots: {OUT_SUMMARY}")
#
# if __name__ == "__main__":
#     main()
#



#!/usr/bin/env python3



#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# import json
# import re
# import ast
# from pathlib import Path
# from typing import Dict, Set, List
#
# import pandas as pd
# import matplotlib.pyplot as plt
#
# # ==========================
# # 🔧 CONFIGURATION
# # ==========================
# CSV_PATH = Path("Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/ensemble_and _model_wise_accuracy_M3.csv")
# LABELS_PATH = Path("Labels.json"/Users/agamage/)
# OUT_ROW_ANNOTATED = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/evaluation_rows_M3_test1.csv")
# OUT_SUMMARY = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/evaluation_summary_M3_test1.csv")
# OUT_PLOT = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/evaluation_summary_bar_M3_test1.png")
#
# # MUST match your logger’s per-model column naming
# MODEL_LIST: List[str] = [
#     "mobilenet_v3_small", "resnet18", "resnet34",
#     "resnet50", "resnet101", "vit_b_16"
# ]
#
# def model_label_col(m: str) -> str: return f"{m}_label"
# def model_prob_col(m: str)  -> str: return f"{m}_prob"
# def model_wait_col(m: str)  -> str: return f"{m}_wait"
#
# # CSV header (file is headerless)
# BASE_COLS = [
#     "ID","Deadline","IAR","RespTime","RunTime","selected_models",
#     "label","Accuracy","combiner_policy","e2e_time_ms","Success",
#     "selected_folder","ModelSize"
# ]
# PER_MODEL_LABEL_COLS = [model_label_col(m) for m in MODEL_LIST]
# PER_MODEL_PROB_COLS  = [model_prob_col(m) for m in MODEL_LIST]
# PER_MODEL_WAIT_COLS  = [model_wait_col(m) for m in MODEL_LIST]
# LOG_HEADER = BASE_COLS + PER_MODEL_LABEL_COLS + PER_MODEL_PROB_COLS + PER_MODEL_WAIT_COLS + ["main_policy"]
#
# # ==========================
# # 🔍 helpers
# # ==========================
# def normalize_label(s: str) -> str:
#     s = (s or "").strip().lower()
#     s = s.replace("_", " ").replace("-", " ")
#     s = re.sub(r"\s+", " ", s)
#     return s
#
# def tokenize_alpha(s: str):
#     return re.findall(r"[a-z]+", (s or "").lower())
#
# def build_synset_map(label_json_path: Path) -> Dict[str, Set[str]]:
#     """Labels.json maps wnid -> 'name1, name2, ...' or list; normalize to tokens set."""
#     with open(label_json_path, "r") as f:
#         raw = json.load(f)
#     m: Dict[str, Set[str]] = {}
#     for wnid, names in raw.items():
#         parts = [normalize_label(x) for x in str(names).split(",")]
#         parts = [p for p in (x.strip() for x in parts) if p]
#         m[wnid] = set(parts)
#     return m
#
# def row_is_correct(wnid_map: Dict[str, Set[str]], wnid: str, pred_raw: str) -> bool:
#     if not wnid or not pred_raw:
#         return False
#     pred_tokens = tokenize_alpha(pred_raw)
#     if not pred_tokens:
#         return False
#     syns = wnid_map.get(wnid, set())
#     if not syns:
#         return False
#     for syn in syns:
#         syn_tokens = tokenize_alpha(syn)
#         # exact token match or prediction tokens fully included in a synonym’s tokens
#         if pred_tokens == syn_tokens or set(pred_tokens).issubset(set(syn_tokens)):
#             return True
#     return False
#
# def parse_selected_models(val):
#     """Safely parse the selected_models string like "['vit_b_16','resnet101']" to a list."""
#     if isinstance(val, list):
#         return val
#     if isinstance(val, str):
#         try:
#             out = ast.literal_eval(val)
#             return out if isinstance(out, list) else []
#         except Exception:
#             return []
#     return []
#
# def clean_pred_series(series: pd.Series) -> pd.Series:
#     """
#     Normalize placeholders to NA but keep true NaNs as NaN.
#     DO NOT cast the whole column to str (which turns NaN into 'nan').
#     """
#     return series.replace({"": pd.NA, "nan": pd.NA, "NaN": pd.NA, "-1": pd.NA, "-1.0": pd.NA, -1: pd.NA, -1.0: pd.NA})
#
# # ==========================
# # 🧮 main
# # ==========================
# def main():
#     if not CSV_PATH.exists():
#         raise FileNotFoundError(f"CSV not found: {CSV_PATH}")
#     if not LABELS_PATH.exists():
#         raise FileNotFoundError(f"Labels.json not found: {LABELS_PATH}")
#
#     wnid_map = build_synset_map(LABELS_PATH)
#
#     # Read CSV (headerless); treat standard placeholders as NA
#     df = pd.read_csv(
#         CSV_PATH,
#         header=None,
#         names=LOG_HEADER,
#         engine="python",
#         na_values=["", "nan", "NaN", "-1", "-1.0"]
#     )
#     df.columns = [c.strip() for c in df.columns]
#
#     # Parse selected models column to lists
#     df["selected_models_list"] = df["selected_models"].apply(parse_selected_models)
#
#     # ---- Ensemble correctness (final selected label) ----
#     df["ensemble_correct"] = [
#         row_is_correct(
#             wnid_map,
#             str(wnid) if pd.notna(wnid) else "",
#             str(pred) if pd.notna(pred) else "",
#         )
#         for wnid, pred in zip(df.get("selected_folder"), df.get("label"))
#     ]
#
#     # ---- Per-model correctness (ONLY on rows where the model was selected & has a label) ----
#     per_model_acc_rows = []
#     for m in MODEL_LIST:
#         col_label = model_label_col(m)
#         if col_label not in df.columns:
#             per_model_acc_rows.append({"model": m, "total": 0, "avg_accuracy": float("nan")})
#             continue
#
#         preds = clean_pred_series(df[col_label])
#         # Only evaluate on rows where:
#         #   - the model m was selected for that request
#         #   - we have a ground-truth (selected_folder)
#         #   - we have a non-missing prediction for this model
#         mask_selected = df["selected_models_list"].apply(lambda L: m in L)
#         mask_eval = df["selected_folder"].notna() & mask_selected & preds.notna()
#
#         total_m = int(mask_eval.sum())
#         if total_m == 0:
#             per_model_acc_rows.append({"model": m, "total": 0, "avg_accuracy": float("nan")})
#             continue
#
#         # Compute correctness on evaluable subset
#         wnids = df.loc[mask_eval, "selected_folder"]
#         model_preds = preds[mask_eval]
#         correct_flags = [
#             row_is_correct(
#                 wnid_map,
#                 str(wnid) if pd.notna(wnid) else "",
#                 str(pred) if pd.notna(pred) else "",
#             )
#             for wnid, pred in zip(wnids, model_preds)
#         ]
#         acc_m = float(pd.Series(correct_flags, dtype="float").mean()) if total_m > 0 else float("nan")
#         per_model_acc_rows.append({"model": m, "total": total_m, "avg_accuracy": acc_m})
#
#     # ---- Ensemble accuracy summary ----
#     evaluable_ens = df[df["selected_folder"].notna() & df["label"].notna()]
#     ens_total = int(len(evaluable_ens))
#     ens_acc = float(evaluable_ens["ensemble_correct"].mean()) if ens_total > 0 else 0.0
#
#     # ---- Build ensemble bar label with size/policy ----
#     # ModelSize might be float/NaN; take the max observed as a simple descriptor
#     max_size = pd.to_numeric(df.get("ModelSize", pd.Series(dtype=float)), errors="coerce").max()
#     max_size = int(max_size) if pd.notna(max_size) else 0
#     pol = str(df.get("main_policy", pd.Series(["mode_s"])).iloc[0]).strip().lower()
#
#     if max_size <= 1:
#         ensemble_label = "Fastest model"
#     elif pol == "randomized":
#         ensemble_label = f"Ensemble size {max_size}"
#     elif pol in {"greedy", "mode_s", "mode-s", "modes"}:
#         ensemble_label = f"Ensemble size {max_size}"
#     else:
#         ensemble_label = f"Ensemble size {max_size}"
#
#     # ---- Summary table (first row = ensemble) ----
#     summary_rows = [{"model": ensemble_label, "total": ens_total, "avg_accuracy": ens_acc}] + per_model_acc_rows
#     summary_df = pd.DataFrame(summary_rows)
#     summary_df.to_csv(OUT_SUMMARY, index=False)
#
#     # ---- Per-row annotated export (keep useful columns if present) ----
#     keep_cols = [
#         "ID","Deadline","IAR","RespTime","RunTime","selected_models",
#         "selected_folder","label","Accuracy","combiner_policy","e2e_time_ms","Success",
#         "ModelSize","main_policy","ensemble_correct",
#     ]
#     for m in MODEL_LIST:
#         if model_label_col(m) in df.columns: keep_cols.append(model_label_col(m))
#         if model_prob_col(m)  in df.columns: keep_cols.append(model_prob_col(m))
#         if model_wait_col(m)  in df.columns: keep_cols.append(model_wait_col(m))
#         corr_col = f"{m}_correct"
#         # Recompute/store per-row correctness column for convenience in the annotated CSV
#         if model_label_col(m) in df.columns:
#             preds_all = clean_pred_series(df[model_label_col(m)])
#             mask_sel = df["selected_models_list"].apply(lambda L, _m=m: _m in L)
#             df[corr_col] = pd.NA
#             idx = df.index[ df["selected_folder"].notna() & mask_sel & preds_all.notna() ]
#             df.loc[idx, corr_col] = [
#                 row_is_correct(
#                     wnid_map,
#                     str(wn) if pd.notna(wn) else "",
#                     str(pr) if pd.notna(pr) else "",
#                 )
#                 for wn, pr in zip(df.loc[idx, "selected_folder"], preds_all.loc[idx])
#             ]
#             keep_cols.append(corr_col)
#
#     keep_cols = [c for c in keep_cols if c in df.columns]
#     df[keep_cols].to_csv(OUT_ROW_ANNOTATED, index=False)
#
#     # ---- Plot: ensemble in green, others blue ----
#     colors = ["#2ecc71"] + ["#3498db"] * (len(summary_df := summary_df) - 1)
#     plt.figure(figsize=(9, 4.6))
#     bars = plt.bar(summary_df["model"], summary_df["avg_accuracy"], color=colors)
#     plt.xticks(rotation=45, ha="right")
#     plt.ylabel("Average Accuracy")
#     plt.title("Ensemble (with size) and Model-wise Accuracy")
#     for b in bars:
#         h = b.get_height()
#         if pd.notna(h):
#             plt.text(b.get_x() + b.get_width()/2, h + 0.01, f"{h:.3f}", ha="center", va="bottom", fontsize=9)
#     plt.ylim(0, 1.1)
#     plt.tight_layout()
#     plt.savefig(OUT_PLOT, dpi=200)
#     plt.show()
#
#     # ---- Console summary ----
#     print("=== Evaluation Summary ===")
#     print(f"CSV file:          {CSV_PATH}")
#     print(f"Labels (json):     {LABELS_PATH}")
#     print(f"Ensemble support:  {ens_total}")
#     print(f"Ensemble Avg Acc:  {ens_acc:.4f}\n")
#     print("Per-model Avg Acc:")
#     for r in per_model_acc_rows:
#         acc_str = "nan" if pd.isna(r['avg_accuracy']) else f"{r['avg_accuracy']:.4f}"
#         print(f"  - {r['model']:<20} total={r['total']:<5} acc={acc_str}")
#     print(f"\nPer-row annotated: {OUT_ROW_ANNOTATED}")
#     print(f"Summary for plots: {OUT_SUMMARY}")
#     print(f"Bar chart saved:   {OUT_PLOT}")
#
# if __name__ == "__main__":
#     main()




#!/usr/bin/env python3
"""
Evaluate accuracy from MODE-S workload logs (headerless CSV).

What you asked for:
1) Ensemble-size accuracy ONLY by ModelSize (ignore policy).
2) Single-model accuracy ONLY when ModelSize == 1 (by model name).
"""

import ast
import json
import re
from pathlib import Path
from typing import Dict, Set, List

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ==========================
# 🔧 CONFIGURATION
# ==========================
CSV_PATH = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/accuracy_confidence_logs_2_3_S.csv")
LABELS_PATH = Path("Labels.json")

OUT_MODEL_WISE = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/model_wise_accuracy.csv")
OUT_ENSEMBLE_WISE = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/ensemble_size_accuracy.csv")
OUT_PLOT = Path("/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/accuracy_bar.png")

# MUST match your logger’s models (and per-model columns)
MODEL_LIST: List[str] = [
    "mobilenet_v3_small", "resnet18", "resnet34",
    "resnet50", "resnet101", "vit_b_16"
]

def model_label_col(m: str) -> str: return f"{m}_label"
def model_prob_col(m: str)  -> str: return f"{m}_prob"
def model_wait_col(m: str)  -> str: return f"{m}_wait"

# Base columns written by your logger
BASE_COLS = [
    "ID","Deadline","IAR","RespTime","RunTime","selected_models",
    "label","Accuracy","combiner_policy","e2e_time_ms","Success",
    "selected_folder","ModelSize"
]
PER_MODEL_LABEL_COLS = [model_label_col(m) for m in MODEL_LIST]
PER_MODEL_PROB_COLS  = [model_prob_col(m) for m in MODEL_LIST]
PER_MODEL_WAIT_COLS  = [model_wait_col(m) for m in MODEL_LIST]

# Tail columns in your NEW log (based on your logger snippet)
LOG_HEADER = BASE_COLS + PER_MODEL_LABEL_COLS + PER_MODEL_PROB_COLS + PER_MODEL_WAIT_COLS + ["main_policy", "alpha"]


# ==========================
# 🔍 helpers
# ==========================
def normalize_label(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    return s

def tokenize_alpha(s: str):
    return re.findall(r"[a-z]+", (s or "").lower())

def build_synset_map(label_json_path: Path) -> Dict[str, Set[str]]:
    """Labels.json maps wnid -> 'name1, name2, ...' or list; normalize to synonyms set."""
    with open(label_json_path, "r") as f:
        raw = json.load(f)
    m: Dict[str, Set[str]] = {}
    for wnid, names in raw.items():
        parts = [normalize_label(x) for x in str(names).split(",")]
        parts = [p for p in (x.strip() for x in parts) if p]
        m[wnid] = set(parts)
    return m

def row_is_correct(wnid_map: Dict[str, Set[str]], wnid: str, pred_raw: str) -> bool:
    """
    Lenient correctness:
      - token-equal OR prediction tokens subset of any synonym tokens.
    """
    if not wnid or not pred_raw:
        return False
    pred_tokens = tokenize_alpha(pred_raw)
    if not pred_tokens:
        return False
    syns = wnid_map.get(wnid, set())
    if not syns:
        return False
    for syn in syns:
        syn_tokens = tokenize_alpha(syn)
        if pred_tokens == syn_tokens or set(pred_tokens).issubset(set(syn_tokens)):
            return True
    return False

def parse_selected_models(val):
    """Parse selected_models like "['vit_b_16','resnet101']" to a list."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            out = ast.literal_eval(val)
            return out if isinstance(out, list) else []
        except Exception:
            return []
    return []

def safe_int_series(s: pd.Series, default: int = 0) -> pd.Series:
    x = pd.to_numeric(s, errors="coerce")
    x = x.fillna(default).astype(int)
    return x

def safe_bool_series(s: pd.Series) -> pd.Series:
    # Success may be True/False (bool) or "True"/"False" (str)
    if s.dtype == bool:
        return s
    return (
        s.astype(str).str.strip().str.lower()
        .map({"true": True, "false": False})
        .fillna(False)
    )


def plot_like_yours(model_wise: pd.DataFrame, ensemble_wise: pd.DataFrame, out_plot: Path):
    """
    Plot exactly in your style:
      - First two bars (Model set size 2/3) green shades
      - Remaining bars steelblue
      - Larger fonts, rotated x labels
      - Avoid clipping first label
    """

    # ---- Build labels + accs exactly like your snippet ----
    # Expect ensemble_wise has rows for ModelSize 2 and 3 (if present)
    ens_map = {int(r["ModelSize"]): float(r["avg_accuracy"]) for _, r in ensemble_wise.iterrows()}
    set2_acc = ens_map.get(2, float("nan"))
    set3_acc = ens_map.get(3, float("nan"))

    # model_wise columns: single_model, avg_accuracy
    model_names = model_wise["single_model"].astype(str).tolist()
    model_accs  = model_wise["avg_accuracy"].astype(float).tolist()

    labels = ["Model set size 2", "Model set size 3"] + model_names
    accs   = [set2_acc, set3_acc] + model_accs

    # ---- Styling EXACTLY like your snippet ----
    plt.rcParams.update({
        "font.size": 16,
        "axes.labelsize": 17,
        "xtick.labelsize": 16,
        "ytick.labelsize": 15,
    })

    fig, ax = plt.subplots(figsize=(11, 5.5))
    bars = ax.bar(labels, accs)

    for idx, bar in enumerate(bars):
        if idx == 0:
            bar.set_color("#2E8B57")
            bar.set_linewidth(2)
        elif idx == 1:
            bar.set_color("#2F7D32")
            bar.set_linewidth(2)
        else:
            bar.set_color("steelblue")

    for bar, val in zip(bars, accs):
        if not (val is None or (isinstance(val, float) and np.isnan(val))):
            ax.text(
                bar.get_x() + bar.get_width()/2,
                bar.get_height() + 0.012,
                f"{val:.3f}",
                ha="center", va="bottom", fontsize=16
            )

    ax.set_ylabel("Average Accuracy")
    ax.set_ylim(0, 1.05)
    ax.set_xticklabels(labels, rotation=25, ha="right")

    # ✅ avoid clipping first label
    ax.margins(x=0.02)
    fig.subplots_adjust(left=0.095, right=0.995, top=0.98, bottom=0.28)

    fig.savefig(out_plot, dpi=400, bbox_inches="tight")
    plt.show()
    print(f"✅ Plot saved to {out_plot}")



# ==========================
# 🧮 main
# ==========================
def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")
    if not LABELS_PATH.exists():
        raise FileNotFoundError(f"Labels.json not found: {LABELS_PATH}")

    wnid_map = build_synset_map(LABELS_PATH)

    # ✅ Headerless CSV: first row is REQ-..., so use header=None and provide LOG_HEADER
    df = pd.read_csv(
        CSV_PATH,
        header=None,
        names=LOG_HEADER,
        engine="python",
        na_values=["", "nan", "NaN", "-1", "-1.0"]
    )
    df.columns = [c.strip() for c in df.columns]

    # Normalize types
    df["ModelSize"] = safe_int_series(df["ModelSize"], default=0)
    df["Success"] = safe_bool_series(df["Success"])

    # Parse selected_models column into list
    df["selected_models_list"] = df["selected_models"].apply(parse_selected_models)

    # Evaluate correctness of FINAL label vs ground-truth wnid
    df["final_correct"] = [
        row_is_correct(
            wnid_map,
            str(gt) if pd.notna(gt) else "",
            str(pred) if pd.notna(pred) else "",
        )
        for gt, pred in zip(df.get("selected_folder"), df.get("label"))
    ]

    # Only evaluate rows with ground truth + prediction present
    df_eval = df[df["selected_folder"].notna() & df["label"].notna()].copy()

    # ==========================
    # (A) Single-model accuracy (ModelSize == 1) — by model name only
    # ==========================
    df_m1 = df_eval[df_eval["ModelSize"] == 1].copy()
    df_m1["single_model"] = df_m1["selected_models_list"].apply(
        lambda L: L[0] if isinstance(L, list) and len(L) == 1 else pd.NA
    )
    df_m1 = df_m1.dropna(subset=["single_model"])

    model_wise = df_m1.groupby(["single_model"]).agg(
        total=("final_correct", "count"),
        avg_accuracy=("final_correct", "mean"),
    ).reset_index()

    model_wise["avg_accuracy"] = model_wise["avg_accuracy"].astype(float)
    model_wise = model_wise.sort_values(["avg_accuracy"], ascending=False)
    model_wise = model_wise.sort_values("single_model", ascending=True).reset_index(drop=True)
    model_wise.to_csv(OUT_MODEL_WISE, index=False)

    # ==========================
    # (B) Ensemble-size accuracy (ModelSize > 1) — by ModelSize only (ignore policy)
    # ==========================
    df_ens = df_eval[df_eval["ModelSize"] > 1].copy()

    ensemble_wise = df_ens.groupby(["ModelSize"]).agg(
        total=("final_correct", "count"),
        avg_accuracy=("final_correct", "mean"),
    ).reset_index()

    ensemble_wise["avg_accuracy"] = ensemble_wise["avg_accuracy"].astype(float)
    ensemble_wise = ensemble_wise.sort_values(["ModelSize"])
    ensemble_wise.to_csv(OUT_ENSEMBLE_WISE, index=False)

    # ==========================
    # (C) Optional bar plot: ensemble sizes + single models
    # ==========================
    plot_labels = []
    plot_vals = []
    plot_colors = []

    # Ensemble bars first (green)
    for _, r in ensemble_wise.iterrows():
        plot_labels.append(f"Model set size {int(r['ModelSize'])}")
        plot_vals.append(float(r["avg_accuracy"]))
        plot_colors.append("#2ecc71")

    # Single model bars next (blue)
    for _, r in model_wise.iterrows():
        plot_labels.append(str(r["single_model"]))
        plot_vals.append(float(r["avg_accuracy"]))
        plot_colors.append("#3498db")

    if plot_labels:
        plt.figure(figsize=(10.5, 4.8))
        bars = plt.bar(plot_labels, plot_vals, color=plot_colors)
        plt.xticks(rotation=35, ha="right")
        plt.ylabel("Average Accuracy")
        plt.title("Ensemble-size and Single-model Accuracy")

        for b in bars:
            h = b.get_height()
            if np.isfinite(h):
                plt.text(
                    b.get_x() + b.get_width()/2, h + 0.01,
                    f"{h:.3f}", ha="center", va="bottom", fontsize=9
                )

        plt.ylim(0, 1.1)
        plt.tight_layout()
        plt.savefig(OUT_PLOT, dpi=200)
        plt.show()

    # Console output
    print("\n=== Single-model accuracy (ModelSize==1) ===")
    print(model_wise.to_string(index=False))

    print("\n=== Ensemble-size accuracy (ModelSize>1) ===")
    print(ensemble_wise.to_string(index=False))

    print(f"\n[OK] Saved:\n - {OUT_MODEL_WISE}\n - {OUT_ENSEMBLE_WISE}\n - {OUT_PLOT}")

    plot_like_yours(model_wise, ensemble_wise, OUT_PLOT)

if __name__ == "__main__":
    main()



