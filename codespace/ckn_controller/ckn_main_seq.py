import grpc
import json
import uuid
import time
import asyncio
import logging
import os
from collections import deque
from typing import Dict, List, Tuple, Optional
from logging.handlers import RotatingFileHandler

# Use ONE set of protobuf imports (avoid duplicates)
import ckn_controller.iluvatar_rpc_pb2 as pb2
import ckn_controller.iluvatar_rpc_pb2_grpc as pb2_grpc

from ckn_controller.ckn_config import (
    SERVER_ADDRESS,
    M_TOTAL,
    POLICY,
    K,
    C,
    ALPHA,  # legacy fixed alpha (we override dynamically)
    ETA,
    MODEL_PROFILES,
    OMEGA,
    MAX_MODEL_SIZE,
    DEFAULT_WEIGHTS,
    GAMMA,
    RHO,
    WEIGHTS_STATE_PATH,
    MODEL_SIZES,

    # --- Cascade parameters ---
    ENSEMBLE_SIZE,
    THRESHOLD,
    THRESHOLD_STAGE,

    # --- Alpha control ---
    ALPHA_MODE,  # "static" or "adaptive"
    ALPHA_STATIC,  # used if static mode
    ALPHA_MIN,  # used if adaptive mode
    ALPHA_MAX,

    # --- Load normalization ---
    QPS_WINDOW_SEC,
    QPS_LOW,
    QPS_HIGH,
    WAIT_LOW,
    WAIT_HIGH,
)

import wait_time_iluvatar
from ckn_controller.output_combiner import combine_outputs
from ckn_controller.weights_io import load_model_weights, save_model_weights_atomic
from ckn_controller.label_utils import wnid_matches_text_label

# -----------------------------
# New parameters (safe defaults)
# -----------------------------
# If you define these in ckn_config.py, those values will be used.
# try:
#     from ckn_controller.ckn_config import ENSEMBLE_SIZE
# except Exception:
#     ENSEMBLE_SIZE = 3
#
# try:
#     from ckn_controller.ckn_config import THRESHOLD
# except Exception:
#     THRESHOLD = 0.85
#
# try:
#     from ckn_controller.ckn_config import ALPHA_MIN, ALPHA_MAX
# except Exception:
#     ALPHA_MIN, ALPHA_MAX = 0.2, 1.0
#
# try:
#     from ckn_controller.ckn_config import QPS_WINDOW_SEC, QPS_LOW, QPS_HIGH
# except Exception:
#     QPS_WINDOW_SEC, QPS_LOW, QPS_HIGH = 1.0, 10.0, 100.0
#
# try:
#     from ckn_controller.ckn_config import WAIT_LOW, WAIT_HIGH
# except Exception:
#     WAIT_LOW, WAIT_HIGH = 0.01, 0.2  # seconds


# -----------------------------
# Logging setup (file + console)
# -----------------------------
LOG_DIR = os.environ.get("MODE_S_LOG_DIR", "./logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "mode_s_cascade.log")

logger = logging.getLogger("mode_s")
logger.setLevel(logging.INFO)

if not logger.handlers:
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)


MODEL_WEIGHTS = load_model_weights(WEIGHTS_STATE_PATH, DEFAULT_WEIGHTS)
active_models = set()


# -----------------------------
# QPS tracking (sliding window)
# -----------------------------
REQUEST_TS = deque()

def record_request(now: float, window_sec: float) -> None:
    REQUEST_TS.append(now)
    cutoff = now - window_sec
    while REQUEST_TS and REQUEST_TS[0] < cutoff:
        REQUEST_TS.popleft()

def get_qps(window_sec: float) -> float:
    return len(REQUEST_TS) / max(window_sec, 1e-9)


