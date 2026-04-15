# #!/usr/bin/env python3
#
# import ast
# import csv
# import math
# import os
# from dataclasses import dataclass
# from typing import List, Optional
#
# import matplotlib.pyplot as plt
#
#
# # --------------------------------------------------
# # User paths: update these three files
# # --------------------------------------------------
# MODE_S_FILE = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/acc_and_latency_model_selec_MODE_S.csv"
# SEQUENTIAL_FILE = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/acc_and_latency_model_selec_seq.csv"
# POWER2_FILE = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/acc_and_latency_model_selec_power2.csv"
#
# OUTPUT_DIR = "policy_plots"
# DEADLINE_SEC = 0.5  # change if needed
#
#
# # --------------------------------------------------
# # Data row
# # --------------------------------------------------
# @dataclass
# class LogRow:
#     step: int
#     req_id: str
#     mode: str
#     e2e_ms: float
#     selected_est_latency_s: float
#     selected_models: List[str]
#     executed_models: List[str]
#     predicted_label: str
#     confidence: float
#     success: bool
#     stop_reason: str
#     alpha: Optional[float] = None
#     selection_strategy: Optional[str] = None
#     extra_qps: Optional[float] = None
#     alpha_mode: Optional[str] = None
#
#
# # --------------------------------------------------
# # Helpers
# # --------------------------------------------------
# def ensure_dir(path: str) -> None:
#     os.makedirs(path, exist_ok=True)
#
#
# def safe_float(x, default=math.nan) -> float:
#     try:
#         return float(x)
#     except Exception:
#         return default
#
#
# def safe_bool(x) -> bool:
#     return str(x).strip().lower() == "true"
#
#
# def safe_list(x) -> List[str]:
#     try:
#         val = ast.literal_eval(x)
#         if isinstance(val, list):
#             return [str(v) for v in val]
#         return []
#     except Exception:
#         return []
#
#
# def label_models(models: List[str]) -> str:
#     return "[" + ", ".join(models) + "]"
#
#
# def read_log_file(filepath: str, mode_name: str) -> List[LogRow]:
#     rows: List[LogRow] = []
#
#     with open(filepath, "r", newline="") as f:
#         reader = csv.reader(f)
#         for idx, row in enumerate(reader, start=1):
#             if not row:
#                 continue
#
#             # Skip header if present
#             if row[0].lower().startswith("req") is False and row[0].lower() != "request_id":
#                 # still allow data rows that begin with REQ-...
#                 pass
#
#             if len(row) < 12:
#                 print(f"Skipping short row in {filepath}: {row}")
#                 continue
#
#             req_id = row[0]
#             e2e_ms = safe_float(row[3])
#             selected_est_latency_s = safe_float(row[4])
#             selected_models = safe_list(row[5])
#             executed_models = safe_list(row[6])
#             predicted_label = row[7] if len(row) > 7 else ""
#             confidence = safe_float(row[8])
#             success = safe_bool(row[11]) if len(row) > 11 else False
#             stop_reason = row[17] if len(row) > 17 else ""
#
#             alpha = safe_float(row[18]) if len(row) > 18 else math.nan
#             selection_strategy = row[19] if len(row) > 19 else ""
#             extra_qps = safe_float(row[20]) if len(row) > 20 else math.nan
#             alpha_mode = row[21] if len(row) > 21 else ""
#
#             rows.append(
#                 LogRow(
#                     step=idx,
#                     req_id=req_id,
#                     mode=mode_name,
#                     e2e_ms=e2e_ms,
#                     selected_est_latency_s=selected_est_latency_s,
#                     selected_models=selected_models,
#                     executed_models=executed_models,
#                     predicted_label=predicted_label,
#                     confidence=confidence,
#                     success=success,
#                     stop_reason=stop_reason,
#                     alpha=alpha,
#                     selection_strategy=selection_strategy,
#                     extra_qps=extra_qps,
#                     alpha_mode=alpha_mode,
#                 )
#             )
#
#     return rows
#
#
# # --------------------------------------------------
# # Plot 1: selected estimated latency over time
# # --------------------------------------------------
# def plot_selected_latency_over_time(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
#     deadline_s: float,
# ) -> None:
#     plt.figure(figsize=(12, 6))
#
#     for rows, mode_name in [
#         (mode_s_rows, "mode_s"),
#         (seq_rows, "sequential"),
#         (p2_rows, "power_of_two_choices"),
#     ]:
#         xs = [r.step for r in rows]
#         ys = [r.selected_est_latency_s for r in rows]
#         plt.plot(xs, ys, marker="o", label=mode_name)
#
#     plt.axhline(deadline_s, linestyle="--", label=f"deadline={deadline_s:.3f}s")
#     plt.xlabel("Request / step index")
#     plt.ylabel("Selected estimated latency (s)")
#     plt.title("Selected estimated latency over time")
#     plt.legend()
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# # --------------------------------------------------
# # Plot 2: selected ensemble over time
# # --------------------------------------------------
# def plot_selected_ensemble_over_time(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
# ) -> None:
#     all_rows = mode_s_rows + seq_rows + p2_rows
#     labels = sorted({label_models(r.selected_models) for r in all_rows})
#     label_to_id = {lab: i for i, lab in enumerate(labels)}
#
#     modes = [
#         ("mode_s", mode_s_rows),
#         ("sequential", seq_rows),
#         ("power_of_two_choices", p2_rows),
#     ]
#
#     fig, axes = plt.subplots(len(modes), 1, figsize=(14, 10), sharex=True)
#
#     for ax, (mode_name, rows) in zip(axes, modes):
#         xs = [r.step for r in rows]
#         ys = [label_to_id[label_models(r.selected_models)] for r in rows]
#
#         ax.plot(xs, ys, marker="o")
#         ax.set_title(f"Selected ensemble over time: {mode_name}")
#         ax.set_yticks(range(len(labels)))
#         ax.set_yticklabels(labels)
#
#     axes[-1].set_xlabel("Request / step index")
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# # --------------------------------------------------
# # Plot 3: confidence over time
# # --------------------------------------------------
# def plot_confidence_over_time(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
# ) -> None:
#     plt.figure(figsize=(12, 6))
#
#     for rows, mode_name in [
#         (mode_s_rows, "mode_s"),
#         (seq_rows, "sequential"),
#         (p2_rows, "power_of_two_choices"),
#     ]:
#         xs = [r.step for r in rows]
#         ys = [r.confidence for r in rows]
#         plt.plot(xs, ys, marker="o", label=mode_name)
#
#     plt.xlabel("Request / step index")
#     plt.ylabel("Confidence")
#     plt.title("Confidence over time")
#     plt.legend()
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# # --------------------------------------------------
# # Optional: plot actual e2e latency too
# # --------------------------------------------------
# def plot_e2e_latency_over_time(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
#     deadline_s: float,
# ) -> None:
#     plt.figure(figsize=(12, 6))
#
#     for rows, mode_name in [
#         (mode_s_rows, "mode_s"),
#         (seq_rows, "sequential"),
#         (p2_rows, "power_of_two_choices"),
#     ]:
#         xs = [r.step for r in rows]
#         ys = [r.e2e_ms / 1000.0 for r in rows]
#         plt.plot(xs, ys, marker="o", label=mode_name)
#
#     plt.axhline(deadline_s, linestyle="--", label=f"deadline={deadline_s:.3f}s")
#     plt.xlabel("Request / step index")
#     plt.ylabel("Actual e2e latency (s)")
#     plt.title("Actual e2e latency over time")
#     plt.legend()
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# # --------------------------------------------------
# # Save merged CSV
# # --------------------------------------------------
# def write_merged_csv(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
# ) -> None:
#     all_rows = mode_s_rows + seq_rows + p2_rows
#     all_rows.sort(key=lambda r: (r.step, r.mode))
#
#     with open(output_path, "w", newline="") as f:
#         writer = csv.writer(f)
#         writer.writerow([
#             "step",
#             "req_id",
#             "mode",
#             "selected_models",
#             "executed_models",
#             "predicted_label",
#             "confidence",
#             "selected_est_latency_s",
#             "e2e_ms",
#             "success",
#             "stop_reason",
#             "alpha",
#             "selection_strategy",
#             "extra_qps",
#             "alpha_mode",
#         ])
#
#         for r in all_rows:
#             writer.writerow([
#                 r.step,
#                 r.req_id,
#                 r.mode,
#                 r.selected_models,
#                 r.executed_models,
#                 r.predicted_label,
#                 r.confidence,
#                 r.selected_est_latency_s,
#                 r.e2e_ms,
#                 r.success,
#                 r.stop_reason,
#                 r.alpha,
#                 r.selection_strategy,
#                 r.extra_qps,
#                 r.alpha_mode,
#             ])
#
#
# # --------------------------------------------------
# # Main
# # --------------------------------------------------
# def main():
#     ensure_dir(OUTPUT_DIR)
#
#     mode_s_rows = read_log_file(MODE_S_FILE, "mode_s")
#     seq_rows = read_log_file(SEQUENTIAL_FILE, "sequential")
#     p2_rows = read_log_file(POWER2_FILE, "power_of_two_choices")
#
#     print(f"Loaded mode_s rows: {len(mode_s_rows)}")
#     print(f"Loaded sequential rows: {len(seq_rows)}")
#     print(f"Loaded power_of_two_choices rows: {len(p2_rows)}")
#
#     write_merged_csv(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "merged_policy_log.csv"),
#     )
#
#     plot_selected_latency_over_time(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "selected_est_latency_over_time.png"),
#         DEADLINE_SEC,
#     )
#
#     plot_selected_ensemble_over_time(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "selected_ensemble_over_time.png"),
#     )
#
#     plot_confidence_over_time(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "confidence_over_time.png"),
#     )
#
#     plot_e2e_latency_over_time(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "e2e_latency_over_time.png"),
#         DEADLINE_SEC,
#     )
#
#     print(f"Done. Output files are in: {os.path.abspath(OUTPUT_DIR)}")
#
#
# if __name__ == "__main__":
#     main()



