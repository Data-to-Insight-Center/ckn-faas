# #!/usr/bin/env python3
# import glob
# import numpy as np
# import pandas as pd
# import matplotlib.pyplot as plt
#
# # ---- Adjust this to your folder/pattern ----
# LOG_PATH_PATTERN = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/avg_latency_vs_arrival_para.csv"
# OUT_CSV = "avg_latency_vs_arrival_by_maxsize_resp.csv"
# OUT_PNG = "avg_latency_vs_arrival_by_maxsize_resp.png"
#
# # Column indices in your headerless CSV (0-based):
# # 2 -> IAR (ms), 3 -> RespTime (s), 12 -> ModelSize
# IAR_COL_IDX = 2
# RESP_COL_IDX = 3          # <--- use RespTime
# MODEL_SIZE_COL_IDX = 12
#
# def read_one_csv(path: str) -> pd.DataFrame:
#     df = pd.read_csv(path, header=None)
#     rename_map = {}
#     if IAR_COL_IDX in df.columns:        rename_map[IAR_COL_IDX] = "IAR"
#     if RESP_COL_IDX in df.columns:       rename_map[RESP_COL_IDX] = "RespTime"      # seconds
#     if MODEL_SIZE_COL_IDX in df.columns: rename_map[MODEL_SIZE_COL_IDX] = "ModelSize"
#     return df.rename(columns=rename_map)
#
# def load_logs(pattern: str) -> pd.DataFrame:
#     files = glob.glob(pattern)
#     if not files:
#         raise SystemExit(f"No CSV files found for pattern:\n{pattern}")
#     frames = [read_one_csv(f) for f in files]
#     return pd.concat(frames, ignore_index=True)
#
# def aggregate_by_maxsize(df: pd.DataFrame, success_only: bool = True) -> pd.DataFrame:
#     # If Success column exists, keep only successful rows
#     if success_only and "Success" in df.columns:
#         df = df[df["Success"] == True].copy()
#
#     # Clean numeric
#     for col in ("IAR", "RespTime"):
#         if col not in df.columns:
#             raise ValueError(f"Missing required column '{col}' in CSV.")
#         df[col] = pd.to_numeric(df[col], errors="coerce")
#
#     if "ModelSize" not in df.columns:
#         raise ValueError("Missing required column 'ModelSize' in CSV.")
#     df["ModelSize"] = pd.to_numeric(df["ModelSize"], errors="coerce")
#
#     # Drop incomplete rows
#     df = df.dropna(subset=["IAR", "RespTime", "ModelSize"])
#
#     # Convert RespTime (s) -> ms for plotting/aggregation
#     df["resp_time_ms"] = df["RespTime"] * 1000.0
#
#     # Arrival rate (req/s) from IAR in ms
#     df["arrival_rate"] = 1000.0 / df["IAR"]
#
#     # Aggregate strictly by IAR and ModelSize using RespTime
#     grouped = df.groupby(["IAR", "ModelSize"], dropna=False).agg(
#         mean_latency_ms=("resp_time_ms", "mean"),
#         std_latency_ms=("resp_time_ms", "std"),
#         n=("resp_time_ms", "count"),
#         arrival_rate=("arrival_rate", "mean"),
#     ).reset_index()
#
#     # Error bars: SEM
#     grouped["sem_latency_ms"] = grouped["std_latency_ms"] / np.sqrt(grouped["n"].clip(lower=1))
#     grouped["sem_latency_ms"] = grouped["sem_latency_ms"].fillna(0.0)
#     grouped["std_latency_ms"] = grouped["std_latency_ms"].fillna(0.0)
#
#     # Nice ordering
#     grouped = grouped.sort_values(["ModelSize", "arrival_rate"]).reset_index(drop=True)
#
#     # Console summary
#     print("[INFO] Lines to plot (ModelSize → #points):")
#     for ms, sub in grouped.groupby("ModelSize"):
#         print(f"  - {int(ms)} → {len(sub)} points")
#
#     return grouped
#
# def plot(grouped: pd.DataFrame, out_png: str) -> None:
#     fig, ax = plt.subplots()
#
#     # Auto-switch to log scale if the range is huge (fastest vs ensembles)
#     ymin = max(grouped["mean_latency_ms"].min(), 1e-6)
#     ymax = grouped["mean_latency_ms"].max()
#     range_ratio = ymax / ymin if ymin > 0 else np.inf
#     use_log = range_ratio > 20  # threshold; tweak if you like
#
#     for ms, sub in grouped.groupby("ModelSize"):
#         sub = sub.sort_values("arrival_rate")
#         y = sub["mean_latency_ms"].to_numpy()
#         yerr = sub["sem_latency_ms"].to_numpy()
#
#         if use_log:
#             # ensure y - yerr > 0 in log scale
#             y = np.maximum(y, 1e-6)
#             yerr = np.minimum(yerr, 0.9 * y)
#
#         label = "Fastest model" if int(ms) == 1 else f"Ensemble size {int(ms)}"
#
#         ax.errorbar(
#             sub["arrival_rate"],
#             y,
#             yerr=yerr,
#             fmt="-o",
#             capsize=3,
#             elinewidth=1,
#             linewidth=2.0 if int(ms) == 1 else 1.5,
#             label=label,
#             alpha=0.95,
#         )
#
#     ax.set_xlabel("Arrival Rate (requests/second)")
#     ax.set_ylabel("Average Latency (ms)")
#     title_suffix = " (log scale)" if use_log else ""
#     ax.set_title(f"Average Latency vs Arrival Rate by Ensemble Size")
#     ax.grid(True, linestyle="--", alpha=0.5)
#     ax.legend()
#     fig.tight_layout()
#     fig.savefig(out_png, dpi=200)
#     print(f"[OK] Plot saved to: {out_png}")
#
# def main():
#     df = load_logs(LOG_PATH_PATTERN)
#     grouped = aggregate_by_maxsize(df, success_only=True)
#     grouped.to_csv(OUT_CSV, index=False)
#     print(f"[OK] Aggregated CSV saved to: {OUT_CSV}")
#     plot(grouped, OUT_PNG)
#
# if __name__ == "__main__":
#     main()