# -----------------------------
# Load-adaptive alpha (hybrid)
# Primary signal: Ilúvatar wait time
# Secondary signal: QPS
# -----------------------------
def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def compute_adaptive_alpha(
    qps: float,
    wait_results: Dict[str, float],
    alpha_min: float,
    alpha_max: float,
    qps_low: float,
    qps_high: float,
    wait_low: float,
    wait_high: float,
) -> float:
    # Normalize QPS
    if qps_high <= qps_low:
        qps_norm = 0.0
    else:
        qps_norm = _clamp01((qps - qps_low) / (qps_high - qps_low))

    # Normalize wait (mean wait)
    waits = [float(v) for v in wait_results.values() if v is not None]
    mean_wait = sum(waits) / len(waits) if waits else 0.0

    if wait_high <= wait_low:
        wait_norm = 0.0
    else:
        wait_norm = _clamp01((mean_wait - wait_low) / (wait_high - wait_low))

    # Hybrid load score: prioritize wait time
    load_score = max(wait_norm, 0.5 * qps_norm)

    # Low load -> alpha_max, High load -> alpha_min
    alpha_now = alpha_max - load_score * (alpha_max - alpha_min)
    return max(alpha_min, min(alpha_max, alpha_now))


# -----------------------------
# Ilúvatar invocation
# -----------------------------
async def send_request(stub, model_name: str, image_b64: str) -> dict:
    request = pb2.InvokeRequest(
        function_name=model_name,
        function_version="1",
        json_args=json.dumps({"model_name": model_name, "image_data": image_b64}),
        transaction_id=str(uuid.uuid4()),
    )
    response = await stub.invoke(request)
    result_json = json.loads(response.json_result)
    return {
        "model": model_name,
        "label": result_json["body"]["Prediction Class"],
        "probability": float(result_json["body"]["Probability"]),
        "latency": response.duration_us / 1e6,
        "success": response.success,
        "container_state": pb2.ContainerState.Name(response.container_state),
    }


