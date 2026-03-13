# import grpc
# import json
# import uuid
# import time
# import asyncio
# import logging
# import os
# from collections import deque
# from typing import Dict, List, Tuple, Optional
# from logging.handlers import RotatingFileHandler
#
# # Use ONE set of protobuf imports (avoid duplicates)
# import ckn_controller.iluvatar_rpc_pb2 as pb2
# import ckn_controller.iluvatar_rpc_pb2_grpc as pb2_grpc
#
# from ckn_controller.ckn_config import (
#     SERVER_ADDRESS,
#     M_TOTAL,
#     POLICY,
#     K,
#     C,
#     ALPHA,  # legacy fixed alpha (we override dynamically)
#     ETA,
#     MODEL_PROFILES,
#     OMEGA,
#     MAX_MODEL_SIZE,
#     DEFAULT_WEIGHTS,
#     GAMMA,
#     RHO,
#     WEIGHTS_STATE_PATH,
#     MODEL_SIZES,
#
#     # --- Cascade parameters ---
#     ENSEMBLE_SIZE,
#     THRESHOLD,
#     THRESHOLD_STAGE,
#
#     # --- Alpha control ---
#     ALPHA_MODE,  # "static" or "adaptive"
#     ALPHA_STATIC,  # used if static mode
#     ALPHA_MIN,  # used if adaptive mode
#     ALPHA_MAX,
#
#     # --- Load normalization ---
#     QPS_WINDOW_SEC,
#     QPS_LOW,
#     QPS_HIGH,
#     WAIT_LOW,
#     WAIT_HIGH,
# )
#
# import wait_time_iluvatar
# from ckn_controller.output_combiner import combine_outputs
# from ckn_controller.weights_io import load_model_weights, save_model_weights_atomic
# from ckn_controller.label_utils import wnid_matches_text_label
#
# # -----------------------------
# # New parameters (safe defaults)
# # -----------------------------
# # If you define these in ckn_config.py, those values will be used.
# # try:
# #     from ckn_controller.ckn_config import ENSEMBLE_SIZE
# # except Exception:
# #     ENSEMBLE_SIZE = 3
# #
# # try:
# #     from ckn_controller.ckn_config import THRESHOLD
# # except Exception:
# #     THRESHOLD = 0.85
# #
# # try:
# #     from ckn_controller.ckn_config import ALPHA_MIN, ALPHA_MAX
# # except Exception:
# #     ALPHA_MIN, ALPHA_MAX = 0.2, 1.0
# #
# # try:
# #     from ckn_controller.ckn_config import QPS_WINDOW_SEC, QPS_LOW, QPS_HIGH
# # except Exception:
# #     QPS_WINDOW_SEC, QPS_LOW, QPS_HIGH = 1.0, 10.0, 100.0
# #
# # try:
# #     from ckn_controller.ckn_config import WAIT_LOW, WAIT_HIGH
# # except Exception:
# #     WAIT_LOW, WAIT_HIGH = 0.01, 0.2  # seconds
#
#
# # -----------------------------
# # Logging setup (file + console)
# # -----------------------------
# LOG_DIR = os.environ.get("MODE_S_LOG_DIR", "./logs")
# os.makedirs(LOG_DIR, exist_ok=True)
# LOG_PATH = os.path.join(LOG_DIR, "mode_s_cascade.log")
#
# logger = logging.getLogger("mode_s")
# logger.setLevel(logging.INFO)
#
# if not logger.handlers:
#     fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
#
#     file_handler = RotatingFileHandler(
#         LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=5
#     )
#     file_handler.setFormatter(fmt)
#     logger.addHandler(file_handler)
#
#     console_handler = logging.StreamHandler()
#     console_handler.setFormatter(fmt)
#     logger.addHandler(console_handler)
#
#
# MODEL_WEIGHTS = load_model_weights(WEIGHTS_STATE_PATH, DEFAULT_WEIGHTS)
# active_models = set()
#
#
# # -----------------------------
# # QPS tracking (sliding window)
# # -----------------------------
# REQUEST_TS = deque()
#
# def record_request(now: float, window_sec: float) -> None:
#     REQUEST_TS.append(now)
#     cutoff = now - window_sec
#     while REQUEST_TS and REQUEST_TS[0] < cutoff:
#         REQUEST_TS.popleft()
#
# def get_qps(window_sec: float) -> float:
#     return len(REQUEST_TS) / max(window_sec, 1e-9)
#
#
# # -----------------------------
# # Load-adaptive alpha (hybrid)
# # Primary signal: Ilúvatar wait time
# # Secondary signal: QPS
# # -----------------------------
# def _clamp01(x: float) -> float:
#     return max(0.0, min(1.0, x))
#
# def compute_adaptive_alpha(
#     qps: float,
#     wait_results: Dict[str, float],
#     alpha_min: float,
#     alpha_max: float,
#     qps_low: float,
#     qps_high: float,
#     wait_low: float,
#     wait_high: float,
# ) -> float:
#     # Normalize QPS
#     if qps_high <= qps_low:
#         qps_norm = 0.0
#     else:
#         qps_norm = _clamp01((qps - qps_low) / (qps_high - qps_low))
#
#     # Normalize wait (mean wait)
#     waits = [float(v) for v in wait_results.values() if v is not None]
#     mean_wait = sum(waits) / len(waits) if waits else 0.0
#
#     if wait_high <= wait_low:
#         wait_norm = 0.0
#     else:
#         wait_norm = _clamp01((mean_wait - wait_low) / (wait_high - wait_low))
#
#     # Hybrid load score: prioritize wait time
#     load_score = max(wait_norm, 0.5 * qps_norm)
#
#     # Low load -> alpha_max, High load -> alpha_min
#     alpha_now = alpha_max - load_score * (alpha_max - alpha_min)
#     return max(alpha_min, min(alpha_max, alpha_now))
#
#
# # -----------------------------
# # Ilúvatar invocation
# # -----------------------------
# async def send_request(stub, model_name: str, image_b64: str) -> dict:
#     request = pb2.InvokeRequest(
#         function_name=model_name,
#         function_version="1",
#         json_args=json.dumps({"model_name": model_name, "image_data": image_b64}),
#         transaction_id=str(uuid.uuid4()),
#     )
#     response = await stub.invoke(request)
#     result_json = json.loads(response.json_result)
#     return {
#         "model": model_name,
#         "label": result_json["body"]["Prediction Class"],
#         "probability": float(result_json["body"]["Probability"]),
#         "latency": response.duration_us / 1e6,
#         "success": response.success,
#         "container_state": pb2.ContainerState.Name(response.container_state),
#     }
#
#
# # -----------------------------
# # Model selection: EXACT ENSEMBLE_SIZE
# # Uses adaptive alpha inside cost function.
# # -----------------------------
# def build_model_set(
#     wait_results: Dict[str, float],
#     deadline_ms: int,
#     ensemble_size: int,
#     alpha_now: float
# ) -> Tuple[List[str], Dict[str, float]]:
#     """
#     Greedy selection to build EXACT size = ensemble_size (if feasible).
#
#     Cost:
#       cost = latency_term + accuracy_term
#       latency_term = clamp(Te/D, 0.1, 0.9), only if Te/D < 1
#       accuracy_term = alpha_now * (MaxMS[size] / sum_bytes_MS)
#
#     Te(MS) = max(wait+compute) across models in MS (parallel completion estimate)
#     """
#     D_sec = deadline_ms / 1000.0
#     if D_sec <= 0:
#         return [], {}
#
#     # Max parallel models allowed by resources
#     max_parallel_models = min(MAX_MODEL_SIZE, K // C, len(M_TOTAL))
#     target_k = min(ensemble_size, max_parallel_models)
#     if target_k <= 0:
#         return [], {}
#
#     # Precompute MaxMS[size]
#     sorted_by_size = sorted(M_TOTAL, key=lambda m: MODEL_SIZES[m], reverse=True)
#     MaxMS: Dict[int, int] = {}
#     rolling_sum = 0
#     for i, m in enumerate(sorted_by_size):
#         rolling_sum += MODEL_SIZES[m]
#         size = i + 1
#         if size <= max_parallel_models:
#             MaxMS[size] = rolling_sum
#
#     def estimate_Te(MS: List[str]) -> float:
#         times = []
#         for m in MS:
#             wait_t = float(wait_results.get(m, float("inf")))
#             compute_t = float(MODEL_PROFILES[m]["latency"])
#             times.append(wait_t + compute_t)
#         return max(times) if times else float("inf")
#
#     def latency_term_for(MS: List[str]):
#         T_e = estimate_Te(MS)
#         raw = T_e / D_sec
#         if raw >= 1.0:
#             return None, T_e, raw
#         lt = min(max(raw, 0.1), 0.9)
#         return lt, T_e, raw
#
#     def accuracy_term_for(MS: List[str]):
#         size = len(MS)
#         sum_bytes = sum(MODEL_SIZES[m] for m in MS)
#         if sum_bytes <= 0 or size not in MaxMS:
#             return None, sum_bytes
#         at = alpha_now * (MaxMS[size] / sum_bytes)
#         return at, sum_bytes
#
#     # Non-greedy policies (optional, keep if you use them)
#     if POLICY.startswith("best_acc_"):
#         k = int(POLICY.split("_")[-1])
#         k = min(k, target_k, len(M_TOTAL))
#
#         def get_acc(m: str) -> float:
#             if m in MODEL_PROFILES and "accuracy" in MODEL_PROFILES[m]:
#                 return float(MODEL_PROFILES[m]["accuracy"])
#             return float("-inf")
#
#         sorted_by_acc = sorted(M_TOTAL, key=get_acc, reverse=True)
#         M_D = sorted_by_acc[:k]
#         return M_D, {m: wait_results.get(m, float("inf")) for m in M_D}
#
#     if POLICY == "randomized":
#         import random
#         k = target_k
#         M_D = random.sample(M_TOTAL, k)
#         return M_D, {m: wait_results.get(m, float("inf")) for m in M_D}
#
#     # Greedy: build to EXACT target_k (if possible)
#     MS: List[str] = []
#     remaining = list(M_TOTAL)
#
#     logger.info(
#         f"[SELECT_BEGIN] deadline_ms={deadline_ms} D_sec={D_sec:.3f} "
#         f"target_k={target_k} max_parallel_models={max_parallel_models} alpha={alpha_now:.3f}"
#     )
#
#     for step in range(1, target_k + 1):
#         best_candidate = None
#         best_cost = float("inf")
#         best_dbg = None
#
#         for m in remaining:
#             trial = MS + [m]
#
#             # core constraint
#             if len(trial) * C > K:
#                 continue
#
#             lt, T_e, raw = latency_term_for(trial)
#             if lt is None:
#                 continue
#
#             at, sum_bytes = accuracy_term_for(trial)
#             if at is None:
#                 continue
#
#             cost = lt + at
#             if cost < best_cost:
#                 best_cost = cost
#                 best_candidate = m
#                 best_dbg = (trial, T_e, raw, lt, at, sum_bytes, cost)
#
#         if best_candidate is None:
#             logger.info(f"[SELECT_STOP] step={step} reason=no_feasible_candidate current_MS={MS}")
#             break
#
#         trial, T_e, raw, lt, at, sum_bytes, cost = best_dbg
#         logger.info(
#             f"[SELECT_CHOOSE] step={step}/{target_k} choose={best_candidate} "
#             f"trial={trial} Te={T_e:.4f}s raw={raw:.3f} lt={lt:.3f} at={at:.3f} "
#             f"sum_bytes={sum_bytes} cost={cost:.3f}"
#         )
#
#         MS.append(best_candidate)
#         remaining.remove(best_candidate)
#
#     if not MS:
#         fastest = min(M_TOTAL, key=lambda m: float(MODEL_PROFILES[m]["latency"]))
#         MS = [fastest]
#         logger.warning(f"[SELECT_FALLBACK] no_feasible_set fallback_fastest={fastest}")
#
#     logger.info(f"[SELECT_DONE] selected_MS={MS} size={len(MS)} target_k={target_k}")
#     return MS, {m: wait_results.get(m, float("inf")) for m in MS}
#
#
# # -----------------------------
# # Main invoke with cascaded execution + adaptive alpha + logging
# # -----------------------------
# async def main_ensemble_invoke(
#     transaction_id: str,
#     deadline: int,
#     image_b64: str,
#     selected_folder: Optional[str] = None
# ) -> dict:
#
#     start_time = time.perf_counter()
#     if not image_b64:
#         raise ValueError("image_b64 is required")
#     if selected_folder is None:
#         selected_folder = "unknown"
#
#     # Record request for QPS estimation
#     now = time.perf_counter()
#     record_request(now, QPS_WINDOW_SEC)
#     qps_est = get_qps(QPS_WINDOW_SEC)
#
#     # gRPC connection
#     async_channel = grpc.aio.insecure_channel(SERVER_ADDRESS)
#     stub = pb2_grpc.IluvatarWorkerStub(async_channel)
#
#     # Wait time estimates (congestion signal)
#     wait_results = wait_time_iluvatar.main()
#
#     # Wait summary
#     all_wait_vals = [float(v) for v in wait_results.values() if v is not None]
#     if all_wait_vals:
#         logger.info(
#             f"[WAIT_SUMMARY] tx={transaction_id} mean_wait={sum(all_wait_vals)/len(all_wait_vals):.4f}s "
#             f"max_wait={max(all_wait_vals):.4f}s min_wait={min(all_wait_vals):.4f}s"
#         )
#     else:
#         logger.info(f"[WAIT_SUMMARY] tx={transaction_id} no_wait_data=True")
#
#     # Adaptive alpha
#     # alpha_now = compute_adaptive_alpha(
#     #     qps=qps_est,
#     #     wait_results=wait_results,
#     #     alpha_min=ALPHA_MIN,
#     #     alpha_max=ALPHA_MAX,
#     #     qps_low=QPS_LOW,
#     #     qps_high=QPS_HIGH,
#     #     wait_low=WAIT_LOW,
#     #     wait_high=WAIT_HIGH,
#     # )
#
#     if ALPHA_MODE == "static":
#         alpha_now = float(ALPHA_STATIC)
#     else:
#         alpha_now = compute_adaptive_alpha(
#             qps=qps_est,
#             wait_results=wait_results,
#             alpha_min=ALPHA_MIN,
#             alpha_max=ALPHA_MAX,
#             qps_low=QPS_LOW,
#             qps_high=QPS_HIGH,
#             wait_low=WAIT_LOW,
#             wait_high=WAIT_HIGH,
#         )
#
#     logger.info(
#         f"[REQ_START] tx={transaction_id} deadline_ms={deadline} qps={qps_est:.2f} "
#         f"alpha={alpha_now:.3f} threshold={THRESHOLD} policy={POLICY} "
#         f"ensemble_size={ENSEMBLE_SIZE} selected_folder={selected_folder}"
#     )
#
#     # Select model set
#     M_D, total_estimates = build_model_set(
#         wait_results=wait_results,
#         deadline_ms=deadline,
#         ensemble_size=ENSEMBLE_SIZE,
#         alpha_now=alpha_now,
#     )
#
#     if not M_D:
#         fastest_model = min(MODEL_PROFILES, key=lambda m: float(MODEL_PROFILES[m]["latency"]))
#         M_D = [fastest_model]
#         logger.warning(f"[SELECT_EMPTY] tx={transaction_id} fallback_fastest={fastest_model}")
#
#     # Cascaded execution: fastest first
#     M_D = sorted(M_D, key=lambda m: float(MODEL_PROFILES[m]["latency"]))
#
#     logger.info(f"[SELECT] tx={transaction_id} selected_models_sorted={M_D}")
#     logger.info(f"[SELECT_WAITS] tx={transaction_id} waits_selected={ {m: float(total_estimates.get(m, -1)) for m in M_D} }")
#
#     results: List[dict] = []
#     stop_reason = "ran_all"
#
#     for i, m in enumerate(M_D):
#         t0 = time.perf_counter()
#         logger.info(f"[RUN] tx={transaction_id} step={i+1}/{len(M_D)} model={m} start=True")
#
#         try:
#             res = await send_request(stub, m, image_b64)
#         except Exception as e:
#             logger.exception(f"[RUN_FAIL] tx={transaction_id} model={m} error={e}")
#             continue
#
#         wall_s = time.perf_counter() - t0
#
#         if not res.get("success", False):
#             logger.warning(f"[RUN_BAD] tx={transaction_id} model={m} success=False wall_s={wall_s:.4f}")
#             continue
#
#         conf = float(res.get("probability", 0.0))
#         label = res.get("label")
#
#         logger.info(
#             f"[RUN_OK] tx={transaction_id} model={m} label={label} conf={conf:.4f} "
#             f"rpc_latency_s={float(res.get('latency', -1)):.4f} wall_s={wall_s:.4f} "
#             f"container_state={res.get('container_state')}"
#         )
#
#         # passed = conf >= THRESHOLD
#         # logger.info(
#         #     f"[THRESH] tx={transaction_id} model={m} conf={conf:.4f} threshold={THRESHOLD:.2f} pass={passed}"
#         # )
#         # stage-specific threshold (fallback to THRESHOLD if list is shorter)
#         # stage_thr = THRESHOLD
#         # if "THRESHOLD_STAGE" in globals():
#         #     if isinstance(THRESHOLD_STAGE, list) and len(THRESHOLD_STAGE) > 0:
#         #         if i < len(THRESHOLD_STAGE):
#         #             stage_thr = THRESHOLD_STAGE[i]
#         #
#         # passed = conf >= stage_thr
#         #
#         # logger.info(
#         #     f"[THRESH] tx={transaction_id} model={m} conf={conf:.4f} "
#         #     f"threshold={stage_thr:.2f} pass={passed}"
#         # )
#
#         stage_thr = THRESHOLD  # default
#
#         # Use stage thresholds only if THRESHOLD_STAGE is a non-empty list
#         if isinstance(THRESHOLD_STAGE, list) and len(THRESHOLD_STAGE) > 0:
#             if i < len(THRESHOLD_STAGE):
#                 stage_thr = THRESHOLD_STAGE[i]
#
#         passed = conf >= stage_thr
#
#         logger.info(
#             f"[THRESH] tx={transaction_id} model={m} conf={conf:.4f} "
#             f"threshold={stage_thr:.2f} pass={passed}"
#         )
#
#         results.append(res)
#
#         if passed:
#             stop_reason = f"early_exit_at_{m}"
#             logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
#             break
#
#     if not results:
#         end_time = time.perf_counter()
#         e2e_ms = (end_time - start_time) * 1000
#         logger.error(f"[REQ_END] tx={transaction_id} success=False reason=no_successful_models e2e_ms={e2e_ms:.2f}")
#         return {
#             "selected_models": M_D,
#             "executed_models": [],
#             "label": -1,
#             "accuracy": 0.0,
#             "combiner_policy": "FAILED",
#             "e2e_time_ms": e2e_ms,
#             "success": False,
#             "selected_folder": selected_folder,
#             "wait_times": total_estimates,
#             "per_model": {},
#             "ensemble_size": ENSEMBLE_SIZE,
#             "threshold": THRESHOLD,
#             "alpha": alpha_now,
#             "qps_est": qps_est,
#             "stop_reason": stop_reason,
#         }
#
#     # Combine outputs once (only executed models)
#     final_result = combine_outputs(
#         results,
#         policy="weighted_majority",
#         historical_acc=OMEGA,
#         model_weights=MODEL_WEIGHTS,
#         ground_truth=selected_folder,
#         gamma=GAMMA,
#         update_weights=True,
#         label_matcher=wnid_matches_text_label,
#         rho=RHO,
#     )
#
#     save_model_weights_atomic(WEIGHTS_STATE_PATH, MODEL_WEIGHTS)
#
#     # Feedback updates
#     for res in results:
#         OMEGA[res["model"]] = (1 - ETA) * OMEGA[res["model"]] + ETA * res["probability"]
#         active_models.add(res["model"])
#
#     per_model = {}
#     for res in results:
#         per_model[res["model"]] = {
#             "label": res.get("label"),
#             "probability": float(res.get("probability", 0.0)),
#             "latency_s": float(res.get("latency", -1)),
#             "success": bool(res.get("success", False)),
#             "state": res.get("container_state", "UNKNOWN"),
#         }
#
#     end_time = time.perf_counter()
#     e2e_ms = (end_time - start_time) * 1000
#
#     logger.info(
#         f"[COMBINE] tx={transaction_id} executed_models={[r['model'] for r in results]} "
#         f"combiner={final_result.get('combiner_policy')} final_label={final_result.get('label')} "
#         f"final_acc={final_result.get('accuracy')}"
#     )
#
#     logger.info(
#         f"[REQ_END] tx={transaction_id} success={final_result.get('success', True)} "
#         f"stop_reason={stop_reason} e2e_ms={e2e_ms:.2f}"
#     )
#
#     return {
#         "selected_models": M_D,
#         "executed_models": [r["model"] for r in results],
#         "label": final_result["label"],
#         "accuracy": final_result["accuracy"],
#         "combiner_policy": final_result["combiner_policy"],
#         "e2e_time_ms": e2e_ms,
#         "success": final_result.get("success", True),
#         "selected_folder": selected_folder,
#         "wait_times": total_estimates,
#         "per_model": per_model,
#         "ensemble_size": ENSEMBLE_SIZE,
#         "threshold": THRESHOLD,
#         "main_policy": POLICY,
#         "alpha": alpha_now,
#         "qps_est": qps_est,
#         "stop_reason": stop_reason,
#         "log_file": LOG_PATH,
#     }




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
    ALPHA_MODE,        # "static" or "adaptive"
    ALPHA_STATIC,      # used if static mode
    ALPHA_MIN,         # used if adaptive mode
    ALPHA_MAX,

    # --- Load normalization ---
    QPS_WINDOW_SEC,
    QPS_LOW,
    QPS_HIGH,

    # --- Parallel-first policy ---
    PARALLEL_FIRST_N,  # set to 2 for your policy
)

