# #!/usr/bin/env python3
# """
# Dynamic analysis of ensemble selection over time.
#
# This script:
# 1. Loads real project config from ckn_controller.ckn_config
# 2. Repeatedly queries Iluvatar wait times (or uses zero waits)
# 3. For each step/request:
#    - selects a model set for mode_s
#    - selects a model set for sequential
#    - selects a model set for parallel_first_finish
#    - estimates selected latency
# 4. Saves a CSV log
# 5. Generates dynamic plots:
#    - estimated latency over requests
#    - mean wait over requests
#    - selected ensemble over requests
#    - deadline violation indicator over requests
#
# Run examples:
#     python dynamic_ensemble_selection_analysis.py
#     python dynamic_ensemble_selection_analysis.py --num-steps 100
#     python dynamic_ensemble_selection_analysis.py --poll-interval-sec 1.0
#     python dynamic_ensemble_selection_analysis.py --use-real-waits false
# """
#
# from __future__ import annotations
#
# import argparse
# import csv
# import math
# import os
# import time
# from dataclasses import dataclass
# from typing import Dict, List, Sequence
#
# import matplotlib.pyplot as plt
#
# from ckn_controller.ckn_config import (
#     M_TOTAL,
#     ENSEMBLE_SIZE,
#     MODEL_PROFILES,
#     NETWORK_LATENCY,
#     PARALLEL_FIRST_N,
#     ALPHA_STATIC,
#     SMALL_INSTANCE_MODELS,
#     LARGE_INSTANCE_MODELS,
#     SMALL_MODEL_SERVER_ADDRESS,
#     LARGE_MODEL_SERVER_ADDRESS,
#     SERVER_ADDRESS,
#     USE_TWO_ILUVATAR_INSTANCES,
# )
# from ckn_controller.ensemble_selector import (
#     build_model_set_by_mode,
#     estimate_selected_set_latency_for_mode,
# )
# import wait_time_iluvatar
#
#
# # =========================================================
# # Data structure
# # =========================================================
#
# @dataclass
# class StepRow:
#     step: int
#     mode: str
#     selected_models: List[str]
#     selected_est_latency_s: float
#     feasible: bool
#     deadline_s: float
#     mean_wait_s: float
#     max_wait_s: float
#     min_wait_s: float
#
#
# # =========================================================
# # Helpers
# # =========================================================
#
# def str2bool(value: str) -> bool:
#     return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}
#
#
# def ensure_dir(path: str) -> None:
#     os.makedirs(path, exist_ok=True)
#
#
# def label_models(models: Sequence[str]) -> str:
#     return "[" + ", ".join(models) + "]"
#
#
# def get_wait_results_for_models(model_list: List[str], use_real_waits: bool) -> Dict[str, float]:
#     """
#     Match controller routing logic.
#     """
#     if not use_real_waits:
#         return {m: 0.0 for m in model_list}
#
#     if not USE_TWO_ILUVATAR_INSTANCES:
#         return wait_time_iluvatar.main(
#             server_address=SERVER_ADDRESS,
#             model_list=model_list,
#         )
#
#     small_models = [m for m in model_list if m in SMALL_INSTANCE_MODELS]
#     large_models = [m for m in model_list if m in LARGE_INSTANCE_MODELS]
#     merged: Dict[str, float] = {}
#
#     if small_models:
#         small_waits = wait_time_iluvatar.main(
#             server_address=SMALL_MODEL_SERVER_ADDRESS,
#             model_list=small_models,
#         )
#         merged.update(small_waits)
#
#     if large_models:
#         large_waits = wait_time_iluvatar.main(
#             server_address=LARGE_MODEL_SERVER_ADDRESS,
#             model_list=large_models,
#         )
#         merged.update(large_waits)
#
#     unassigned = [m for m in model_list if m not in merged]
#     if unassigned:
#         fallback_waits = wait_time_iluvatar.main(
#             server_address=SERVER_ADDRESS,
#             model_list=unassigned,
#         )
#         merged.update(fallback_waits)
#
#     return merged
#
#
# def summarize_waits(wait_results: Dict[str, float]) -> tuple[float, float, float]:
#     vals = [float(v) for v in wait_results.values() if v is not None and math.isfinite(float(v))]
#     if not vals:
#         return 0.0, 0.0, 0.0
#     return sum(vals) / len(vals), max(vals), min(vals)
#
#
# def select_for_mode(
#     mode: str,
#     wait_results: Dict[str, float],
#     deadline_ms: int,
#     ensemble_size: int,
#     alpha_now: float,
#     parallel_first_n: int,
#     network_latency: float,
# ):
#     selected_models, _ = build_model_set_by_mode(
#         cascade_mode=mode,
#         wait_results=wait_results,
#         deadline_ms=deadline_ms,
#         ensemble_size=ensemble_size,
#         alpha_now=alpha_now,
#         parallel_first_n=parallel_first_n,
#         network_latency=network_latency,
#         logger=None,
#     )
#
#     selected_est_latency_s = estimate_selected_set_latency_for_mode(
#         cascade_mode=mode,
#         selected_models=selected_models,
#         wait_results=wait_results,
#         network_latency=network_latency,
#         parallel_first_n=parallel_first_n,
#     )
#
#     deadline_s = deadline_ms / 1000.0
#     feasible = math.isfinite(selected_est_latency_s) and selected_est_latency_s < deadline_s
#
#     return selected_models, selected_est_latency_s, feasible
#
#
# def write_rows_csv(path: str, rows: List[StepRow]) -> None:
#     with open(path, "w", newline="") as f:
#         writer = csv.writer(f)
#         writer.writerow([
#             "step",
#             "mode",
#             "selected_models",
#             "selected_est_latency_s",
#             "feasible",
#             "deadline_s",
#             "mean_wait_s",
#             "max_wait_s",
#             "min_wait_s",
#         ])
#         for r in rows:
#             writer.writerow([
#                 r.step,
#                 r.mode,
#                 list(r.selected_models),
#                 r.selected_est_latency_s,
#                 r.feasible,
#                 r.deadline_s,
#                 r.mean_wait_s,
#                 r.max_wait_s,
#                 r.min_wait_s,
#             ])
#
#
# # =========================================================
# # Plotting
# # =========================================================
#
# def plot_est_latency_over_time(rows: List[StepRow], output_path: str) -> None:
#     plt.figure(figsize=(12, 6))
#
#     # modes = ["mode_s", "sequential", "parallel_first_finish"]
#     modes = ["mode_s", "sequential"]
#     for mode in modes:
#         mode_rows = [r for r in rows if r.mode == mode]
#         xs = [r.step for r in mode_rows]
#         ys = [r.selected_est_latency_s for r in mode_rows]
#         plt.plot(xs, ys, marker="o", label=mode)
#
#     if rows:
#         deadline_s = rows[0].deadline_s
#         plt.axhline(deadline_s, linestyle="--", label=f"deadline={deadline_s:.3f}s")
#
#     plt.xlabel("Request / step index")
#     plt.ylabel("Selected estimated latency (s)")
#     plt.title("Selected estimated latency over time")
#     plt.legend()
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# def plot_mean_wait_over_time(rows: List[StepRow], output_path: str) -> None:
#     # mean wait is the same across modes for a given step, so use mode_s rows only
#     base_rows = [r for r in rows if r.mode == "mode_s"]
#
#     plt.figure(figsize=(12, 6))
#     xs = [r.step for r in base_rows]
#     ys = [r.mean_wait_s for r in base_rows]
#     plt.plot(xs, ys, marker="o")
#
#     plt.xlabel("Request / step index")
#     plt.ylabel("Mean wait time (s)")
#     plt.title("Mean wait time over time")
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# def plot_selected_set_over_time(rows: List[StepRow], output_path: str) -> None:
#     modes = ["mode_s", "sequential"]
#
#     # Map each unique label to an integer for plotting
#     labels = sorted({label_models(r.selected_models) for r in rows})
#     label_to_id = {lab: i for i, lab in enumerate(labels)}
#
#     fig, axes = plt.subplots(len(modes), 1, figsize=(14, 8), sharex=True)
#
#     if len(modes) == 1:
#         axes = [axes]
#
#     for ax, mode in zip(axes, modes):
#         mode_rows = [r for r in rows if r.mode == mode]
#         xs = [r.step for r in mode_rows]
#         ys = [label_to_id[label_models(r.selected_models)] for r in mode_rows]
#
#         ax.plot(xs, ys, marker="o")
#         ax.set_title(f"Selected ensemble over time: {mode}")
#         ax.set_yticks(range(len(labels)))
#         ax.set_yticklabels(labels)
#
#     axes[-1].set_xlabel("Request / step index")
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# def plot_deadline_violations(rows: List[StepRow], output_path: str) -> None:
#     plt.figure(figsize=(12, 6))
#
#     modes = ["mode_s", "sequential", "parallel_first_finish"]
#     for mode in modes:
#         mode_rows = [r for r in rows if r.mode == mode]
#         xs = [r.step for r in mode_rows]
#         ys = [0 if r.feasible else 1 for r in mode_rows]
#         plt.plot(xs, ys, marker="o", label=mode)
#
#     plt.xlabel("Request / step index")
#     plt.ylabel("Deadline violation (1=yes, 0=no)")
#     plt.title("Deadline violations over time")
#     plt.legend()
#     plt.tight_layout()
#     plt.savefig(output_path, dpi=200, bbox_inches="tight")
#     plt.close()
#
#
# # =========================================================
# # Main
# # =========================================================
#
# def main() -> None:
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--deadline-ms", type=int, default=2000)
#     parser.add_argument("--ensemble-size", type=int, default=ENSEMBLE_SIZE)
#     parser.add_argument("--parallel-first-n", type=int, default=PARALLEL_FIRST_N)
#     parser.add_argument("--network-latency", type=float, default=NETWORK_LATENCY)
#     parser.add_argument("--alpha", type=float, default=ALPHA_STATIC)
#     parser.add_argument("--num-steps", type=int, default=20)
#     parser.add_argument("--poll-interval-sec", type=float, default=3.0)
#     parser.add_argument("--use-real-waits", type=str, default="true")
#     parser.add_argument("--output-dir", type=str, default="dynamic_analysis_outputs")
#     args = parser.parse_args()
#
#     use_real_waits = str2bool(args.use_real_waits)
#     ensure_dir(args.output_dir)
#
#     rows: List[StepRow] = []
#     models = list(M_TOTAL)
#     deadline_s = args.deadline_ms / 1000.0
#
#     for step in range(1, args.num_steps + 1):
#         wait_results = get_wait_results_for_models(models, use_real_waits)
#         mean_wait_s, max_wait_s, min_wait_s = summarize_waits(wait_results)
#
#         for mode in ["mode_s", "sequential", "parallel_first_finish"]:
#             selected_models, selected_est_latency_s, feasible = select_for_mode(
#                 mode=mode,
#                 wait_results=wait_results,
#                 deadline_ms=args.deadline_ms,
#                 ensemble_size=args.ensemble_size,
#                 alpha_now=args.alpha,
#                 parallel_first_n=args.parallel_first_n,
#                 network_latency=args.network_latency,
#             )
#
#             rows.append(
#                 StepRow(
#                     step=step,
#                     mode=mode,
#                     selected_models=list(selected_models),
#                     selected_est_latency_s=selected_est_latency_s,
#                     feasible=feasible,
#                     deadline_s=deadline_s,
#                     mean_wait_s=mean_wait_s,
#                     max_wait_s=max_wait_s,
#                     min_wait_s=min_wait_s,
#                 )
#             )
#
#         print(
#             f"step={step:03d} "
#             f"mean_wait={mean_wait_s:.4f}s max_wait={max_wait_s:.4f}s min_wait={min_wait_s:.4f}s"
#         )
#
#         if step < args.num_steps:
#             time.sleep(args.poll_interval_sec)
#
#     # Save CSV
#     csv_path = os.path.join(args.output_dir, "dynamic_selection_log.csv")
#     write_rows_csv(csv_path, rows)
#
#     # Plots
#     plot_est_latency_over_time(
#         rows=rows,
#         output_path=os.path.join(args.output_dir, "selected_est_latency_over_time.png"),
#     )
#
#     plot_mean_wait_over_time(
#         rows=rows,
#         output_path=os.path.join(args.output_dir, "mean_wait_over_time.png"),
#     )
#
#     plot_selected_set_over_time(
#         rows=rows,
#         output_path=os.path.join(args.output_dir, "selected_ensemble_over_time.png"),
#     )
#
#     plot_deadline_violations(
#         rows=rows,
#         output_path=os.path.join(args.output_dir, "deadline_violations_over_time.png"),
#     )
#
#     # Summary text
#     summary_path = os.path.join(args.output_dir, "summary.txt")
#     with open(summary_path, "w") as f:
#         f.write(f"deadline_ms={args.deadline_ms}\n")
#         f.write(f"ensemble_size={args.ensemble_size}\n")
#         f.write(f"parallel_first_n={args.parallel_first_n}\n")
#         f.write(f"network_latency={args.network_latency}\n")
#         f.write(f"alpha={args.alpha}\n")
#         f.write(f"use_real_waits={use_real_waits}\n")
#         f.write(f"num_steps={args.num_steps}\n")
#         f.write(f"poll_interval_sec={args.poll_interval_sec}\n")
#
#     print("\nDynamic analysis complete.")
#     print(f"Outputs written to: {os.path.abspath(args.output_dir)}")
#     print("Generated files:")
#     for name in sorted(os.listdir(args.output_dir)):
#         print(f"  - {name}")
#
#
# if __name__ == "__main__":
#     main()