# -----------------------------
# Model selection: EXACT ENSEMBLE_SIZE
# Uses adaptive alpha inside cost function.
# -----------------------------
def build_model_set(
    wait_results: Dict[str, float],
    deadline_ms: int,
    ensemble_size: int,
    alpha_now: float
) -> Tuple[List[str], Dict[str, float]]:
    """
    Greedy selection to build EXACT size = ensemble_size (if feasible).

    Cost:
      cost = latency_term + accuracy_term
      latency_term = clamp(Te/D, 0.1, 0.9), only if Te/D < 1
      accuracy_term = alpha_now * (MaxMS[size] / sum_bytes_MS)

    Te(MS) = max(wait+compute) across models in MS (parallel completion estimate)
    """
    D_sec = deadline_ms / 1000.0
    if D_sec <= 0:
        return [], {}

    # Max parallel models allowed by resources
    max_parallel_models = min(MAX_MODEL_SIZE, K // C, len(M_TOTAL))
    target_k = min(ensemble_size, max_parallel_models)
    if target_k <= 0:
        return [], {}

    # Precompute MaxMS[size]
    sorted_by_size = sorted(M_TOTAL, key=lambda m: MODEL_SIZES[m], reverse=True)
    MaxMS: Dict[int, int] = {}
    rolling_sum = 0
    for i, m in enumerate(sorted_by_size):
        rolling_sum += MODEL_SIZES[m]
        size = i + 1
        if size <= max_parallel_models:
            MaxMS[size] = rolling_sum

    def estimate_Te(MS: List[str]) -> float:
        times = []
        for m in MS:
            wait_t = float(wait_results.get(m, float("inf")))
            compute_t = float(MODEL_PROFILES[m]["latency"])
            times.append(wait_t + compute_t)
        return max(times) if times else float("inf")

    def latency_term_for(MS: List[str]):
        T_e = estimate_Te(MS)
        raw = T_e / D_sec
        if raw >= 1.0:
            return None, T_e, raw
        lt = min(max(raw, 0.1), 0.9)
        return lt, T_e, raw

    def accuracy_term_for(MS: List[str]):
        size = len(MS)
        sum_bytes = sum(MODEL_SIZES[m] for m in MS)
        if sum_bytes <= 0 or size not in MaxMS:
            return None, sum_bytes
        at = alpha_now * (MaxMS[size] / sum_bytes)
        return at, sum_bytes

    # Non-greedy policies (optional, keep if you use them)
    if POLICY.startswith("best_acc_"):
        k = int(POLICY.split("_")[-1])
        k = min(k, target_k, len(M_TOTAL))

        def get_acc(m: str) -> float:
            if m in MODEL_PROFILES and "accuracy" in MODEL_PROFILES[m]:
                return float(MODEL_PROFILES[m]["accuracy"])
            return float("-inf")

        sorted_by_acc = sorted(M_TOTAL, key=get_acc, reverse=True)
        M_D = sorted_by_acc[:k]
        return M_D, {m: wait_results.get(m, float("inf")) for m in M_D}

    if POLICY == "randomized":
        import random
        k = target_k
        M_D = random.sample(M_TOTAL, k)
        return M_D, {m: wait_results.get(m, float("inf")) for m in M_D}

    # Greedy: build to EXACT target_k (if possible)
    MS: List[str] = []
    remaining = list(M_TOTAL)

    logger.info(
        f"[SELECT_BEGIN] deadline_ms={deadline_ms} D_sec={D_sec:.3f} "
        f"target_k={target_k} max_parallel_models={max_parallel_models} alpha={alpha_now:.3f}"
    )

    for step in range(1, target_k + 1):
        best_candidate = None
        best_cost = float("inf")
        best_dbg = None

        for m in remaining:
            trial = MS + [m]

            # core constraint
            if len(trial) * C > K:
                continue

            lt, T_e, raw = latency_term_for(trial)
            if lt is None:
                continue

            at, sum_bytes = accuracy_term_for(trial)
            if at is None:
                continue

            cost = lt + at
            if cost < best_cost:
                best_cost = cost
                best_candidate = m
                best_dbg = (trial, T_e, raw, lt, at, sum_bytes, cost)

        if best_candidate is None:
            logger.info(f"[SELECT_STOP] step={step} reason=no_feasible_candidate current_MS={MS}")
            break

        trial, T_e, raw, lt, at, sum_bytes, cost = best_dbg
        logger.info(
            f"[SELECT_CHOOSE] step={step}/{target_k} choose={best_candidate} "
            f"trial={trial} Te={T_e:.4f}s raw={raw:.3f} lt={lt:.3f} at={at:.3f} "
            f"sum_bytes={sum_bytes} cost={cost:.3f}"
        )

        MS.append(best_candidate)
        remaining.remove(best_candidate)

    if not MS:
        fastest = min(M_TOTAL, key=lambda m: float(MODEL_PROFILES[m]["latency"]))
        MS = [fastest]
        logger.warning(f"[SELECT_FALLBACK] no_feasible_set fallback_fastest={fastest}")

    logger.info(f"[SELECT_DONE] selected_MS={MS} size={len(MS)} target_k={target_k}")
    return MS, {m: wait_results.get(m, float("inf")) for m in MS}


# -----------------------------
# Main invoke with cascaded execution + adaptive alpha + logging
# -----------------------------
async def main_ensemble_invoke(
    transaction_id: str,
    deadline: int,
    image_b64: str,
    selected_folder: Optional[str] = None
) -> dict:

    start_time = time.perf_counter()
    if not image_b64:
        raise ValueError("image_b64 is required")
    if selected_folder is None:
        selected_folder = "unknown"

    # Record request for QPS estimation
    now = time.perf_counter()
    record_request(now, QPS_WINDOW_SEC)
    qps_est = get_qps(QPS_WINDOW_SEC)

    # gRPC connection
    async_channel = grpc.aio.insecure_channel(SERVER_ADDRESS)
    stub = pb2_grpc.IluvatarWorkerStub(async_channel)

    # Wait time estimates (congestion signal)
    wait_results = wait_time_iluvatar.main()

    # Wait summary
    all_wait_vals = [float(v) for v in wait_results.values() if v is not None]
    if all_wait_vals:
        logger.info(
            f"[WAIT_SUMMARY] tx={transaction_id} mean_wait={sum(all_wait_vals)/len(all_wait_vals):.4f}s "
            f"max_wait={max(all_wait_vals):.4f}s min_wait={min(all_wait_vals):.4f}s"
        )
    else:
        logger.info(f"[WAIT_SUMMARY] tx={transaction_id} no_wait_data=True")

    # Adaptive alpha
    # alpha_now = compute_adaptive_alpha(
    #     qps=qps_est,
    #     wait_results=wait_results,
    #     alpha_min=ALPHA_MIN,
    #     alpha_max=ALPHA_MAX,
    #     qps_low=QPS_LOW,
    #     qps_high=QPS_HIGH,
    #     wait_low=WAIT_LOW,
    #     wait_high=WAIT_HIGH,
    # )

    if ALPHA_MODE == "static":
        alpha_now = float(ALPHA_STATIC)
    else:
        alpha_now = compute_adaptive_alpha(
            qps=qps_est,
            wait_results=wait_results,
            alpha_min=ALPHA_MIN,
            alpha_max=ALPHA_MAX,
            qps_low=QPS_LOW,
            qps_high=QPS_HIGH,
            wait_low=WAIT_LOW,
            wait_high=WAIT_HIGH,
        )

    logger.info(
        f"[REQ_START] tx={transaction_id} deadline_ms={deadline} qps={qps_est:.2f} "
        f"alpha={alpha_now:.3f} threshold={THRESHOLD} policy={POLICY} "
        f"ensemble_size={ENSEMBLE_SIZE} selected_folder={selected_folder}"
    )

    # Select model set
    M_D, total_estimates = build_model_set(
        wait_results=wait_results,
        deadline_ms=deadline,
        ensemble_size=ENSEMBLE_SIZE,
        alpha_now=alpha_now,
    )

    if not M_D:
        fastest_model = min(MODEL_PROFILES, key=lambda m: float(MODEL_PROFILES[m]["latency"]))
        M_D = [fastest_model]
        logger.warning(f"[SELECT_EMPTY] tx={transaction_id} fallback_fastest={fastest_model}")

    # Cascaded execution: fastest first
    M_D = sorted(M_D, key=lambda m: float(MODEL_PROFILES[m]["latency"]))

    logger.info(f"[SELECT] tx={transaction_id} selected_models_sorted={M_D}")
    logger.info(f"[SELECT_WAITS] tx={transaction_id} waits_selected={ {m: float(total_estimates.get(m, -1)) for m in M_D} }")

    results: List[dict] = []
    stop_reason = "ran_all"

    for i, m in enumerate(M_D):
        t0 = time.perf_counter()
        logger.info(f"[RUN] tx={transaction_id} step={i+1}/{len(M_D)} model={m} start=True")

        try:
            res = await send_request(stub, m, image_b64)
        except Exception as e:
            logger.exception(f"[RUN_FAIL] tx={transaction_id} model={m} error={e}")
            continue

        wall_s = time.perf_counter() - t0

        if not res.get("success", False):
            logger.warning(f"[RUN_BAD] tx={transaction_id} model={m} success=False wall_s={wall_s:.4f}")
            continue

        conf = float(res.get("probability", 0.0))
        label = res.get("label")

        logger.info(
            f"[RUN_OK] tx={transaction_id} model={m} label={label} conf={conf:.4f} "
            f"rpc_latency_s={float(res.get('latency', -1)):.4f} wall_s={wall_s:.4f} "
            f"container_state={res.get('container_state')}"
        )

        # passed = conf >= THRESHOLD
        # logger.info(
        #     f"[THRESH] tx={transaction_id} model={m} conf={conf:.4f} threshold={THRESHOLD:.2f} pass={passed}"
        # )
        # stage-specific threshold (fallback to THRESHOLD if list is shorter)
        # stage_thr = THRESHOLD
        # if "THRESHOLD_STAGE" in globals():
        #     if isinstance(THRESHOLD_STAGE, list) and len(THRESHOLD_STAGE) > 0:
        #         if i < len(THRESHOLD_STAGE):
        #             stage_thr = THRESHOLD_STAGE[i]
        #
        # passed = conf >= stage_thr
        #
        # logger.info(
        #     f"[THRESH] tx={transaction_id} model={m} conf={conf:.4f} "
        #     f"threshold={stage_thr:.2f} pass={passed}"
        # )

        stage_thr = THRESHOLD  # default

        # Use stage thresholds only if THRESHOLD_STAGE is a non-empty list
        if isinstance(THRESHOLD_STAGE, list) and len(THRESHOLD_STAGE) > 0:
            if i < len(THRESHOLD_STAGE):
                stage_thr = THRESHOLD_STAGE[i]

        passed = conf >= stage_thr

        logger.info(
            f"[THRESH] tx={transaction_id} model={m} conf={conf:.4f} "
            f"threshold={stage_thr:.2f} pass={passed}"
        )

        results.append(res)

        if passed:
            stop_reason = f"early_exit_at_{m}"
            logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
            break

    if not results:
        end_time = time.perf_counter()
        e2e_ms = (end_time - start_time) * 1000
        logger.error(f"[REQ_END] tx={transaction_id} success=False reason=no_successful_models e2e_ms={e2e_ms:.2f}")
        return {
            "selected_models": M_D,
            "executed_models": [],
            "label": -1,
            "accuracy": 0.0,
            "combiner_policy": "FAILED",
            "e2e_time_ms": e2e_ms,
            "success": False,
            "selected_folder": selected_folder,
            "wait_times": total_estimates,
            "per_model": {},
            "ensemble_size": ENSEMBLE_SIZE,
            "threshold": THRESHOLD,
            "alpha": alpha_now,
            "qps_est": qps_est,
            "stop_reason": stop_reason,
        }

    # Combine outputs once (only executed models)
    final_result = combine_outputs(
        results,
        policy="weighted_majority",
        historical_acc=OMEGA,
        model_weights=MODEL_WEIGHTS,
        ground_truth=selected_folder,
        gamma=GAMMA,
        update_weights=True,
        label_matcher=wnid_matches_text_label,
        rho=RHO,
    )

    save_model_weights_atomic(WEIGHTS_STATE_PATH, MODEL_WEIGHTS)

    # Feedback updates
    for res in results:
        OMEGA[res["model"]] = (1 - ETA) * OMEGA[res["model"]] + ETA * res["probability"]
        active_models.add(res["model"])

    per_model = {}
    for res in results:
        per_model[res["model"]] = {
            "label": res.get("label"),
            "probability": float(res.get("probability", 0.0)),
            "latency_s": float(res.get("latency", -1)),
            "success": bool(res.get("success", False)),
            "state": res.get("container_state", "UNKNOWN"),
        }

    end_time = time.perf_counter()
    e2e_ms = (end_time - start_time) * 1000

    logger.info(
        f"[COMBINE] tx={transaction_id} executed_models={[r['model'] for r in results]} "
        f"combiner={final_result.get('combiner_policy')} final_label={final_result.get('label')} "
        f"final_acc={final_result.get('accuracy')}"
    )

    logger.info(
        f"[REQ_END] tx={transaction_id} success={final_result.get('success', True)} "
        f"stop_reason={stop_reason} e2e_ms={e2e_ms:.2f}"
    )

    return {
        "selected_models": M_D,
        "executed_models": [r["model"] for r in results],
        "label": final_result["label"],
        "accuracy": final_result["accuracy"],
        "combiner_policy": final_result["combiner_policy"],
        "e2e_time_ms": e2e_ms,
        "success": final_result.get("success", True),
        "selected_folder": selected_folder,
        "wait_times": total_estimates,
        "per_model": per_model,
        "ensemble_size": ENSEMBLE_SIZE,
        "threshold": THRESHOLD,
        "main_policy": POLICY,
        "alpha": alpha_now,
        "qps_est": qps_est,
        "stop_reason": stop_reason,
        "log_file": LOG_PATH,
    }