#!/usr/bin/env python3

# import ast
# import csv
# import json
# import math
# import os
# import re
# import textwrap
# from dataclasses import dataclass
# from typing import Dict, List, Optional
#
# import matplotlib.pyplot as plt
#
#
# # --------------------------------------------------
# # User paths
# # --------------------------------------------------
# MODE_S_FILE = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/acc_and_latency_model_selec_MODE_S.csv"
# SEQUENTIAL_FILE = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/acc_and_latency_model_selec_seq.csv"
# POWER2_FILE = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/acc_and_latency_model_selec_power2.csv"
#
# # update this path
# LABEL_JSON_FILE = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/Labels.json"
#
# OUTPUT_DIR = "policy_plots"
# DEADLINE_SEC = 2.0
#
#
# # --------------------------------------------------
# # Data row
# # --------------------------------------------------
# @dataclass
# class LogRow:
#     step: int
#     req_id: str
#     mode: str
#     response_time_s: float
#     current_time_sec: float
#     selected_models: List[str]
#     executed_models: List[str]
#     predicted_label: str
#     confidence: float
#     combiner: str
#     e2e_ms: float
#     success: bool
#     ground_truth_folder: str
#     stop_reason: str
#     qps_est: Optional[float] = None
#     alpha: Optional[float] = None
#     alpha_mode: Optional[str] = None
#     selected_est_latency_s: Optional[float] = None
#     is_correct: Optional[int] = None
#
#
# # --------------------------------------------------
# # Helpers
# # --------------------------------------------------
# def ensure_dir(path: str) -> None:
#     os.makedirs(path, exist_ok=True)
#
#
# def safe_float(x, default=math.nan) -> float:
#     try:
#         return float(x)
#     except Exception:
#         return default
#
#
# def safe_bool(x) -> bool:
#     return str(x).strip().lower() == "true"
#
#
# def safe_list(x) -> List[str]:
#     try:
#         val = ast.literal_eval(x)
#         if isinstance(val, list):
#             return [str(v) for v in val]
#         return []
#     except Exception:
#         return []
#
#
# def label_models(models: List[str]) -> str:
#     return "[" + ", ".join(models) + "]"
#
#
# def normalize_label(text: str) -> str:
#     if text is None:
#         return ""
#     text = str(text).strip().lower()
#     text = text.replace("_", " ")
#     text = re.sub(r"\s+", " ", text)
#     return text
#
#
# def load_label_map(json_path: str) -> Dict[str, List[str]]:
#     with open(json_path, "r") as f:
#         raw = json.load(f)
#
#     label_map: Dict[str, List[str]] = {}
#     for wnid, value in raw.items():
#         if isinstance(value, str):
#             synonyms = [normalize_label(x) for x in value.split(",")]
#             synonyms = [x for x in synonyms if x]
#             label_map[str(wnid)] = synonyms
#         else:
#             label_map[str(wnid)] = []
#
#     return label_map
#
#
# def is_prediction_correct(predicted_label: str, ground_truth_folder: str, label_map: Dict[str, List[str]]) -> int:
#     pred = normalize_label(predicted_label)
#     gt_folder = str(ground_truth_folder).strip()
#
#     if not pred or not gt_folder:
#         return 0
#
#     gt_labels = label_map.get(gt_folder, [])
#     return 1 if pred in gt_labels else 0
#
#
# # --------------------------------------------------
# # Read CSV
# # --------------------------------------------------
# def read_log_file(filepath: str, mode_name: str, label_map: Dict[str, List[str]]) -> List[LogRow]:
#     rows: List[LogRow] = []
#
#     with open(filepath, "r", newline="") as f:
#         reader = csv.reader(f)
#
#         for row in reader:
#             if not row:
#                 continue
#
#             first_col = row[0].strip().lower()
#
#             # skip header
#             if first_col in ("req_id", "request_id"):
#                 continue
#
#             if len(row) < 22:
#                 print(f"Skipping short row in {filepath}: {row}")
#                 continue
#
#             req_id = row[0]
#             response_time_s = safe_float(row[3])       # client response time in seconds
#             current_time_sec = safe_float(row[4])
#             selected_models = safe_list(row[5])
#             executed_models = safe_list(row[6])
#             predicted_label = row[7] if len(row) > 7 else ""
#             confidence = safe_float(row[8])
#             combiner = row[9] if len(row) > 9 else ""
#             e2e_ms = safe_float(row[10])              # server-side e2e in ms
#             success = safe_bool(row[11]) if len(row) > 11 else False
#             ground_truth_folder = row[12] if len(row) > 12 else ""
#             stop_reason = row[17] if len(row) > 17 else ""
#             qps_est = safe_float(row[18]) if len(row) > 18 else math.nan
#             alpha = safe_float(row[20]) if len(row) > 20 else math.nan
#             alpha_mode = row[21] if len(row) > 21 else ""
#             selected_est_latency_s = safe_float(row[-1]) if len(row) > 22 else math.nan
#
#             correct = is_prediction_correct(predicted_label, ground_truth_folder, label_map)
#
#             rows.append(
#                 LogRow(
#                     step=len(rows) + 1,
#                     req_id=req_id,
#                     mode=mode_name,
#                     response_time_s=response_time_s,
#                     current_time_sec=current_time_sec,
#                     selected_models=selected_models,
#                     executed_models=executed_models,
#                     predicted_label=predicted_label,
#                     confidence=confidence,
#                     combiner=combiner,
#                     e2e_ms=e2e_ms,
#                     success=success,
#                     ground_truth_folder=ground_truth_folder,
#                     stop_reason=stop_reason,
#                     qps_est=qps_est,
#                     alpha=alpha,
#                     alpha_mode=alpha_mode,
#                     selected_est_latency_s=selected_est_latency_s,
#                     is_correct=correct,
#                 )
#             )
#
#     return rows
#
#
# # --------------------------------------------------
# # Plot 1: selected estimated latency over time
# # this is the graph style you said looks nice
# # --------------------------------------------------
# def plot_selected_estimated_latency_over_time(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
#     deadline_s: float,
# ) -> None:
#     plt.figure(figsize=(16, 7))
#
#     for rows, mode_name in [
#         (mode_s_rows, "mode_s"),
#         (seq_rows, "sequential"),
#         (p2_rows, "power_of_two_choices"),
#     ]:
#         xs = [r.step for r in rows]
#         ys = [r.selected_est_latency_s for r in rows]
#         plt.plot(xs, ys, marker="o", label=mode_name)
#
#     plt.axhline(deadline_s, linestyle="--", label=f"deadline={deadline_s:.3f}s")
#     plt.xlabel("Request / step index")
#     plt.ylabel("Selected estimated latency (s)")
#     plt.title("Selected estimated latency over time")
#     plt.legend()
#     plt.grid(True, alpha=0.3)
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# # --------------------------------------------------
# # Plot 2: actual client response time over time
# # --------------------------------------------------
# def plot_actual_response_time_over_time(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
#     deadline_s: float,
# ) -> None:
#     plt.figure(figsize=(16, 7))
#
#     for rows, mode_name in [
#         (mode_s_rows, "mode_s"),
#         (seq_rows, "sequential"),
#         (p2_rows, "power_of_two_choices"),
#     ]:
#         xs = [r.step for r in rows]
#         ys = [r.response_time_s for r in rows]
#         plt.plot(xs, ys, marker="o", label=mode_name)
#
#     plt.axhline(deadline_s, linestyle="--", label=f"deadline={deadline_s:.3f}s")
#     plt.xlabel("Request / step index")
#     plt.ylabel("Actual client response time (s)")
#     plt.title("Actual client response time over time")
#     plt.legend()
#     plt.grid(True, alpha=0.3)
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# # --------------------------------------------------
# # Plot 3: correctness over time (0/1)
# # one subplot per policy so it stays clear
# # --------------------------------------------------
# def plot_correctness_over_time(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
# ) -> None:
#     modes = [
#         ("mode_s", mode_s_rows),
#         ("sequential", seq_rows),
#         ("power_of_two_choices", p2_rows),
#     ]
#
#     fig, axes = plt.subplots(len(modes), 1, figsize=(14, 8), sharex=True)
#
#     if len(modes) == 1:
#         axes = [axes]
#
#     for ax, (mode_name, rows) in zip(axes, modes):
#         xs = [r.step for r in rows]
#         ys = [r.is_correct for r in rows]
#
#         ax.plot(xs, ys, marker="o")
#         ax.set_title(f"Prediction correctness over time: {mode_name}")
#         ax.set_ylabel("Correct")
#         ax.set_yticks([0, 1])
#         ax.set_yticklabels(["Wrong", "Correct"])
#         ax.grid(True, alpha=0.3)
#
#     axes[-1].set_xlabel("Request / step index")
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# # --------------------------------------------------
# # Plot 4: running accuracy over time
# # --------------------------------------------------
# def plot_running_accuracy_over_time(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
# ) -> None:
#     plt.figure(figsize=(16, 7))
#
#     for rows, mode_name in [
#         (mode_s_rows, "mode_s"),
#         (seq_rows, "sequential"),
#         (p2_rows, "power_of_two_choices"),
#     ]:
#         xs = []
#         ys = []
#         correct_so_far = 0
#
#         for i, r in enumerate(rows, start=1):
#             correct_so_far += int(r.is_correct)
#             xs.append(r.step)
#             ys.append(correct_so_far / i)
#
#         plt.plot(xs, ys, marker="o", label=mode_name)
#
#     plt.xlabel("Request / step index")
#     plt.ylabel("Running accuracy")
#     plt.title("Running accuracy over time")
#     plt.legend()
#     plt.grid(True, alpha=0.3)
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# # --------------------------------------------------
# # Plot 5: final accuracy summary
# # --------------------------------------------------
# def plot_final_accuracy_summary(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
# ) -> None:
#     data = [
#         ("mode_s", mode_s_rows),
#         ("sequential", seq_rows),
#         ("power_of_two_choices", p2_rows),
#     ]
#
#     names = []
#     accs = []
#
#     for name, rows in data:
#         names.append(name)
#         if rows:
#             acc = sum(int(r.is_correct) for r in rows) / len(rows)
#         else:
#             acc = 0.0
#         accs.append(acc)
#
#     plt.figure(figsize=(10, 6))
#     plt.bar(names, accs)
#     plt.ylabel("Final accuracy")
#     plt.title("Final accuracy summary by policy")
#     plt.ylim(0, 1.05)
#
#     for i, v in enumerate(accs):
#         plt.text(i, v + 0.02, f"{v:.3f}", ha="center")
#
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# # --------------------------------------------------
# # Plot 6: selected ensemble over time with names
# # --------------------------------------------------
# def plot_selected_ensemble_over_time_named_clean(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
# ) -> None:
#     modes = [
#         ("mode_s", mode_s_rows),
#         ("sequential", seq_rows),
#         ("power_of_two_choices", p2_rows),
#     ]
#
#     fig, axes = plt.subplots(len(modes), 1, figsize=(18, 12), sharex=True)
#
#     if len(modes) == 1:
#         axes = [axes]
#
#     for ax, (mode_name, rows) in zip(axes, modes):
#         labels = [label_models(r.selected_models) for r in rows]
#         unique_labels = sorted(set(labels))
#         label_to_id = {lab: i for i, lab in enumerate(unique_labels)}
#
#         xs = [r.step for r in rows]
#         ys = [label_to_id[label_models(r.selected_models)] for r in rows]
#
#         wrapped_labels = [textwrap.fill(lab, width=26) for lab in unique_labels]
#
#         ax.plot(xs, ys, marker="o")
#         ax.set_yticks(range(len(unique_labels)))
#         ax.set_yticklabels(wrapped_labels, fontsize=9)
#         ax.set_title(f"Selected ensemble over time: {mode_name}")
#         ax.set_ylabel("Selected ensemble")
#         ax.grid(True, axis="x", alpha=0.3)
#
#     axes[-1].set_xlabel("Request / step index")
#     plt.subplots_adjust(left=0.33, hspace=0.35)
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# # --------------------------------------------------
# # Plot 7: confidence over time
# # --------------------------------------------------
# def plot_confidence_over_time(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
# ) -> None:
#     plt.figure(figsize=(12, 6))
#
#     for rows, mode_name in [
#         (mode_s_rows, "mode_s"),
#         (seq_rows, "sequential"),
#         (p2_rows, "power_of_two_choices"),
#     ]:
#         xs = [r.step for r in rows]
#         ys = [r.confidence for r in rows]
#         plt.plot(xs, ys, marker="o", label=mode_name)
#
#     plt.xlabel("Request / step index")
#     plt.ylabel("Confidence")
#     plt.title("Confidence over time")
#     plt.legend()
#     plt.grid(True, alpha=0.3)
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# # --------------------------------------------------
# # Save merged CSV
# # --------------------------------------------------
# def write_merged_csv(
#     mode_s_rows: List[LogRow],
#     seq_rows: List[LogRow],
#     p2_rows: List[LogRow],
#     output_path: str,
# ) -> None:
#     all_rows = mode_s_rows + seq_rows + p2_rows
#     all_rows.sort(key=lambda r: (r.step, r.mode))
#
#     with open(output_path, "w", newline="") as f:
#         writer = csv.writer(f)
#         writer.writerow([
#             "step",
#             "req_id",
#             "mode",
#             "selected_models",
#             "executed_models",
#             "predicted_label",
#             "ground_truth_folder",
#             "is_correct",
#             "confidence",
#             "response_time_s",
#             "e2e_ms",
#             "selected_est_latency_s",
#             "success",
#             "stop_reason",
#             "qps_est",
#             "alpha",
#             "alpha_mode",
#         ])
#
#         for r in all_rows:
#             writer.writerow([
#                 r.step,
#                 r.req_id,
#                 r.mode,
#                 r.selected_models,
#                 r.executed_models,
#                 r.predicted_label,
#                 r.ground_truth_folder,
#                 r.is_correct,
#                 r.confidence,
#                 r.response_time_s,
#                 r.e2e_ms,
#                 r.selected_est_latency_s,
#                 r.success,
#                 r.stop_reason,
#                 r.qps_est,
#                 r.alpha,
#                 r.alpha_mode,
#             ])
#
#
# # --------------------------------------------------
# # Main
# # --------------------------------------------------
# def main():
#     ensure_dir(OUTPUT_DIR)
#
#     label_map = load_label_map(LABEL_JSON_FILE)
#
#     mode_s_rows = read_log_file(MODE_S_FILE, "mode_s", label_map)
#     seq_rows = read_log_file(SEQUENTIAL_FILE, "sequential", label_map)
#     p2_rows = read_log_file(POWER2_FILE, "power_of_two_choices", label_map)
#
#     print(f"Loaded mode_s rows: {len(mode_s_rows)}")
#     print(f"Loaded sequential rows: {len(seq_rows)}")
#     print(f"Loaded power_of_two_choices rows: {len(p2_rows)}")
#
#     write_merged_csv(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "merged_policy_log.csv"),
#     )
#
#     plot_selected_estimated_latency_over_time(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "selected_estimated_latency_over_time.png"),
#         DEADLINE_SEC,
#     )
#
#     plot_actual_response_time_over_time(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "actual_response_time_over_time.png"),
#         DEADLINE_SEC,
#     )
#
#     plot_correctness_over_time(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "correctness_over_time.png"),
#     )
#
#     plot_running_accuracy_over_time(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "running_accuracy_over_time.png"),
#     )
#
#     plot_final_accuracy_summary(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "final_accuracy_summary.png"),
#     )
#
#     plot_selected_ensemble_over_time_named_clean(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "selected_ensemble_over_time_named_clean.png"),
#     )
#
#     plot_confidence_over_time(
#         mode_s_rows,
#         seq_rows,
#         p2_rows,
#         os.path.join(OUTPUT_DIR, "confidence_over_time.png"),
#     )
#
#     print(f"Done. Output files are in: {os.path.abspath(OUTPUT_DIR)}")
#
#
# if __name__ == "__main__":
#     main()