# #!/usr/bin/env python3
# import ast
# import csv
# import glob
# import numpy as np
# import pandas as pd
# import matplotlib.pyplot as plt
# from typing import List
#
# # ---- Adjust this to your folder/pattern ----
# LOG_PATH_PATTERN = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/avg_latency_vs_arrival1.csv"
# OUT_CSV = "avg_latency_vs_arrival_by_maxsize_resp.csv"
# OUT_PNG = "avg_latency_vs_arrival_by_maxsize_resp.png"
#
# # Fixed positional columns in your logger (0-based)
# IAR_COL_IDX        = 2   # IAR (ms)
# RESP_COL_IDX       = 3   # RespTime (s)
# SEL_MODELS_COL_IDX = 5   # selected_models (stringified list)
# MODEL_SIZE_IDX     = 12  # ModelSize (numeric in new logs)
#
# def _parse_models_cell(x):
#     """Parse selected_models like "['vit_b_16','resnet50']" to a list."""
#     if x is None:
#         return []
#     if isinstance(x, list):
#         return x
#     sx = str(x).strip()
#     try:
#         val = ast.literal_eval(sx)
#         if isinstance(val, (list, tuple)):
#             return list(val)
#     except Exception:
#         pass
#     # Fallback: pull out items between quotes
#     return [m for m in pd.Series(sx).str.findall(r"[\"']([^\"']+)[\"']").sum()]
#
# def _lenient_csv_read(path: str) -> List[List[str]]:
#     """
#     Read CSV rows leniently:
#       - Keep all rows regardless of field count
#       - Preserve quoting
#       - Return list of lists (strings)
#     """
#     rows: List[List[str]] = []
#     with open(path, "r", newline="") as f:
#         rdr = csv.reader(f)
#         for row in rdr:
#             rows.append(row)
#     return rows
#
# def _extract_policy_from_tail(row: List[str]) -> str:
#     """
#     Inspect the rightmost 1–2 cells to detect a textual policy.
#     If empty/numeric/absent -> return default 'mode_s'.
#     """
#     def is_number(s: str) -> bool:
#         try:
#             float(s)
#             return True
#         except Exception:
#             return False
#
#     for offset in (1, 2):  # last, then second-last
#         if len(row) >= offset:
#             cell = row[-offset].strip() if row[-offset] is not None else ""
#             if cell and not is_number(cell):
#                 return cell.lower()
#     return "mode_s"  # default
#
# def _read_csv_lenient_any_schema(path: str) -> pd.DataFrame:
#     """
#     Robust parse:
#       - Always read rows leniently (ragged ok).
#       - Map fixed early columns (IAR, RespTime, selected_models, ModelSize if present).
#       - If ModelSize not numeric -> derive from selected_models.
#       - main_policy from tail text; if empty/numeric -> 'mode_s'.
#     """
#     rows = _lenient_csv_read(path)
#     # Determine max columns to pad shorter rows
#     max_cols = max(len(r) for r in rows) if rows else 0
#
#     # Pad rows to equal length
#     norm_rows = [r + [""] * (max_cols - len(r)) for r in rows]
#     df = pd.DataFrame(norm_rows)
#
#     # Map required columns if they exist
#     colnames = {}
#     if IAR_COL_IDX < df.shape[1]:        colnames[IAR_COL_IDX] = "IAR"
#     if RESP_COL_IDX < df.shape[1]:       colnames[RESP_COL_IDX] = "RespTime"
#     if SEL_MODELS_COL_IDX < df.shape[1]: colnames[SEL_MODELS_COL_IDX] = "selected_models"
#     if MODEL_SIZE_IDX < df.shape[1]:     colnames[MODEL_SIZE_IDX] = "ModelSize"
#     df = df.rename(columns=colnames)
#
#     # Policy from the tail cells (last/second-last)
#     df["main_policy"] = [ _extract_policy_from_tail(list(r)) for _, r in df.iterrows() ]
#     # Normalize policy label
#     df["main_policy"] = df["main_policy"].astype(str).str.lower().replace({"": "mode_s"}).fillna("mode_s")
#
#     # ModelSize numeric if present; else derive from selected_models
#     if "ModelSize" in df.columns:
#         ms_num = pd.to_numeric(df["ModelSize"], errors="coerce")
#     else:
#         ms_num = pd.Series([np.nan] * len(df))
#
#     # Derive size from selected_models where ModelSize is NaN or non-positive
#     need_derive = ms_num.isna() | (ms_num <= 0)
#     if "selected_models" in df.columns and need_derive.any():
#         parsed = df.loc[need_derive, "selected_models"].apply(_parse_models_cell)
#         ms_num.loc[need_derive] = parsed.apply(len).astype(float)
#
#     df["ModelSize"] = ms_num
#
#     return df
#
# def load_logs(pattern: str) -> pd.DataFrame:
#     files = glob.glob(pattern)
#     if not files:
#         raise SystemExit(f"No CSV files found for pattern:\n{pattern}")
#     frames = [_read_csv_lenient_any_schema(f) for f in files]
#     return pd.concat(frames, ignore_index=True)
#
# def aggregate_by_maxsize(df: pd.DataFrame, success_only: bool = True) -> pd.DataFrame:
#     # Optional filter (only if column exists)
#     if success_only and "Success" in df.columns:
#         df = df[df["Success"] == True].copy()
#
#     # Ensure required numerics
#     for col in ("IAR", "RespTime", "ModelSize"):
#         if col not in df.columns:
#             raise ValueError(f"Missing required column '{col}' in CSV.")
#         df[col] = pd.to_numeric(df[col], errors="coerce")
#
#     # Drop incomplete/useless rows
#     df = df.dropna(subset=["IAR", "RespTime", "ModelSize"])
#     df = df[df["ModelSize"] > 0]
#
#     # Units + arrival rate
#     df["resp_time_ms"] = df["RespTime"] * 1000.0
#     df["arrival_rate"] = 1000.0 / df["IAR"]
#
#     grouped = df.groupby(["IAR", "ModelSize", "main_policy"], dropna=False).agg(
#         mean_latency_ms=("resp_time_ms", "mean"),
#         std_latency_ms=("resp_time_ms", "std"),
#         n=("resp_time_ms", "count"),
#         arrival_rate=("arrival_rate", "mean"),
#     ).reset_index()
#
#     grouped["sem_latency_ms"] = grouped["std_latency_ms"] / np.sqrt(grouped["n"].clip(lower=1))
#     grouped["sem_latency_ms"] = grouped["sem_latency_ms"].fillna(0.0)
#     grouped["std_latency_ms"] = grouped["std_latency_ms"].fillna(0.0)
#
#     grouped = grouped.sort_values(["main_policy", "ModelSize", "arrival_rate"]).reset_index(drop=True)
#
#     print("[INFO] Lines to plot (policy, size → #points):")
#     for (pol, ms), sub in grouped.groupby(["main_policy", "ModelSize"]):
#         print(f"  - {pol}, size {int(ms)} → {len(sub)} points")
#
#     return grouped
#
# def _label_for(pol: str, ms: float) -> str:
#     ms_int = int(ms)
#     p = (pol or "mode_s").lower()
#     if ms_int == 1:
#         return "Fastest model"
#     if p == "randomized":
#         return f"Ensemble size {ms_int}"
#     if p in {"greedy", "mode_s", "mode-s", "modes"}:
#         return f"MODE-S max ensemble size {ms_int}"
#     return f"{p} size {ms_int}"
#
# def plot(grouped: pd.DataFrame, out_png: str) -> None:
#     fig, ax = plt.subplots()
#
#     ymin = max(grouped["mean_latency_ms"].min(), 1e-6)
#     ymax = grouped["mean_latency_ms"].max()
#     use_log = (ymax / ymin) > 20 if ymin > 0 else True
#
#     for (pol, ms), sub in grouped.groupby(["main_policy", "ModelSize"]):
#         sub = sub.sort_values("arrival_rate")
#         y = sub["mean_latency_ms"].to_numpy()
#         yerr = sub["sem_latency_ms"].to_numpy()
#         if use_log:
#             y = np.maximum(y, 1e-6)
#             yerr = np.minimum(yerr, 0.9 * y)
#
#         ax.errorbar(
#             sub["arrival_rate"],
#             y,
#             yerr=yerr,
#             fmt="-o",
#             capsize=3,
#             elinewidth=1,
#             linewidth=2.0 if int(ms) == 1 else 1.5,
#             label=_label_for(pol, ms),
#             alpha=0.95,
#         )
#
#     ax.set_xlabel("Arrival Rate (requests/second)")
#     ax.set_ylabel("Average Latency (ms)")
#     ax.set_title("Average Latency vs Arrival Rate by Ensemble Size")
#     ax.grid(True, linestyle="--", alpha=0.5)
#     ax.legend(ncol=1, fontsize=9)
#     fig.tight_layout()
#     fig.savefig(out_png, dpi=200)
#     fig.show()
#     print(f"[OK] Plot saved to: {out_png}")
#
# def main():
#     df = load_logs(LOG_PATH_PATTERN)
#     grouped = aggregate_by_maxsize(df, success_only=True)
#     grouped.to_csv(OUT_CSV, index=False)
#     print(f"[OK] Aggregated CSV saved to: {OUT_CSV}")
#     plot(grouped, OUT_PNG)
#
# if __name__ == "__main__":
#     main()

