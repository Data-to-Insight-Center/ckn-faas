#!/usr/bin/env python3
"""
Analyze ensemble selection for MODE-S, sequential cascade, and parallel-first-finish.

This script:
1. Loads model/config info from ckn_controller.ckn_config
2. Optionally queries real wait times from Iluvatar
3. Enumerates candidate model combinations up to ENSEMBLE_SIZE
4. Computes E[T] for sequential and parallel-first-finish
5. Computes MODE-S cost for mode_s
6. Compares greedy vs exhaustive selection
7. Saves CSV summaries and plots

Run from your project root, for example:
    python ensemble_selection_analysis.py
    python ensemble_selection_analysis.py --deadline-ms 250 --top-k 10
    python ensemble_selection_analysis.py --use-real-waits false

Outputs are written to ./analysis_outputs by default.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import math
import os
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import matplotlib.pyplot as plt

from ckn_controller.ckn_config import (
    M_TOTAL,
    POLICY,
    K,
    C,
    ENSEMBLE_SIZE,
    MODEL_PROFILES,
    MODEL_SIZES,
    NETWORK_LATENCY,
    PARALLEL_FIRST_N,
    SMALL_INSTANCE_MODELS,
    LARGE_INSTANCE_MODELS,
    SMALL_MODEL_SERVER_ADDRESS,
    LARGE_MODEL_SERVER_ADDRESS,
    SERVER_ADDRESS,
    USE_TWO_ILUVATAR_INSTANCES,
    ALPHA_STATIC,
)
from ckn_controller.ensemble_selector import (
    reorder_for_sequential,
    estimate_expected_latency_sequential,
    estimate_expected_latency_parallel_first_finish,
    build_model_set_mode_s,
    build_model_set_sequential_greedy,
    build_model_set_sequential_exhaustive,
    build_model_set_parallel_first_greedy,
    build_model_set_parallel_first_exhaustive,
)
import wait_time_iluvatar


@dataclass
class CandidateRow:
    mode: str
    subset: Tuple[str, ...]
    ordered_models: Tuple[str, ...]
    size: int
    est_latency_s: float
    feasible: bool
    extra_info_1: float | None = None
    extra_info_2: float | None = None


def str2bool(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def get_wait_results_for_models(model_list: List[str], use_real_waits: bool) -> Dict[str, float]:
    """Match the main controller's routing logic."""
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

    # Any unassigned model falls back to SERVER_ADDRESS
    unassigned = [m for m in model_list if m not in merged]
    if unassigned:
        fallback_waits = wait_time_iluvatar.main(
            server_address=SERVER_ADDRESS,
            model_list=unassigned,
        )
        merged.update(fallback_waits)

    return merged