#!/usr/bin/env python3

import ast
import csv
import json
import math
import os
import re
import textwrap
from dataclasses import dataclass
from typing import Dict, List, Optional

import matplotlib.pyplot as plt


# --------------------------------------------------
# User paths
# --------------------------------------------------
MODE_S_FILE = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/acc_and_latency_model_selec_MODE_S.csv"
SEQUENTIAL_FILE = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/acc_and_latency_model_selec_seq.csv"
POWER2_FILE = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/acc_and_latency_model_selec_power2.csv"

LABEL_JSON_FILE = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/Labels.json"

OUTPUT_DIR = "policy_plots"
DEADLINE_SEC = 2.0   # change if needed


# --------------------------------------------------
# Data row
# --------------------------------------------------
@dataclass
class LogRow:
    step: int
    req_id: str
    mode: str
    response_time_s: float
    current_time_sec: float
    selected_models: List[str]
    executed_models: List[str]
    predicted_label: str
    confidence: float
    combiner: str
    e2e_ms: float
    success: bool
    ground_truth_folder: str
    stop_reason: str
    qps_est: Optional[float] = None
    alpha: Optional[float] = None
    alpha_mode: Optional[str] = None
    selected_est_latency_s: Optional[float] = None
    is_correct: Optional[int] = None