# #!/usr/bin/env python3
# import ast
# import csv
# import glob
# import numpy as np
# import pandas as pd
# import matplotlib.pyplot as plt
# from typing import List
#
# # ---- Adjust this to your folder/pattern ----
# # LOG_PATH_PATTERN = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/avg_latency_vs_arrival1.csv"
# LOG_PATH_PATTERN = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/avg_latency_vs_arrival_para_run.csv"
# OUT_CSV = "avg_latency_vs_arrival_by_maxsize_resp.csv"
# OUT_PNG = "avg_latency_vs_arrival_by_maxsize_resp.png"
#
# # Fixed positional columns in your logger (0-based)
# IAR_COL_IDX        = 2   # IAR (ms)
# RESP_COL_IDX       = 3   # RespTime (s)
# SEL_MODELS_COL_IDX = 5   # selected_models (stringified list)
# MODEL_SIZE_IDX     = 12  # ModelSize (numeric in new logs)
#
# def _parse_models_cell(x):
#     """Parse selected_models like "['vit_b_16','resnet50']" to a list."""
#     if x is None:
#         return []
#     if isinstance(x, list):
#         return x
#     sx = str(x).strip()
#     try:
#         val = ast.literal_eval(sx)
#         if isinstance(val, (list, tuple)):
#             return list(val)
#     except Exception:
#         pass
#     # Fallback: pull out items between quotes
#     return [m for m in pd.Series(sx).str.findall(r"[\"']([^\"']+)[\"']").sum()]
#
# def _lenient_csv_read(path: str) -> List[List[str]]:
#     """Read CSV rows leniently and return list of string lists."""
#     rows: List[List[str]] = []
#     with open(path, "r", newline="") as f:
#         rdr = csv.reader(f)
#         for row in rdr:
#             rows.append(row)
#     return rows
#
# def _extract_policy_from_tail(row: List[str]) -> str:
#     """Try to detect textual policy from last columns."""
#     def is_number(s: str) -> bool:
#         try:
#             float(s)
#             return True
#         except Exception:
#             return False
#     for offset in (1, 2):
#         if len(row) >= offset:
#             cell = row[-offset].strip() if row[-offset] is not None else ""
#             if cell and not is_number(cell):
#                 return cell.lower()
#     return "mode_s"
#
# def _read_csv_lenient_any_schema(path: str) -> pd.DataFrame:
#     rows = _lenient_csv_read(path)
#     max_cols = max(len(r) for r in rows) if rows else 0
#     norm_rows = [r + [""] * (max_cols - len(r)) for r in rows]
#     df = pd.DataFrame(norm_rows)
#
#     # Map required columns
#     colnames = {}
#     if IAR_COL_IDX < df.shape[1]:        colnames[IAR_COL_IDX] = "IAR"
#     if RESP_COL_IDX < df.shape[1]:       colnames[RESP_COL_IDX] = "RespTime"
#     if SEL_MODELS_COL_IDX < df.shape[1]: colnames[SEL_MODELS_COL_IDX] = "selected_models"
#     if MODEL_SIZE_IDX < df.shape[1]:     colnames[MODEL_SIZE_IDX] = "ModelSize"
#     df = df.rename(columns=colnames)
#
#     # Policy extraction
#     df["main_policy"] = [ _extract_policy_from_tail(list(r)) for _, r in df.iterrows() ]
#     df["main_policy"] = df["main_policy"].astype(str).str.lower().replace({"": "mode_s"}).fillna("mode_s")
#
#     # Model size
#     if "ModelSize" in df.columns:
#         ms_num = pd.to_numeric(df["ModelSize"], errors="coerce")
#     else:
#         ms_num = pd.Series([np.nan] * len(df))
#     need_derive = ms_num.isna() | (ms_num <= 0)
#     if "selected_models" in df.columns and need_derive.any():
#         parsed = df.loc[need_derive, "selected_models"].apply(_parse_models_cell)
#         ms_num.loc[need_derive] = parsed.apply(len).astype(float)
#     df["ModelSize"] = ms_num
#
#     return df
#
# def load_logs(pattern: str) -> pd.DataFrame:
#     files = glob.glob(pattern)
#     if not files:
#         raise SystemExit(f"No CSV files found for pattern:\n{pattern}")
#     frames = [_read_csv_lenient_any_schema(f) for f in files]
#     return pd.concat(frames, ignore_index=True)
#
# def aggregate_by_maxsize(df: pd.DataFrame, success_only: bool = True) -> pd.DataFrame:
#     if success_only and "Success" in df.columns:
#         df = df[df["Success"] == True].copy()
#     for col in ("IAR", "RespTime", "ModelSize"):
#         if col not in df.columns:
#             raise ValueError(f"Missing required column '{col}' in CSV.")
#         df[col] = pd.to_numeric(df[col], errors="coerce")
#     df = df.dropna(subset=["IAR", "RespTime", "ModelSize"])
#     df = df[df["ModelSize"] > 0]
#     df["resp_time_ms"] = df["RespTime"] * 1000.0
#     df["arrival_rate"] = 1000.0 / df["IAR"]
#
#     grouped = df.groupby(["IAR", "ModelSize", "main_policy"], dropna=False).agg(
#         mean_latency_ms=("resp_time_ms", "mean"),
#         std_latency_ms=("resp_time_ms", "std"),
#         n=("resp_time_ms", "count"),
#         arrival_rate=("arrival_rate", "mean"),
#     ).reset_index()
#     grouped["sem_latency_ms"] = grouped["std_latency_ms"] / np.sqrt(grouped["n"].clip(lower=1))
#     grouped["sem_latency_ms"] = grouped["sem_latency_ms"].fillna(0.0)
#     grouped["std_latency_ms"] = grouped["std_latency_ms"].fillna(0.0)
#     grouped = grouped.sort_values(["main_policy", "ModelSize", "arrival_rate"]).reset_index(drop=True)
#     print("[INFO] Lines to plot (policy, size → #points):")
#     for (pol, ms), sub in grouped.groupby(["main_policy", "ModelSize"]):
#         print(f"  - {pol}, size {int(ms)} → {len(sub)} points")
#     return grouped
#
# def _label_for(pol: str, ms: float) -> str:
#     ms_int = int(ms)
#     p = (pol or "mode_s").lower()
#     if ms_int == 1:
#         return "Fastest model"
#     if p == "randomized":
#         return f"Random model set size {ms_int}"
#     if p in {"greedy", "mode_s", "mode-s", "modes"}:
#         return f"MODE-S max model set size {ms_int}"
#     return f"{p} size {ms_int}"
#
# def plot(grouped: pd.DataFrame, out_png: str) -> None:
#     fig, ax = plt.subplots()
#     ymin = max(grouped["mean_latency_ms"].min(), 1e-6)
#     ymax = grouped["mean_latency_ms"].max()
#     use_log = (ymax / ymin) > 20 if ymin > 0 else True
#
#     for (pol, ms), sub in grouped.groupby(["main_policy", "ModelSize"]):
#         sub = sub.sort_values("arrival_rate")
#         y = sub["mean_latency_ms"].to_numpy()
#         yerr = sub["sem_latency_ms"].to_numpy()
#         if use_log:
#             y = np.maximum(y, 1e-6)
#             yerr = np.minimum(yerr, 0.9 * y)
#
#         label_txt = _label_for(pol, ms).strip()
#         # only dashed for "Fastest model" and "Ensemble size …"
#         dashed = (
#             label_txt.lower().startswith("fastest model")
#             or label_txt.lower().startswith("random ensemble size")
#         )
#
#         ax.errorbar(
#             sub["arrival_rate"],
#             y,
#             yerr=yerr,
#             fmt="o",
#             linestyle="--" if dashed else "-",   # dashed vs solid
#             capsize=3,
#             elinewidth=1,
#             linewidth=2.0 if int(ms) == 1 else 1.5,
#             label=label_txt,
#             alpha=0.95,
#         )
#
#     ax.set_xlabel("Arrival Rate (requests/second)")
#     ax.set_ylabel("Average Latency (ms)")
#     ax.set_title("Average Latency vs Arrival Rate by Model Set Size")
#     ax.grid(True, linestyle="--", alpha=0.5)
#     ax.legend(ncol=1, fontsize=9)
#     fig.tight_layout()
#     fig.savefig(out_png, dpi=200)
#     fig.show()
#     print(f"[OK] Plot saved to: {out_png}")
#
# def main():
#     df = load_logs(LOG_PATH_PATTERN)
#     grouped = aggregate_by_maxsize(df, success_only=True)
#     grouped.to_csv(OUT_CSV, index=False)
#     print(f"[OK] Aggregated CSV saved to: {OUT_CSV}")
#     plot(grouped, OUT_PNG)
#
# if __name__ == "__main__":
#     main()