def estimate_mode_s_cost(
    subset: Sequence[str],
    wait_results: Dict[str, float],
    deadline_ms: int,
    alpha_now: float,
) -> Tuple[float, float, bool]:
    """Original MODE-S style cost for one candidate subset."""
    d_sec = deadline_ms / 1000.0
    if d_sec <= 0:
        return math.inf, math.inf, False

    times = []
    for m in subset:
        wait_t = float(wait_results.get(m, math.inf))
        compute_t = float(MODEL_PROFILES[m]["latency"])
        times.append(wait_t + compute_t)

    te = max(times) if times else math.inf
    if not math.isfinite(te):
        return math.inf, te, False

    raw = te / d_sec
    if raw >= 1.0:
        return math.inf, te, False

    latency_term = min(max(raw, 0.1), 0.9)

    max_models = min(ENSEMBLE_SIZE, K // C, len(M_TOTAL))
    sorted_by_size = sorted(M_TOTAL, key=lambda m: MODEL_SIZES[m], reverse=True)
    maxms: Dict[int, int] = {}
    rolling_sum = 0
    for i, m in enumerate(sorted_by_size):
        rolling_sum += MODEL_SIZES[m]
        size = i + 1
        if size <= max_models:
            maxms[size] = rolling_sum

    size = len(subset)
    sum_bytes = sum(MODEL_SIZES[m] for m in subset)
    if sum_bytes <= 0 or size not in maxms:
        return math.inf, te, False

    size_cost = maxms[size] / sum_bytes
    cost = ((1.0 - alpha_now) * latency_term) + (alpha_now * size_cost)
    return cost, te, True


def generate_candidate_subsets(models: Sequence[str], max_size: int) -> List[Tuple[str, ...]]:
    out: List[Tuple[str, ...]] = []
    for k in range(1, max_size + 1):
        out.extend(itertools.combinations(models, k))
    return out


def compute_sequential_rows(
    subsets: Sequence[Tuple[str, ...]],
    wait_results: Dict[str, float],
    deadline_ms: int,
    network_latency: float,
) -> List[CandidateRow]:
    d_sec = deadline_ms / 1000.0
    rows: List[CandidateRow] = []
    for subset in subsets:
        if len(subset) * C > K:
            continue
        ordered = tuple(reorder_for_sequential(list(subset), wait_results))
        et = estimate_expected_latency_sequential(list(ordered), wait_results, network_latency)
        feasible = math.isfinite(et) and et < d_sec
        rows.append(
            CandidateRow(
                mode="sequential",
                subset=tuple(subset),
                ordered_models=ordered,
                size=len(subset),
                est_latency_s=et,
                feasible=feasible,
            )
        )
    return rows


def compute_parallel_first_rows(
    subsets: Sequence[Tuple[str, ...]],
    wait_results: Dict[str, float],
    deadline_ms: int,
    parallel_first_n: int,
    network_latency: float,
) -> List[CandidateRow]:
    d_sec = deadline_ms / 1000.0
    rows: List[CandidateRow] = []
    for subset in subsets:
        if len(subset) * C > K:
            continue
        et = estimate_expected_latency_parallel_first_finish(
            list(subset), wait_results, parallel_first_n, network_latency
        )
        feasible = math.isfinite(et) and et < d_sec
        rows.append(
            CandidateRow(
                mode="parallel_first_finish",
                subset=tuple(subset),
                ordered_models=tuple(subset),
                size=len(subset),
                est_latency_s=et,
                feasible=feasible,
            )
        )
    return rows


def compute_mode_s_rows(
    subsets: Sequence[Tuple[str, ...]],
    wait_results: Dict[str, float],
    deadline_ms: int,
    alpha_now: float,
) -> List[CandidateRow]:
    rows: List[CandidateRow] = []
    for subset in subsets:
        if len(subset) * C > K:
            continue
        cost, te, feasible = estimate_mode_s_cost(subset, wait_results, deadline_ms, alpha_now)
        rows.append(
            CandidateRow(
                mode="mode_s",
                subset=tuple(subset),
                ordered_models=tuple(subset),
                size=len(subset),
                est_latency_s=te,
                feasible=feasible,
                extra_info_1=cost,
            )
        )
    return rows


def write_rows_csv(path: str, rows: Sequence[CandidateRow]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "mode",
            "subset",
            "ordered_models",
            "size",
            "est_latency_s",
            "feasible",
            "extra_info_1",
            "extra_info_2",
        ])
        for r in rows:
            writer.writerow([
                r.mode,
                list(r.subset),
                list(r.ordered_models),
                r.size,
                r.est_latency_s,
                r.feasible,
                r.extra_info_1,
                r.extra_info_2,
            ])


def label_subset(models: Sequence[str]) -> str:
    return "[" + ", ".join(models) + "]"