# --------------------------------------------------
# Helpers
# --------------------------------------------------
def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def safe_float(x, default=math.nan) -> float:
    try:
        return float(x)
    except Exception:
        return default


def safe_bool(x) -> bool:
    return str(x).strip().lower() == "true"


def safe_list(x) -> List[str]:
    try:
        val = ast.literal_eval(x)
        if isinstance(val, list):
            return [str(v) for v in val]
        return []
    except Exception:
        return []


def label_models(models: List[str]) -> str:
    return "[" + ", ".join(models) + "]"


def normalize_label(text: str) -> str:
    if text is None:
        return ""
    text = str(text).strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def load_label_map(json_path: str) -> Dict[str, List[str]]:
    with open(json_path, "r") as f:
        raw = json.load(f)

    label_map: Dict[str, List[str]] = {}
    for wnid, value in raw.items():
        if isinstance(value, str):
            synonyms = [normalize_label(x) for x in value.split(",")]
            synonyms = [x for x in synonyms if x]
            label_map[str(wnid)] = synonyms
        else:
            label_map[str(wnid)] = []

    return label_map


def is_prediction_correct(predicted_label: str, ground_truth_folder: str, label_map: Dict[str, List[str]]) -> int:
    pred = normalize_label(predicted_label)
    gt_folder = str(ground_truth_folder).strip()

    if not pred or not gt_folder:
        return 0

    gt_labels = label_map.get(gt_folder, [])
    return 1 if pred in gt_labels else 0