import ast
import csv
import glob
import os
from typing import List

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ---- Adjust this to your folder/pattern ----
LOG_PATH_PATTERN = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/avg_latency_vs_arrival_seq.csv"
OUT_CSV = "avg_latency_vs_arrival_by_maxsize_resp.csv"
OUT_PNG = "avg_latency_vs_arrival_by_maxsize_resp.png"

# Fixed positional columns in your logger (0-based)
IAR_COL_IDX        = 2   # IAR (ms)
RESP_COL_IDX       = 3   # RespTime (s)
SEL_MODELS_COL_IDX = 5   # selected_models (stringified list)
MODEL_SIZE_IDX     = 13  # ensemble_size in updated logs


def _parse_models_cell(x):
    """Parse selected_models like "['vit_b_16','resnet50']" to a list."""
    if x is None:
        return []
    if isinstance(x, list):
        return x
    sx = str(x).strip()
    try:
        val = ast.literal_eval(sx)
        if isinstance(val, (list, tuple)):
            return list(val)
    except Exception:
        pass
    return [m for m in pd.Series(sx).str.findall(r"[\"']([^\"']+)[\"']").sum()]


def _single_model_name(selected_models_cell):
    """
    Only meaningful when the selected model set size is 1.
    """
    models = _parse_models_cell(selected_models_cell)
    if len(models) == 1:
        return models[0]
    return ""