def plot_top_k_et(
    rows: Sequence[CandidateRow],
    deadline_s: float,
    title: str,
    output_path: str,
    top_k: int,
) -> None:
    filtered = [r for r in rows if math.isfinite(r.est_latency_s)]
    filtered.sort(key=lambda r: r.est_latency_s)
    top = filtered[:top_k]

    labels = [label_subset(r.ordered_models) for r in top]
    vals = [r.est_latency_s for r in top]

    plt.figure(figsize=(12, 6))
    bars = plt.bar(labels, vals)
    if bars:
        bars[0].set_hatch("//")
    plt.axhline(deadline_s, linestyle="--")
    plt.xlabel("Model combinations")
    plt.ylabel("Estimated latency / E[T] (seconds)")
    plt.title(title)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def plot_parallel_first_breakdown(
    rows: Sequence[CandidateRow],
    wait_results: Dict[str, float],
    parallel_first_n: int,
    network_latency: float,
    output_path: str,
    top_k: int,
) -> None:
    filtered = [r for r in rows if math.isfinite(r.est_latency_s)]
    filtered.sort(key=lambda r: r.est_latency_s)
    top = filtered[:top_k]

    labels: List[str] = []
    first_parts: List[float] = []
    tail_parts: List[float] = []

    for r in top:
        models = list(r.ordered_models)
        first_n = max(1, min(parallel_first_n, len(models)))
        first_batch = models[:first_n]
        tail = models[first_n:]

        first_latency = min(
            float(wait_results.get(m, math.inf)) + float(MODEL_PROFILES[m]["latency"])
            for m in first_batch
        )

        if not tail:
            tail_contrib = 0.0
        else:
            fail_prob = 1.0
            for m in first_batch:
                p = float(MODEL_PROFILES[m].get("accuracy", 0.5))
                fail_prob *= (1.0 - p)
            tail_et = estimate_expected_latency_sequential(
                reorder_for_sequential(tail, wait_results),
                wait_results,
                network_latency,
            )
            tail_contrib = fail_prob * (network_latency + tail_et)

        labels.append(label_subset(models))
        first_parts.append(first_latency)
        tail_parts.append(tail_contrib)

    plt.figure(figsize=(12, 6))
    plt.bar(labels, first_parts, label="First batch latency")
    plt.bar(labels, tail_parts, bottom=first_parts, label="Failure-weighted tail")
    plt.xlabel("Model combinations")
    plt.ylabel("Estimated E[T] (seconds)")
    plt.title("Power_of_two_choices latency breakdown")
    plt.legend()
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def plot_greedy_vs_exhaustive(
    mode_name: str,
    greedy_models: Sequence[str],
    greedy_et: float,
    exhaustive_models: Sequence[str],
    exhaustive_et: float,
    deadline_s: float,
    output_path: str,
) -> None:
    labels = [
        f"Greedy\n{label_subset(greedy_models)}",
        f"Exhaustive\n{label_subset(exhaustive_models)}",
    ]
    vals = [greedy_et, exhaustive_et]

    plt.figure(figsize=(8, 6))
    plt.bar(labels, vals)
    plt.axhline(deadline_s, linestyle="--")
    plt.xlabel("Selection strategy")
    plt.ylabel("Estimated latency / E[T] (seconds)")
    plt.title(f"{mode_name}: Greedy vs Exhaustive")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close()