# --------------------------------------------------
# Read CSV
# --------------------------------------------------
def read_log_file(filepath: str, mode_name: str, label_map: Dict[str, List[str]]) -> List[LogRow]:
    rows: List[LogRow] = []

    with open(filepath, "r", newline="") as f:
        reader = csv.reader(f)

        for row in reader:
            if not row:
                continue

            first_col = row[0].strip().lower()

            # skip header
            if first_col in ("req_id", "request_id"):
                continue

            if len(row) < 22:
                print(f"Skipping short row in {filepath}: {row}")
                continue

            req_id = row[0]
            response_time_s = safe_float(row[3])       # client response time
            current_time_sec = safe_float(row[4])
            selected_models = safe_list(row[5])
            executed_models = safe_list(row[6])
            predicted_label = row[7] if len(row) > 7 else ""
            confidence = safe_float(row[8])
            combiner = row[9] if len(row) > 9 else ""
            e2e_ms = safe_float(row[10])              # server e2e in ms
            success = safe_bool(row[11]) if len(row) > 11 else False
            ground_truth_folder = row[12] if len(row) > 12 else ""
            stop_reason = row[17] if len(row) > 17 else ""
            qps_est = safe_float(row[18]) if len(row) > 18 else math.nan
            alpha = safe_float(row[20]) if len(row) > 20 else math.nan
            alpha_mode = row[21] if len(row) > 21 else ""
            selected_est_latency_s = safe_float(row[-1]) if len(row) > 22 else math.nan

            correct = is_prediction_correct(predicted_label, ground_truth_folder, label_map)

            rows.append(
                LogRow(
                    step=len(rows) + 1,
                    req_id=req_id,
                    mode=mode_name,
                    response_time_s=response_time_s,
                    current_time_sec=current_time_sec,
                    selected_models=selected_models,
                    executed_models=executed_models,
                    predicted_label=predicted_label,
                    confidence=confidence,
                    combiner=combiner,
                    e2e_ms=e2e_ms,
                    success=success,
                    ground_truth_folder=ground_truth_folder,
                    stop_reason=stop_reason,
                    qps_est=qps_est,
                    alpha=alpha,
                    alpha_mode=alpha_mode,
                    selected_est_latency_s=selected_est_latency_s,
                    is_correct=correct,
                )
            )

    return rows