def _lenient_csv_read(path: str) -> List[List[str]]:
    rows: List[List[str]] = []
    with open(path, "r", newline="") as f:
        rdr = csv.reader(f)
        for row in rdr:
            rows.append(row)
    return rows


def _extract_policy_from_tail(row: List[str]) -> str:
    """Detect policy name from row cells near the end."""
    def is_number(s: str) -> bool:
        try:
            float(s)
            return True
        except Exception:
            return False

    known_policies = {
        "randomized", "greedy", "mode_s", "mode-s", "modes",
        "best_acc_1", "best_acc_2", "best_acc_3"
    }

    for cell in reversed(row[-10:]):
        cell = (cell or "").strip().lower()
        if not cell or is_number(cell):
            continue
        cell = cell.replace(" ", "_")
        if cell in known_policies:
            return cell

    return "mode_s"


def _read_csv_lenient_any_schema(path: str) -> pd.DataFrame:
    rows = _lenient_csv_read(path)
    max_cols = max(len(r) for r in rows) if rows else 0
    norm_rows = [r + [""] * (max_cols - len(r)) for r in rows]
    df = pd.DataFrame(norm_rows)

    # Map required columns
    colnames = {}
    if IAR_COL_IDX < df.shape[1]:
        colnames[IAR_COL_IDX] = "IAR"
    if RESP_COL_IDX < df.shape[1]:
        colnames[RESP_COL_IDX] = "RespTime"
    if SEL_MODELS_COL_IDX < df.shape[1]:
        colnames[SEL_MODELS_COL_IDX] = "selected_models"
    if MODEL_SIZE_IDX < df.shape[1]:
        colnames[MODEL_SIZE_IDX] = "ModelSize"

    df = df.rename(columns=colnames)

    # Policy extraction
    df["main_policy"] = [_extract_policy_from_tail(list(r)) for _, r in df.iterrows()]
    df["main_policy"] = (
        df["main_policy"]
        .astype(str)
        .str.lower()
        .replace({"": "mode_s"})
        .fillna("mode_s")
    )

    # ModelSize comes from ensemble_size column in the log
    if "ModelSize" in df.columns:
        ms_num = pd.to_numeric(df["ModelSize"], errors="coerce")
    else:
        ms_num = pd.Series([np.nan] * len(df))

    # Fallback only if ensemble_size is missing/invalid
    need_derive = ms_num.isna() | (ms_num <= 0)
    if "selected_models" in df.columns and need_derive.any():
        parsed = df.loc[need_derive, "selected_models"].apply(_parse_models_cell)
        ms_num.loc[need_derive] = parsed.apply(len).astype(float)

    df["ModelSize"] = ms_num

    # Keep actual model name only for size==1
    if "selected_models" in df.columns:
        df["single_model_name"] = df["selected_models"].apply(_single_model_name)
    else:
        df["single_model_name"] = ""

    # IMPORTANT FIX:
    # For ModelSize >= 2, do not group by model name.
    # Otherwise, you get multiple lines for the same ensemble size.
    df["plot_model_name"] = np.where(df["ModelSize"] == 1, df["single_model_name"], "")

    return df