def write_summary_txt(path: str, lines: Sequence[str]) -> None:
    with open(path, "w") as f:
        for line in lines:
            f.write(line + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deadline-ms", type=int, default=200)
    parser.add_argument("--ensemble-size", type=int, default=ENSEMBLE_SIZE)
    parser.add_argument("--parallel-first-n", type=int, default=PARALLEL_FIRST_N)
    parser.add_argument("--network-latency", type=float, default=NETWORK_LATENCY)
    parser.add_argument("--alpha", type=float, default=ALPHA_STATIC)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--use-real-waits", type=str, default="true")
    parser.add_argument("--output-dir", type=str, default="analysis_outputs")
    args = parser.parse_args()

    use_real_waits = str2bool(args.use_real_waits)
    ensure_dir(args.output_dir)

    models = list(M_TOTAL)
    wait_results = get_wait_results_for_models(models, use_real_waits)
    subsets = generate_candidate_subsets(models, min(args.ensemble_size, len(models)))
    deadline_s = args.deadline_ms / 1000.0

    seq_rows = compute_sequential_rows(
        subsets=subsets,
        wait_results=wait_results,
        deadline_ms=args.deadline_ms,
        network_latency=args.network_latency,
    )
    pff_rows = compute_parallel_first_rows(
        subsets=subsets,
        wait_results=wait_results,
        deadline_ms=args.deadline_ms,
        parallel_first_n=args.parallel_first_n,
        network_latency=args.network_latency,
    )
    mode_s_rows = compute_mode_s_rows(
        subsets=subsets,
        wait_results=wait_results,
        deadline_ms=args.deadline_ms,
        alpha_now=args.alpha,
    )

    write_rows_csv(os.path.join(args.output_dir, "sequential_candidates.csv"), seq_rows)
    write_rows_csv(os.path.join(args.output_dir, "parallel_first_candidates.csv"), pff_rows)
    write_rows_csv(os.path.join(args.output_dir, "mode_s_candidates.csv"), mode_s_rows)

    seq_greedy_models, _ = build_model_set_sequential_greedy(
        wait_results=wait_results,
        deadline_ms=args.deadline_ms,
        ensemble_size=args.ensemble_size,
        network_latency=args.network_latency,
    )
    seq_exh_models, _ = build_model_set_sequential_exhaustive(
        wait_results=wait_results,
        deadline_ms=args.deadline_ms,
        ensemble_size=args.ensemble_size,
        network_latency=args.network_latency,
    )
    pff_greedy_models, _ = build_model_set_parallel_first_greedy(
        wait_results=wait_results,
        deadline_ms=args.deadline_ms,
        ensemble_size=args.ensemble_size,
        parallel_first_n=args.parallel_first_n,
        network_latency=args.network_latency,
    )
    pff_exh_models, _ = build_model_set_parallel_first_exhaustive(
        wait_results=wait_results,
        deadline_ms=args.deadline_ms,
        ensemble_size=args.ensemble_size,
        parallel_first_n=args.parallel_first_n,
        network_latency=args.network_latency,
    )
    mode_s_models, _ = build_model_set_mode_s(
        wait_results=wait_results,
        deadline_ms=args.deadline_ms,
        ensemble_size=args.ensemble_size,
        alpha_now=args.alpha,
    )

    seq_greedy_et = estimate_expected_latency_sequential(seq_greedy_models, wait_results, args.network_latency)
    seq_exh_et = estimate_expected_latency_sequential(seq_exh_models, wait_results, args.network_latency)
    pff_greedy_et = estimate_expected_latency_parallel_first_finish(
        pff_greedy_models, wait_results, args.parallel_first_n, args.network_latency
    )
    pff_exh_et = estimate_expected_latency_parallel_first_finish(
        pff_exh_models, wait_results, args.parallel_first_n, args.network_latency
    )
    mode_s_cost, mode_s_te, mode_s_feasible = estimate_mode_s_cost(
        mode_s_models, wait_results, args.deadline_ms, args.alpha
    )

    plot_top_k_et(
        rows=seq_rows,
        deadline_s=deadline_s,
        title="Sequential cascade: top candidate combinations by E[T]",
        output_path=os.path.join(args.output_dir, "sequential_topk.png"),
        top_k=args.top_k,
    )
    plot_top_k_et(
        rows=pff_rows,
        deadline_s=deadline_s,
        title="power_of_two_choices: top candidate combinations by E[T]",
        output_path=os.path.join(args.output_dir, "parallel_first_topk.png"),
        top_k=args.top_k,
    )
    plot_parallel_first_breakdown(
        rows=pff_rows,
        wait_results=wait_results,
        parallel_first_n=args.parallel_first_n,
        network_latency=args.network_latency,
        output_path=os.path.join(args.output_dir, "power_of_two_choices_breakdown.png"),
        top_k=args.top_k,
    )
    plot_greedy_vs_exhaustive(
        mode_name="Sequential",
        greedy_models=seq_greedy_models,
        greedy_et=seq_greedy_et,
        exhaustive_models=seq_exh_models,
        exhaustive_et=seq_exh_et,
        deadline_s=deadline_s,
        output_path=os.path.join(args.output_dir, "sequential_greedy_vs_exhaustive.png"),
    )
    plot_greedy_vs_exhaustive(
        mode_name="Parallel-first-finish",
        greedy_models=pff_greedy_models,
        greedy_et=pff_greedy_et,
        exhaustive_models=pff_exh_models,
        exhaustive_et=pff_exh_et,
        deadline_s=deadline_s,
        output_path=os.path.join(args.output_dir, "parallel_first_greedy_vs_exhaustive.png"),
    )

    summary_lines = [
        f"deadline_ms={args.deadline_ms}",
        f"ensemble_size={args.ensemble_size}",
        f"parallel_first_n={args.parallel_first_n}",
        f"network_latency={args.network_latency}",
        f"alpha={args.alpha}",
        f"use_real_waits={use_real_waits}",
        "",
        f"MODE-S selected: {mode_s_models}",
        f"MODE-S estimated Te: {mode_s_te:.6f} s",
        f"MODE-S cost: {mode_s_cost:.6f}",
        f"MODE-S feasible: {mode_s_feasible}",
        "",
        f"Sequential greedy selected: {seq_greedy_models}",
        f"Sequential greedy E[T]: {seq_greedy_et:.6f} s",
        f"Sequential exhaustive selected: {seq_exh_models}",
        f"Sequential exhaustive E[T]: {seq_exh_et:.6f} s",
        "",
        f"Parallel-first greedy selected: {pff_greedy_models}",
        f"Parallel-first greedy E[T]: {pff_greedy_et:.6f} s",
        f"Parallel-first exhaustive selected: {pff_exh_models}",
        f"Parallel-first exhaustive E[T]: {pff_exh_et:.6f} s",
        "",
        "Wait results:",
    ]
    for m in models:
        summary_lines.append(f"  {m}: {wait_results.get(m, math.inf)}")

    write_summary_txt(os.path.join(args.output_dir, "summary.txt"), summary_lines)

    print("Analysis complete.")
    print(f"Outputs written to: {os.path.abspath(args.output_dir)}")
    print("Generated files:")
    for name in sorted(os.listdir(args.output_dir)):
        print(f"  - {name}")


if __name__ == "__main__":
    main()