# --------------------------------------------------
# Plot 1: selected estimated latency over time
# --------------------------------------------------
def plot_selected_estimated_latency_over_time(
    mode_s_rows: List[LogRow],
    seq_rows: List[LogRow],
    p2_rows: List[LogRow],
    output_path: str,
    deadline_s: float,
) -> None:
    plt.figure(figsize=(16, 7))

    for rows, mode_name in [
        (mode_s_rows, "mode_s"),
        (seq_rows, "sequential"),
        (p2_rows, "power_of_two_choices"),
    ]:
        xs = [r.step for r in rows]
        ys = [r.selected_est_latency_s for r in rows]
        plt.plot(xs, ys, marker="o", label=mode_name)

    plt.axhline(deadline_s, linestyle="--", label=f"deadline={deadline_s:.3f}s")
    plt.xlabel("Request / step index")
    plt.ylabel("Selected estimated latency (s)")
    plt.title("Selected estimated latency over time")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


# --------------------------------------------------
# Plot 2: actual client response time over time
# --------------------------------------------------
def plot_actual_response_time_over_time(
    mode_s_rows: List[LogRow],
    seq_rows: List[LogRow],
    p2_rows: List[LogRow],
    output_path: str,
    deadline_s: float,
) -> None:
    plt.figure(figsize=(16, 7))

    for rows, mode_name in [
        (mode_s_rows, "mode_s"),
        (seq_rows, "sequential"),
        (p2_rows, "power_of_two_choices"),
    ]:
        xs = [r.step for r in rows]
        ys = [r.response_time_s for r in rows]
        plt.plot(xs, ys, marker="o", label=mode_name)

    plt.axhline(deadline_s, linestyle="--", label=f"deadline={deadline_s:.3f}s")
    plt.xlabel("Request / step index")
    plt.ylabel("Actual client response time (s)")
    plt.title("Actual client response time over time")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