def load_logs(pattern: str) -> pd.DataFrame:
    files = glob.glob(pattern)
    if not files:
        raise SystemExit(f"No CSV files found for pattern:\n{pattern}")
    frames = [_read_csv_lenient_any_schema(f) for f in files]
    return pd.concat(frames, ignore_index=True)


def aggregate_by_maxsize(df: pd.DataFrame, success_only: bool = True) -> pd.DataFrame:
    if success_only and "Success" in df.columns:
        df = df[df["Success"] == True].copy()

    for col in ("IAR", "RespTime", "ModelSize"):
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in CSV.")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["IAR", "RespTime", "ModelSize"])
    df = df[df["ModelSize"] > 0]

    df["resp_time_ms"] = df["RespTime"] * 1000.0
    df["arrival_rate"] = 1000.0 / df["IAR"]

    grouped = df.groupby(
        ["IAR", "ModelSize", "main_policy", "plot_model_name"],
        dropna=False
    ).agg(
        mean_latency_ms=("resp_time_ms", "mean"),
        std_latency_ms=("resp_time_ms", "std"),
        n=("resp_time_ms", "count"),
        arrival_rate=("arrival_rate", "mean"),
    ).reset_index()

    grouped["sem_latency_ms"] = grouped["std_latency_ms"] / np.sqrt(grouped["n"].clip(lower=1))
    grouped["sem_latency_ms"] = grouped["sem_latency_ms"].fillna(0.0)
    grouped["std_latency_ms"] = grouped["std_latency_ms"].fillna(0.0)

    grouped = grouped.sort_values(
        ["main_policy", "ModelSize", "plot_model_name", "arrival_rate"]
    ).reset_index(drop=True)

    print("[INFO] Lines to plot (policy, size, plot_model_name → #points):")
    for (pol, ms, plot_model_name), sub in grouped.groupby(
        ["main_policy", "ModelSize", "plot_model_name"]
    ):
        name_txt = plot_model_name if str(plot_model_name).strip() else "-"
        print(f"  - {pol}, size {int(ms)}, model {name_txt} → {len(sub)} points")

    return grouped