import wait_time_iluvatar
from ckn_controller.output_combiner import combine_outputs
from ckn_controller.weights_io import load_model_weights, save_model_weights_atomic
from ckn_controller.label_utils import wnid_matches_text_label


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
# -----------------------------
def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def compute_adaptive_alpha(
    qps: float,
    alpha_min: float,
    alpha_max: float,
    qps_low: float,
    qps_high: float,
) -> float:
    if qps_high <= qps_low:
        qps_norm = 0.0
    else:
        qps_norm = _clamp01((qps - qps_low) / (qps_high - qps_low))

    load_score = qps_norm
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


def _get_stage_threshold(stage_index: int) -> float:
    """
    Stage-specific threshold:
      - if THRESHOLD_STAGE list exists and has entry for stage_index, use it
      - otherwise fallback to THRESHOLD
    """
    try:
        if isinstance(THRESHOLD_STAGE, list) and len(THRESHOLD_STAGE) > stage_index:
            return float(THRESHOLD_STAGE[stage_index])
    except Exception:
        pass
    return float(THRESHOLD)


# -----------------------------
# Model selection: EXACT ENSEMBLE_SIZE
# -----------------------------
def build_model_set(
    wait_results: Dict[str, float],
    deadline_ms: int,
    ensemble_size: int,
    alpha_now: float
) -> Tuple[List[str], Dict[str, float]]:
    """
    Greedy selection to build EXACT size = ensemble_size (if feasible).

    cost = latency_term + accuracy_term
      latency_term = clamp(Te/D, 0.1, 0.9), only if Te/D < 1
      accuracy_term = alpha_now * (MaxMS[size] / sum_bytes_MS)

    Te(MS) = max(wait+compute) across models in MS (parallel completion estimate)
    """
    D_sec = deadline_ms / 1000.0
    if D_sec <= 0:
        return [], {}

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

    # Optional policies
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

    # Greedy build
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
# Main invoke:
#   - run first 2 models in parallel
#   - if MODEL-1 passes -> return it directly AND cancel other task
#   - if MODEL-1 fails but MODEL-2 passes -> aggregate MODEL-1+MODEL-2
#   - else continue sequentially with remaining models
#   - IMPORTANT: if only 1 executed model, DO NOT call combine_outputs
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

    # QPS estimate
    now = time.perf_counter()
    record_request(now, QPS_WINDOW_SEC)
    qps_est = get_qps(QPS_WINDOW_SEC)

    # gRPC connection
    async_channel = grpc.aio.insecure_channel(SERVER_ADDRESS)
    stub = pb2_grpc.IluvatarWorkerStub(async_channel)

    # Wait estimates
    wait_results = wait_time_iluvatar.main()
    all_wait_vals = [float(v) for v in wait_results.values() if v is not None]
    if all_wait_vals:
        logger.info(
            f"[WAIT_SUMMARY] tx={transaction_id} mean_wait={sum(all_wait_vals)/len(all_wait_vals):.4f}s "
            f"max_wait={max(all_wait_vals):.4f}s min_wait={min(all_wait_vals):.4f}s"
        )
    else:
        logger.info(f"[WAIT_SUMMARY] tx={transaction_id} no_wait_data=True")

    # Alpha
    if str(ALPHA_MODE).lower() == "static":
        alpha_now = float(ALPHA_STATIC)
    else:
        alpha_now = compute_adaptive_alpha(
            qps=qps_est,
            alpha_min=ALPHA_MIN,
            alpha_max=ALPHA_MAX,
            qps_low=QPS_LOW,
            qps_high=QPS_HIGH,
        )

    logger.info(
        f"[REQ_START] tx={transaction_id} deadline_ms={deadline} qps={qps_est:.2f} "
        f"alpha={alpha_now:.3f} alpha_mode={ALPHA_MODE} policy={POLICY} "
        f"ensemble_size={ENSEMBLE_SIZE} selected_folder={selected_folder}"
    )

    # Select ensemble
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

    # Fastest first
    # M_D = sorted(M_D, key=lambda m: float(MODEL_PROFILES[m]["latency"]))

    logger.info(f"[SELECT] tx={transaction_id} selected_models={M_D}")
    logger.info(f"[SELECT_WAITS] tx={transaction_id} waits_selected={ {m: float(total_estimates.get(m, -1)) for m in M_D} }")

    results: List[dict] = []
    stop_reason = "ran_all"

    # --- Parallel-first-two (policy assumes N=2) ---
    first_n = int(PARALLEL_FIRST_N) if PARALLEL_FIRST_N is not None else 0
    first_n = max(0, min(first_n, len(M_D)))

    first_batch = M_D[:first_n]
    rest_models = M_D[first_n:]

    if first_n >= 2:
        m1, m2 = first_batch[0], first_batch[1]
        logger.info(f"[PARALLEL_FIRST] tx={transaction_id} first_batch={[m1, m2]} rest={rest_models}")

        # Start BOTH tasks (parallel), but await MODEL-1 first (decision depends on it)
        t1 = asyncio.create_task(send_request(stub, m1, image_b64))
        t2 = asyncio.create_task(send_request(stub, m2, image_b64))

        r1 = None
        r2 = None
        pass1 = False
        pass2 = False

        # Await model-1
        try:
            r1 = await t1
            if r1.get("success", False):
                conf1 = float(r1.get("probability", 0.0))
                thr1 = _get_stage_threshold(0)
                pass1 = conf1 >= thr1
                logger.info(
                    f"[RUN_OK] tx={transaction_id} model={m1} label={r1.get('label')} conf={conf1:.4f} "
                    f"rpc_latency_s={float(r1.get('latency', -1)):.4f} container_state={r1.get('container_state')}"
                )
                logger.info(f"[THRESH] tx={transaction_id} model={m1} conf={conf1:.4f} threshold={thr1:.2f} pass={pass1}")
            else:
                logger.warning(f"[RUN_BAD] tx={transaction_id} model={m1} success=False")
        except Exception as e:
            logger.exception(f"[RUN_FAIL] tx={transaction_id} model={m1} error={e}")

        # RULE 1: If model-1 passes -> cancel model-2 and return model-1 ONLY
        if r1 is not None and r1.get("success", False) and pass1:
            # cancel the other process
            if not t2.done():
                t2.cancel()
                try:
                    await t2
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass

            results = [r1]
            stop_reason = f"early_exit_first_pass={m1}"
            logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")

        else:
            # Need model-2 result (because model-1 did not pass threshold)
            try:
                r2 = await t2
                if r2.get("success", False):
                    conf2 = float(r2.get("probability", 0.0))
                    thr2 = _get_stage_threshold(1)
                    pass2 = conf2 >= thr2
                    logger.info(
                        f"[RUN_OK] tx={transaction_id} model={m2} label={r2.get('label')} conf={conf2:.4f} "
                        f"rpc_latency_s={float(r2.get('latency', -1)):.4f} container_state={r2.get('container_state')}"
                    )
                    logger.info(f"[THRESH] tx={transaction_id} model={m2} conf={conf2:.4f} threshold={thr2:.2f} pass={pass2}")
                else:
                    logger.warning(f"[RUN_BAD] tx={transaction_id} model={m2} success=False")
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.exception(f"[RUN_FAIL] tx={transaction_id} model={m2} error={e}")

            # Keep successful outputs
            if r1 is not None and r1.get("success", False):
                results.append(r1)
            if r2 is not None and r2.get("success", False):
                results.append(r2)

            # RULE 2: If model-1 fails but model-2 passes -> EARLY EXIT with aggregation over both
            if (r1 is not None and r1.get("success", False) and (not pass1)) and (r2 is not None and r2.get("success", False) and pass2):
                stop_reason = f"early_exit_second_pass_aggregate=({m1},{m2})"
                logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
            # else: both fail -> continue sequentially (stop_reason remains ran_all)

    elif first_n == 1:
        # Only one model available
        m = first_batch[0]
        logger.info(f"[RUN] tx={transaction_id} step=1/{len(M_D)} model={m} start=True")
        try:
            r = await send_request(stub, m, image_b64)
            if r.get("success", False):
                conf = float(r.get("probability", 0.0))
                thr = _get_stage_threshold(0)
                passed = conf >= thr
                logger.info(
                    f"[RUN_OK] tx={transaction_id} model={m} label={r.get('label')} conf={conf:.4f} "
                    f"rpc_latency_s={float(r.get('latency', -1)):.4f} container_state={r.get('container_state')}"
                )
                logger.info(f"[THRESH] tx={transaction_id} model={m} conf={conf:.4f} threshold={thr:.2f} pass={passed}")
                results.append(r)
                if passed:
                    stop_reason = f"early_exit_first_pass={m}"
                    logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
            else:
                logger.warning(f"[RUN_BAD] tx={transaction_id} model={m} success=False")
        except Exception as e:
            logger.exception(f"[RUN_FAIL] tx={transaction_id} model={m} error={e}")

    # Continue sequentially only if we did NOT early exit (and we have remaining models)
    if stop_reason == "ran_all":
        for j, m in enumerate(rest_models):
            stage_index = first_n + j
            t0 = time.perf_counter()
            logger.info(f"[RUN] tx={transaction_id} step={first_n+j+1}/{len(M_D)} model={m} start=True")

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
            thr = _get_stage_threshold(stage_index)
            passed = conf >= thr

            logger.info(
                f"[RUN_OK] tx={transaction_id} model={m} label={res.get('label')} conf={conf:.4f} "
                f"rpc_latency_s={float(res.get('latency', -1)):.4f} wall_s={wall_s:.4f} "
                f"container_state={res.get('container_state')}"
            )
            logger.info(f"[THRESH] tx={transaction_id} model={m} conf={conf:.4f} threshold={thr:.2f} pass={passed}")

            results.append(res)

            if passed:
                stop_reason = f"early_exit_at_{m}"
                logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
                break

    # If no successful results
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
            "alpha_mode": ALPHA_MODE,
            "qps_est": qps_est,
            "stop_reason": stop_reason,
            "log_file": LOG_PATH,
        }

    # --- IMPORTANT FIX ---
    # If only ONE model executed, return it directly (no aggregation policy).
    if len(results) == 1:
        single = results[0]
        final_result = {
            "label": single.get("label"),
            "accuracy": float(single.get("probability", 0.0)),
            "combiner_policy": "single_model",
            "success": True,
        }
        logger.info(
            f"[SINGLE] tx={transaction_id} model={single.get('model')} "
            f"label={final_result['label']} conf={final_result['accuracy']:.4f}"
        )
    else:
        # Aggregation applies only when >=2 models were executed
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
        logger.info(
            f"[COMBINE] tx={transaction_id} executed_models={[r['model'] for r in results]} "
            f"combiner={final_result.get('combiner_policy')} final_label={final_result.get('label')} "
            f"final_acc={final_result.get('accuracy')}"
        )

    save_model_weights_atomic(WEIGHTS_STATE_PATH, MODEL_WEIGHTS)

    # Feedback updates (only for executed models)
    for res in results:
        try:
            OMEGA[res["model"]] = (1 - ETA) * OMEGA[res["model"]] + ETA * float(res.get("probability", 0.0))
            active_models.add(res["model"])
        except Exception:
            pass

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
        "threshold_stage": THRESHOLD_STAGE,
        "main_policy": POLICY,
        "alpha": alpha_now,
        "alpha_mode": ALPHA_MODE,
        "qps_est": qps_est,
        "stop_reason": stop_reason,
        "log_file": LOG_PATH,
        "parallel_first_n": first_n,
    }