# --------------------------------------------------
# Plot 3: correctness over time
# --------------------------------------------------
def plot_correctness_over_time(
    mode_s_rows: List[LogRow],
    seq_rows: List[LogRow],
    p2_rows: List[LogRow],
    output_path: str,
) -> None:
    modes = [
        ("mode_s", mode_s_rows),
        ("sequential", seq_rows),
        ("power_of_two_choices", p2_rows),
    ]

    fig, axes = plt.subplots(len(modes), 1, figsize=(14, 8), sharex=True)

    if len(modes) == 1:
        axes = [axes]

    for ax, (mode_name, rows) in zip(axes, modes):
        xs = [r.step for r in rows]
        ys = [r.is_correct for r in rows]

        ax.plot(xs, ys, marker="o")
        ax.set_title(f"Prediction correctness over time: {mode_name}")
        ax.set_ylabel("Correct")
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["Wrong", "Correct"])
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Request / step index")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


# --------------------------------------------------
# Plot 4: running accuracy over time
# --------------------------------------------------
def plot_running_accuracy_over_time(
    mode_s_rows: List[LogRow],
    seq_rows: List[LogRow],
    p2_rows: List[LogRow],
    output_path: str,
) -> None:
    plt.figure(figsize=(16, 7))

    for rows, mode_name in [
        (mode_s_rows, "mode_s"),
        (seq_rows, "sequential"),
        (p2_rows, "power_of_two_choices"),
    ]:
        xs = []
        ys = []
        correct_so_far = 0

        for i, r in enumerate(rows, start=1):
            correct_so_far += int(r.is_correct)
            xs.append(r.step)
            ys.append(correct_so_far / i)

        plt.plot(xs, ys, marker="o", label=mode_name)

    plt.xlabel("Request / step index")
    plt.ylabel("Running accuracy")
    plt.title("Running accuracy over time")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


# --------------------------------------------------
# Plot 5: final accuracy summary
# --------------------------------------------------
def plot_final_accuracy_summary(
    mode_s_rows: List[LogRow],
    seq_rows: List[LogRow],
    p2_rows: List[LogRow],
    output_path: str,
) -> None:
    data = [
        ("mode_s", mode_s_rows),
        ("sequential", seq_rows),
        ("power_of_two_choices", p2_rows),
    ]

    names = []
    accs = []

    for name, rows in data:
        names.append(name)
        acc = (sum(int(r.is_correct) for r in rows) / len(rows)) if rows else 0.0
        accs.append(acc)

    plt.figure(figsize=(10, 6))
    plt.bar(names, accs)
    plt.ylabel("Final accuracy")
    plt.title("Final accuracy summary by policy")
    plt.ylim(0, 1.05)

    for i, v in enumerate(accs):
        plt.text(i, v + 0.02, f"{v:.3f}", ha="center")

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


# --------------------------------------------------
# Plot 6/7/8: separate ensemble graphs
# --------------------------------------------------
def plot_single_ensemble_graph(rows, mode_name, output_path):
    import matplotlib.pyplot as plt

    plt.figure(figsize=(10, 3.5))

    labels = [label_models(r.selected_models) for r in rows]
    unique_labels = sorted(set(labels))
    label_to_id = {lab: i for i, lab in enumerate(unique_labels)}

    xs = [r.step for r in rows]
    ys = [label_to_id[label_models(r.selected_models)] for r in rows]

    # keep labels in one line
    single_line_labels = unique_labels

    plt.plot(xs, ys, marker="o", markersize=4, linewidth=1.2)

    plt.yticks(range(len(unique_labels)), single_line_labels, fontsize=8)

    plt.xlabel("Request / step index", fontsize=10)
    plt.ylabel("Selected ensemble", fontsize=10)
    plt.title(f"Selected ensemble over time: {mode_name}", fontsize=10)

    plt.grid(True, axis="x", alpha=0.3)

    # more space for long one-line labels
    plt.subplots_adjust(left=0.55)

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