def _label_for(pol: str, ms: float, plot_model_name: str = "") -> str:
    """
    Label rule:
    - If size == 1: show actual model name
    - If size >= 2: show maximum model set size X
    """
    ms_int = int(ms)
    p = (pol or "mode_s").lower()
    name = str(plot_model_name).strip()

    if ms_int == 1:
        return name if name else "Single model"

    if p == "randomized":
        return f"Random maximum model set size {ms_int}"

    if p in {"greedy", "mode_s", "mode-s", "modes"}:
        return f"Sequential Case - model set size {ms_int}"
        # return f"Power of Two Choices Case - model set size {ms_int}"

    if p == "best_acc_1":
        return name if name else "Best-accuracy model"

    if p in {"best_acc_2", "best_acc_3"}:
        return f"Best-accuracy maximum model set size {ms_int}"

    return f"{p} maximum model set size {ms_int}"


def plot(grouped: pd.DataFrame, out_png: str) -> None:
    fig, ax = plt.subplots()

    ymin = max(grouped["mean_latency_ms"].min(), 1e-6)
    ymax = grouped["mean_latency_ms"].max()
    use_log = (ymax / ymin) > 20 if ymin > 0 else True

    for (pol, ms, plot_model_name), sub in grouped.groupby(
        ["main_policy", "ModelSize", "plot_model_name"]
    ):
        sub = sub.sort_values("arrival_rate")

        y = sub["mean_latency_ms"].to_numpy()
        yerr = sub["sem_latency_ms"].to_numpy()

        if use_log:
            y = np.maximum(y, 1e-6)
            yerr = np.minimum(yerr, 0.9 * y)

        label_txt = _label_for(pol, ms, plot_model_name).strip()

        p = (pol or "").lower()
        is_single = int(ms) == 1
        is_random = p == "randomized"
        is_bestacc = p in {"best_acc_1", "best_acc_2", "best_acc_3"}

        dashed = is_single or is_random or is_bestacc

        ax.errorbar(
            sub["arrival_rate"],
            y,
            yerr=yerr,
            fmt="o",
            linestyle="--" if dashed else "-",
            capsize=3,
            elinewidth=1,
            linewidth=2.0 if is_single else 1.5,
            label=label_txt,
            alpha=0.95,
        )

    ax.set_xlabel("Arrival Rate (requests/second)")
    ax.set_ylabel("Average Latency (ms)")
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.legend(ncol=1, fontsize=9)
    fig.tight_layout()
    fig.savefig(out_png, dpi=200)
    fig.show()
    print(f"[OK] Plot saved to: {out_png}")


def main():
    df = load_logs(LOG_PATH_PATTERN)
    grouped = aggregate_by_maxsize(df, success_only=True)
    grouped.to_csv(OUT_CSV, index=False)
    print(f"[OK] Aggregated CSV saved to: {OUT_CSV}")
    plot(grouped, OUT_PNG)


if __name__ == "__main__":
    main()