#!/usr/bin/env python3
"""
Dynamic analysis of ensemble selection over time.

This script:
1. Loads real project config from ckn_controller.ckn_config
2. Repeatedly queries Iluvatar wait times (or uses zero waits)
3. For each step/request:
   - selects a model set for mode_s
   - selects a model set for sequential
   - selects a model set for power_of_two_choices
   - estimates selected latency
4. Saves a CSV log
5. Generates dynamic plots:
   - estimated latency over requests
   - mean wait over requests
   - selected ensemble over requests
   - deadline violation indicator over requests
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Sequence

import matplotlib.pyplot as plt

from ckn_controller.ckn_config import (
    M_TOTAL,
    ENSEMBLE_SIZE,
    NETWORK_LATENCY,
    PARALLEL_FIRST_N,
    ALPHA_STATIC,
    SMALL_INSTANCE_MODELS,
    LARGE_INSTANCE_MODELS,
    SMALL_MODEL_SERVER_ADDRESS,
    LARGE_MODEL_SERVER_ADDRESS,
    SERVER_ADDRESS,
    USE_TWO_ILUVATAR_INSTANCES,
    THRESHOLD,
    SELECTION_STRATEGY,
    USE_DEADLINE_FAST_PATH,
)
from ckn_controller.ensemble_selector import (
    build_model_set_by_mode,
    estimate_selected_set_latency_for_mode,
)
import wait_time_iluvatar


@dataclass
class StepRow:
    step: int
    mode: str
    selected_models: List[str]
    selected_est_latency_s: float
    feasible: bool
    deadline_s: float
    mean_wait_s: float
    max_wait_s: float
    min_wait_s: float


def str2bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def label_models(models: Sequence[str]) -> str:
    return "[" + ", ".join(models) + "]"


def get_wait_results_for_models(model_list: List[str], use_real_waits: bool) -> Dict[str, float]:
    if not use_real_waits:
        return {m: 0.0 for m in model_list}

    if not USE_TWO_ILUVATAR_INSTANCES:
        return wait_time_iluvatar.main(
            server_address=SERVER_ADDRESS,
            model_list=model_list,
        )

    small_models = [m for m in model_list if m in SMALL_INSTANCE_MODELS]
    large_models = [m for m in model_list if m in LARGE_INSTANCE_MODELS]
    merged: Dict[str, float] = {}

    if small_models:
        small_waits = wait_time_iluvatar.main(
            server_address=SMALL_MODEL_SERVER_ADDRESS,
            model_list=small_models,
        )
        merged.update(small_waits)

    if large_models:
        large_waits = wait_time_iluvatar.main(
            server_address=LARGE_MODEL_SERVER_ADDRESS,
            model_list=large_models,
        )
        merged.update(large_waits)

    unassigned = [m for m in model_list if m not in merged]
    if unassigned:
        fallback_waits = wait_time_iluvatar.main(
            server_address=SERVER_ADDRESS,
            model_list=unassigned,
        )
        merged.update(fallback_waits)

    return merged


def summarize_waits(wait_results: Dict[str, float]) -> tuple[float, float, float]:
    vals = [float(v) for v in wait_results.values() if v is not None and math.isfinite(float(v))]
    if not vals:
        return 0.0, 0.0, 0.0
    return sum(vals) / len(vals), max(vals), min(vals)


def select_for_mode(
    mode: str,
    wait_results: Dict[str, float],
    deadline_ms: int,
    ensemble_size: int,
    alpha_now: float,
    parallel_first_n: int,
    network_latency: float,
):
    selected_models, _ = build_model_set_by_mode(
        cascade_mode=mode,
        wait_results=wait_results,
        deadline_ms=deadline_ms,
        ensemble_size=ensemble_size,
        alpha_now=alpha_now,
        parallel_first_n=parallel_first_n,
        network_latency=network_latency,
        logger=None,
    )

    selected_est_latency_s = estimate_selected_set_latency_for_mode(
        cascade_mode=mode,
        selected_models=selected_models,
        wait_results=wait_results,
        network_latency=network_latency,
        parallel_first_n=parallel_first_n,
    )

    deadline_s = deadline_ms / 1000.0
    feasible = math.isfinite(selected_est_latency_s) and selected_est_latency_s < deadline_s

    return selected_models, selected_est_latency_s, feasible


def write_rows_csv(path: str, rows: List[StepRow]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "step",
            "mode",
            "selected_models",
            "selected_est_latency_s",
            "feasible",
            "deadline_s",
            "mean_wait_s",
            "max_wait_s",
            "min_wait_s",
        ])
        for r in rows:
            writer.writerow([
                r.step,
                r.mode,
                list(r.selected_models),
                r.selected_est_latency_s,
                r.feasible,
                r.deadline_s,
                r.mean_wait_s,
                r.max_wait_s,
                r.min_wait_s,
            ])


def plot_est_latency_over_time(rows: List[StepRow], output_path: str) -> None:
    plt.figure(figsize=(12, 6))

    modes = ["mode_s", "sequential", "power_of_two_choices"]
    for mode in modes:
        mode_rows = [r for r in rows if r.mode == mode]
        xs = [r.step for r in mode_rows]
        ys = [r.selected_est_latency_s for r in mode_rows]
        plt.plot(xs, ys, marker="o", label=mode)

    if rows:
        deadline_s = rows[0].deadline_s
        plt.axhline(deadline_s, linestyle="--", label=f"deadline={deadline_s:.3f}s")

    plt.xlabel("Request / step index")
    plt.ylabel("Selected estimated latency (s)")
    plt.title("Selected estimated latency over time")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def plot_mean_wait_over_time(rows: List[StepRow], output_path: str) -> None:
    base_rows = [r for r in rows if r.mode == "mode_s"]

    plt.figure(figsize=(12, 6))
    xs = [r.step for r in base_rows]
    ys = [r.mean_wait_s for r in base_rows]
    plt.plot(xs, ys, marker="o")

    plt.xlabel("Request / step index")
    plt.ylabel("Mean wait time (s)")
    plt.title("Mean wait time over time")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def plot_selected_set_over_time(rows: List[StepRow], output_path: str) -> None:
    modes = ["mode_s", "sequential", "power_of_two_choices"]

    labels = sorted({label_models(r.selected_models) for r in rows})
    label_to_id = {lab: i for i, lab in enumerate(labels)}

    fig, axes = plt.subplots(len(modes), 1, figsize=(14, 10), sharex=True)

    if len(modes) == 1:
        axes = [axes]

    for ax, mode in zip(axes, modes):
        mode_rows = [r for r in rows if r.mode == mode]
        xs = [r.step for r in mode_rows]
        ys = [label_to_id[label_models(r.selected_models)] for r in mode_rows]

        ax.plot(xs, ys, marker="o")
        ax.set_title(f"Selected ensemble over time: {mode}")
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels)

    axes[-1].set_xlabel("Request / step index")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def plot_deadline_violations(rows: List[StepRow], output_path: str) -> None:
    plt.figure(figsize=(12, 6))

    modes = ["mode_s", "sequential", "power_of_two_choices"]
    for mode in modes:
        mode_rows = [r for r in rows if r.mode == mode]
        xs = [r.step for r in mode_rows]
        ys = [0 if r.feasible else 1 for r in mode_rows]
        plt.plot(xs, ys, marker="o", label=mode)

    plt.xlabel("Request / step index")
    plt.ylabel("Deadline violation (1=yes, 0=no)")
    plt.title("Deadline violations over time")
    plt.legend()
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deadline-ms", type=int, default=15000)
    parser.add_argument("--ensemble-size", type=int, default=ENSEMBLE_SIZE)
    parser.add_argument("--parallel-first-n", type=int, default=PARALLEL_FIRST_N)
    parser.add_argument("--network-latency", type=float, default=NETWORK_LATENCY)
    parser.add_argument("--alpha", type=float, default=ALPHA_STATIC)
    parser.add_argument("--num-steps", type=int, default=45)
    parser.add_argument("--poll-interval-sec", type=float, default=3.0)
    parser.add_argument("--use-real-waits", type=str, default="true")
    parser.add_argument("--output-dir", type=str, default="dynamic_analysis_outputs")
    args = parser.parse_args()

    use_real_waits = str2bool(args.use_real_waits)
    ensure_dir(args.output_dir)

    rows: List[StepRow] = []
    models = list(M_TOTAL)
    deadline_s = args.deadline_ms / 1000.0

    print("SELECTION_STRATEGY =", SELECTION_STRATEGY)
    print("USE_DEADLINE_FAST_PATH =", USE_DEADLINE_FAST_PATH)

    for step in range(1, args.num_steps + 1):
        wait_results = get_wait_results_for_models(models, use_real_waits)
        mean_wait_s, max_wait_s, min_wait_s = summarize_waits(wait_results)

        for mode in ["mode_s", "sequential", "power_of_two_choices"]:
            selected_models, selected_est_latency_s, feasible = select_for_mode(
                mode=mode,
                wait_results=wait_results,
                deadline_ms=args.deadline_ms,
                ensemble_size=args.ensemble_size,
                alpha_now=args.alpha,
                parallel_first_n=args.parallel_first_n,
                network_latency=args.network_latency,
            )

            rows.append(
                StepRow(
                    step=step,
                    mode=mode,
                    selected_models=list(selected_models),
                    selected_est_latency_s=selected_est_latency_s,
                    feasible=feasible,
                    deadline_s=deadline_s,
                    mean_wait_s=mean_wait_s,
                    max_wait_s=max_wait_s,
                    min_wait_s=min_wait_s,
                )
            )

            print(
                f"step={step:03d} mode={mode} "
                f"selected={selected_models} size={len(selected_models)} "
                f"est_latency={selected_est_latency_s:.6f}"
            )

        print(
            f"step={step:03d} "
            f"mean_wait={mean_wait_s:.4f}s max_wait={max_wait_s:.4f}s min_wait={min_wait_s:.4f}s"
        )

        if step < args.num_steps:
            time.sleep(args.poll_interval_sec)

    csv_path = os.path.join(args.output_dir, "dynamic_selection_log.csv")
    write_rows_csv(csv_path, rows)

    plot_est_latency_over_time(
        rows=rows,
        output_path=os.path.join(args.output_dir, "selected_est_latency_over_time.png"),
    )

    plot_mean_wait_over_time(
        rows=rows,
        output_path=os.path.join(args.output_dir, "mean_wait_over_time.png"),
    )

    plot_selected_set_over_time(
        rows=rows,
        output_path=os.path.join(args.output_dir, "selected_ensemble_over_time.png"),
    )

    plot_deadline_violations(
        rows=rows,
        output_path=os.path.join(args.output_dir, "deadline_violations_over_time.png"),
    )

    summary_path = os.path.join(args.output_dir, "summary.txt")
    with open(summary_path, "w") as f:
        f.write(f"deadline_ms={args.deadline_ms}\n")
        f.write(f"ensemble_size={args.ensemble_size}\n")
        f.write(f"parallel_first_n={args.parallel_first_n}\n")
        f.write(f"network_latency={args.network_latency}\n")
        f.write(f"alpha={args.alpha}\n")
        f.write(f"use_real_waits={use_real_waits}\n")
        f.write(f"num_steps={args.num_steps}\n")
        f.write(f"poll_interval_sec={args.poll_interval_sec}\n")
        f.write(f"threshold={THRESHOLD}\n")
        f.write(f"selection_strategy={SELECTION_STRATEGY}\n")
        f.write(f"use_deadline_fast_path={USE_DEADLINE_FAST_PATH}\n")

    print("\nDynamic analysis complete.")
    print(f"Outputs written to: {os.path.abspath(args.output_dir)}")
    print("Generated files:")
    for name in sorted(os.listdir(args.output_dir)):
        print(f"  - {name}")


if __name__ == "__main__":
    main()