# --------------------------------------------------
# Plot 9: confidence over time
# --------------------------------------------------
def plot_confidence_over_time(
    mode_s_rows: List[LogRow],
    seq_rows: List[LogRow],
    p2_rows: List[LogRow],
    output_path: str,
) -> None:
    plt.figure(figsize=(12, 6))

    for rows, mode_name in [
        (mode_s_rows, "mode_s"),
        (seq_rows, "sequential"),
        (p2_rows, "power_of_two_choices"),
    ]:
        xs = [r.step for r in rows]
        ys = [r.confidence for r in rows]
        plt.plot(xs, ys, marker="o", label=mode_name)

    plt.xlabel("Request / step index")
    plt.ylabel("Confidence")
    plt.title("Confidence over time")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


# --------------------------------------------------
# Save merged CSV
# --------------------------------------------------
def write_merged_csv(
    mode_s_rows: List[LogRow],
    seq_rows: List[LogRow],
    p2_rows: List[LogRow],
    output_path: str,
) -> None:
    all_rows = mode_s_rows + seq_rows + p2_rows
    all_rows.sort(key=lambda r: (r.step, r.mode))

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "step",
            "req_id",
            "mode",
            "selected_models",
            "executed_models",
            "predicted_label",
            "ground_truth_folder",
            "is_correct",
            "confidence",
            "response_time_s",
            "e2e_ms",
            "selected_est_latency_s",
            "success",
            "stop_reason",
            "qps_est",
            "alpha",
            "alpha_mode",
        ])

        for r in all_rows:
            writer.writerow([
                r.step,
                r.req_id,
                r.mode,
                r.selected_models,
                r.executed_models,
                r.predicted_label,
                r.ground_truth_folder,
                r.is_correct,
                r.confidence,
                r.response_time_s,
                r.e2e_ms,
                r.selected_est_latency_s,
                r.success,
                r.stop_reason,
                r.qps_est,
                r.alpha,
                r.alpha_mode,
            ])


# --------------------------------------------------
# Main
# --------------------------------------------------
def main():
    ensure_dir(OUTPUT_DIR)

    label_map = load_label_map(LABEL_JSON_FILE)

    mode_s_rows = read_log_file(MODE_S_FILE, "mode_s", label_map)
    seq_rows = read_log_file(SEQUENTIAL_FILE, "sequential", label_map)
    p2_rows = read_log_file(POWER2_FILE, "power_of_two_choices", label_map)

    print(f"Loaded mode_s rows: {len(mode_s_rows)}")
    print(f"Loaded sequential rows: {len(seq_rows)}")
    print(f"Loaded power_of_two_choices rows: {len(p2_rows)}")

    write_merged_csv(
        mode_s_rows,
        seq_rows,
        p2_rows,
        os.path.join(OUTPUT_DIR, "merged_policy_log.csv"),
    )

    plot_selected_estimated_latency_over_time(
        mode_s_rows,
        seq_rows,
        p2_rows,
        os.path.join(OUTPUT_DIR, "selected_estimated_latency_over_time.png"),
        DEADLINE_SEC,
    )

    plot_actual_response_time_over_time(
        mode_s_rows,
        seq_rows,
        p2_rows,
        os.path.join(OUTPUT_DIR, "actual_response_time_over_time.png"),
        DEADLINE_SEC,
    )

    plot_correctness_over_time(
        mode_s_rows,
        seq_rows,
        p2_rows,
        os.path.join(OUTPUT_DIR, "correctness_over_time.png"),
    )

    plot_running_accuracy_over_time(
        mode_s_rows,
        seq_rows,
        p2_rows,
        os.path.join(OUTPUT_DIR, "running_accuracy_over_time.png"),
    )

    plot_final_accuracy_summary(
        mode_s_rows,
        seq_rows,
        p2_rows,
        os.path.join(OUTPUT_DIR, "final_accuracy_summary.png"),
    )

    plot_single_ensemble_graph(
        mode_s_rows,
        "mode_s",
        os.path.join(OUTPUT_DIR, "ensemble_mode_s.png"),
    )

    plot_single_ensemble_graph(
        seq_rows,
        "sequential",
        os.path.join(OUTPUT_DIR, "ensemble_sequential.png"),
    )

    plot_single_ensemble_graph(
        p2_rows,
        "power_of_two_choices",
        os.path.join(OUTPUT_DIR, "ensemble_power2.png"),
    )

    plot_confidence_over_time(
        mode_s_rows,
        seq_rows,
        p2_rows,
        os.path.join(OUTPUT_DIR, "confidence_over_time.png"),
    )

    print(f"Done. Output files are in: {os.path.abspath(OUTPUT_DIR)}")


if __name__ == "__main__":
    main()