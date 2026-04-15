
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

    ENSEMBLE_SIZE,
    THRESHOLD,
    THRESHOLD_STAGE,

    ALPHA_MODE,
    ALPHA_STATIC,
    ALPHA_MIN,
    ALPHA_MAX,

    QPS_WINDOW_SEC,
    QPS_LOW,
    QPS_HIGH,

    CASCADE_MODE,
    PARALLEL_FIRST_N,
    PARALLEL_BATCH_SIZE,
    NETWORK_LATENCY,
    USE_DEADLINE_FAST_PATH,

    # Manual multi-instance routing
    USE_TWO_ILUVATAR_INSTANCES,
    SMALL_MODEL_SERVER_ADDRESS,
    LARGE_MODEL_SERVER_ADDRESS,
    SMALL_INSTANCE_MODELS,
    LARGE_INSTANCE_MODELS,
)

import wait_time_iluvatar
from ckn_controller.output_combiner import combine_outputs
from ckn_controller.weights_io import load_model_weights, save_model_weights_atomic
from ckn_controller.label_utils import wnid_matches_text_label
from ckn_controller.ensemble_selector import (
    build_model_set_by_mode,
    estimate_selected_set_latency_for_mode,
)


# -----------------------------
# Logging setup
# -----------------------------
LOG_DIR = os.environ.get("MODE_S_LOG_DIR", "./logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, "mode_s_cascade.log")

logger = logging.getLogger("cascade")
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
# QPS tracking
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
# Adaptive alpha
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
    alpha_now = max(alpha_min, min(alpha_max, alpha_now))

    logger.info(
        f"[ALPHA_DEBUG] qps={qps:.4f} qps_norm={qps_norm:.4f} alpha={alpha_now:.6f}"
    )
    return alpha_now


# -----------------------------
# Deadline helper
# -----------------------------
def should_stop_before_next_model(
    start_time: float,
    deadline_ms: int,
    next_model: str,
    safety_margin_ms: float = 0.0,
) -> Tuple[bool, float, float]:
    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    remaining_ms = float(deadline_ms) - elapsed_ms
    next_latency_ms = float(MODEL_PROFILES[next_model]["latency"]) * 1000.0
    stop_now = remaining_ms <= (next_latency_ms + safety_margin_ms)
    return stop_now, elapsed_ms, remaining_ms


# -----------------------------
# Manual routing helpers
# -----------------------------
def get_server_address_for_model(model_name: str) -> str:
    if not USE_TWO_ILUVATAR_INSTANCES:
        return SERVER_ADDRESS

    if model_name in SMALL_INSTANCE_MODELS:
        return SMALL_MODEL_SERVER_ADDRESS

    if model_name in LARGE_INSTANCE_MODELS:
        return LARGE_MODEL_SERVER_ADDRESS

    raise ValueError(f"Model {model_name} is not assigned to any Iluvatar instance.")


def build_stub_map_for_selected_models(model_list: List[str]):
    addresses = {get_server_address_for_model(m) for m in model_list}
    channel_map = {}
    stub_map = {}

    for addr in addresses:
        channel = grpc.aio.insecure_channel(addr)
        stub = pb2_grpc.IluvatarWorkerStub(channel)
        channel_map[addr] = channel
        stub_map[addr] = stub

    return channel_map, stub_map


async def close_channels(channel_map):
    for channel in channel_map.values():
        try:
            await channel.close()
        except Exception:
            pass


def get_stub_for_model(model_name: str, stub_map):
    addr = get_server_address_for_model(model_name)
    return stub_map[addr]


def get_wait_results_for_models(model_list: List[str]) -> Dict[str, float]:
    """
    Query wait times from the correct instance(s) using manual routing.
    Requires wait_time_iluvatar.main(server_address=..., model_list=...)
    """
    if not USE_TWO_ILUVATAR_INSTANCES:
        return wait_time_iluvatar.main(
            server_address=SERVER_ADDRESS,
            model_list=model_list,
        )

    small_models = [m for m in model_list if m in SMALL_INSTANCE_MODELS]
    large_models = [m for m in model_list if m in LARGE_INSTANCE_MODELS]

    merged = {}

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

    return merged


# -----------------------------
# Iluvatar invocation
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
        "server_address": get_server_address_for_model(model_name),
    }


def _get_stage_threshold(stage_index: int) -> float:
    try:
        if isinstance(THRESHOLD_STAGE, list) and len(THRESHOLD_STAGE) > stage_index:
            return float(THRESHOLD_STAGE[stage_index])
    except Exception:
        pass
    return float(THRESHOLD)


# -----------------------------
# Sequential cascade execution
# -----------------------------
async def execute_sequential_cascade(
    stub_map,
    transaction_id: str,
    model_list: List[str],
    image_b64: str,
    start_time: float,
    deadline_ms: int,
) -> Tuple[List[dict], str]:
    results: List[dict] = []
    stop_reason = "ran_all"

    for i, m in enumerate(model_list):
        t0 = time.perf_counter()
        logger.info(f"[RUN] tx={transaction_id} step={i+1}/{len(model_list)} model={m} start=True")

        stub = get_stub_for_model(m, stub_map)

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
        stage_thr = _get_stage_threshold(i)
        passed = conf >= stage_thr

        logger.info(
            f"[RUN_OK] tx={transaction_id} model={m} label={label} conf={conf:.4f} "
            f"rpc_latency_s={float(res.get('latency', -1)):.4f} wall_s={wall_s:.4f} "
            f"container_state={res.get('container_state')} server={res.get('server_address')}"
        )
        logger.info(
            f"[THRESH] tx={transaction_id} model={m} conf={conf:.4f} "
            f"threshold={stage_thr:.2f} pass={passed}"
        )

        results.append(res)

        if i == 0 and passed:
            stop_reason = f"early_exit_first_pass={m}"
            logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
            break

        if i > 0 and passed:
            stop_reason = f"early_exit_with_aggregation_at_{m}"
            logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
            break

        if i + 1 < len(model_list):
            next_model = model_list[i + 1]
            stop_now, elapsed_ms, remaining_ms = should_stop_before_next_model(
                start_time=start_time,
                deadline_ms=deadline_ms,
                next_model=next_model,
            )

            logger.info(
                f"[DEADLINE_CHECK] tx={transaction_id} after_model={m} next_model={next_model} "
                f"elapsed_ms={elapsed_ms:.2f} remaining_ms={remaining_ms:.2f} "
                f"next_est_ms={float(MODEL_PROFILES[next_model]['latency']) * 1000.0:.2f} "
                f"stop={stop_now}"
            )

            if stop_now:
                stop_reason = f"deadline_stop_before_{next_model}"
                logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
                break

    return results, stop_reason


# -----------------------------
# MODE-S execution
# -----------------------------
async def execute_mode_s_cascade(
    stub_map,
    transaction_id: str,
    model_list: List[str],
    image_b64: str,
) -> Tuple[List[dict], str]:
    logger.info(f"[MODE_S_START] tx={transaction_id} models={model_list}")

    tasks = []
    task_models = []

    for m in model_list:
        stub = get_stub_for_model(m, stub_map)
        tasks.append(asyncio.create_task(send_request(stub, m, image_b64)))
        task_models.append(m)

    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    results: List[dict] = []
    for idx, out in enumerate(raw_results):
        m = task_models[idx]

        if isinstance(out, Exception):
            logger.exception(f"[RUN_FAIL] tx={transaction_id} model={m} error={out}")
            continue

        res = out
        if not res.get("success", False):
            logger.warning(f"[RUN_BAD] tx={transaction_id} model={m} success=False")
            continue

        logger.info(
            f"[RUN_OK] tx={transaction_id} model={m} "
            f"label={res.get('label')} conf={float(res.get('probability', 0.0)):.4f} "
            f"rpc_latency_s={float(res.get('latency', -1)):.4f} "
            f"container_state={res.get('container_state')} server={res.get('server_address')}"
        )
        results.append(res)

    return results, "mode_s_executed"



# -----------------------------
# Parallel-first-finish cascade
# -----------------------------
async def execute_parallel_first_finish_cascade(
    stub_map,
    transaction_id: str,
    model_list: List[str],
    image_b64: str,
    parallel_first_n: int,
    parallel_batch_size: int,
    start_time: float,
    deadline_ms: int,
    selected_folder: str,
) -> Tuple[List[dict], str]:
    results: List[dict] = []
    stop_reason = "ran_all"

    first_n = max(0, min(int(parallel_first_n), len(model_list)))
    batch_size = max(1, int(parallel_batch_size))

    first_batch = model_list[:first_n]
    rest_models = model_list[first_n:]

    if first_n >= 2:
        logger.info(
            f"[PARALLEL_FIRST_FINISH] tx={transaction_id} "
            f"first_batch={first_batch} rest={rest_models}"
        )

        task_map = {
            asyncio.create_task(send_request(get_stub_for_model(m, stub_map), m, image_b64)): m
            for m in first_batch
        }

        done, pending = await asyncio.wait(
            set(task_map.keys()),
            return_when=asyncio.FIRST_COMPLETED,
        )

        first_task = next(iter(done))
        first_model = task_map[first_task]

        first_result = None
        first_pass = False

        try:
            first_result = first_task.result()

            if first_result.get("success", False):
                first_conf = float(first_result.get("probability", 0.0))
                first_thr = _get_stage_threshold(0)
                first_pass = first_conf >= first_thr

                logger.info(
                    f"[RUN_OK] tx={transaction_id} first_finished_model={first_model} "
                    f"label={first_result.get('label')} conf={first_conf:.4f} "
                    f"rpc_latency_s={float(first_result.get('latency', -1)):.4f} "
                    f"container_state={first_result.get('container_state')} "
                    f"server={first_result.get('server_address')}"
                )
                logger.info(
                    f"[THRESH] tx={transaction_id} first_finished_model={first_model} "
                    f"conf={first_conf:.4f} threshold={first_thr:.2f} pass={first_pass}"
                )
            else:
                logger.warning(
                    f"[RUN_BAD] tx={transaction_id} first_finished_model={first_model} success=False"
                )

        except asyncio.CancelledError:
            logger.warning(
                f"[RUN_CANCELLED] tx={transaction_id} first_finished_model={first_model}"
            )
            first_result = None

        except Exception as e:
            logger.exception(
                f"[RUN_FAIL] tx={transaction_id} first_finished_model={first_model} error={e}"
            )
            first_result = None

        # Early exit if first finished model already passes threshold
        if first_result is not None and first_result.get("success", False) and first_pass:
            for p in pending:
                p.cancel()

            for p in pending:
                try:
                    await p
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.exception(
                        f"[CANCEL_WAIT_FAIL] tx={transaction_id} "
                        f"model={task_map.get(p, 'unknown')} error={e}"
                    )

            results = [first_result]
            stop_reason = f"early_exit_first_finished_pass={first_model}"
            logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
            return results, stop_reason

        # Otherwise, wait for remaining first-batch tasks and aggregate
        remaining_results: List[dict] = []

        for p in pending:
            model_name = task_map[p]
            try:
                res = await p
                if res.get("success", False):
                    remaining_results.append(res)

                    logger.info(
                        f"[RUN_OK] tx={transaction_id} model={model_name} "
                        f"label={res.get('label')} conf={float(res.get('probability', 0.0)):.4f} "
                        f"rpc_latency_s={float(res.get('latency', -1)):.4f} "
                        f"container_state={res.get('container_state')} "
                        f"server={res.get('server_address')}"
                    )
                else:
                    logger.warning(
                        f"[RUN_BAD] tx={transaction_id} model={model_name} success=False"
                    )
            except asyncio.CancelledError:
                logger.warning(
                    f"[RUN_CANCELLED] tx={transaction_id} model={model_name}"
                )
            except Exception as e:
                logger.exception(
                    f"[RUN_FAIL] tx={transaction_id} model={model_name} error={e}"
                )

        if first_result is not None and first_result.get("success", False):
            results.append(first_result)

        results.extend(remaining_results)

        if len(results) >= 2:
            temp_final = combine_outputs(
                results,
                policy="weighted_majority",
                historical_acc=OMEGA,
                model_weights=MODEL_WEIGHTS,
                ground_truth=selected_folder,
                gamma=GAMMA,
                update_weights=False,
                label_matcher=wnid_matches_text_label,
                rho=RHO,
            )

            agg_conf = float(temp_final.get("accuracy", 0.0))
            agg_thr = _get_stage_threshold(1)
            agg_pass = agg_conf >= agg_thr

            logger.info(
                f"[AGG_CHECK] tx={transaction_id} models={[r['model'] for r in results]} "
                f"agg_label={temp_final.get('label')} agg_conf={agg_conf:.4f} "
                f"threshold={agg_thr:.2f} pass={agg_pass}"
            )

            if agg_pass:
                stop_reason = (
                    f"early_exit_aggregate_pass_after_first_batch="
                    f"{[r['model'] for r in results]}"
                )
                logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
                return results, stop_reason

    elif first_n == 1:
        m = first_batch[0]
        try:
            stub = get_stub_for_model(m, stub_map)
            r = await send_request(stub, m, image_b64)

            if r.get("success", False):
                conf = float(r.get("probability", 0.0))
                thr = _get_stage_threshold(0)
                passed = conf >= thr
                results.append(r)

                logger.info(
                    f"[RUN_OK] tx={transaction_id} model={m} "
                    f"label={r.get('label')} conf={conf:.4f} "
                    f"rpc_latency_s={float(r.get('latency', -1)):.4f} "
                    f"container_state={r.get('container_state')} "
                    f"server={r.get('server_address')}"
                )
                logger.info(
                    f"[THRESH] tx={transaction_id} model={m} "
                    f"conf={conf:.4f} threshold={thr:.2f} pass={passed}"
                )

                if passed:
                    stop_reason = f"early_exit_first_pass={m}"
                    logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
                    return results, stop_reason
            else:
                logger.warning(f"[RUN_BAD] tx={transaction_id} model={m} success=False")

        except asyncio.CancelledError:
            logger.warning(f"[RUN_CANCELLED] tx={transaction_id} model={m}")
        except Exception as e:
            logger.exception(f"[RUN_FAIL] tx={transaction_id} model={m} error={e}")

    start_idx = first_n

    for batch_start in range(0, len(rest_models), batch_size):
        batch = rest_models[batch_start: batch_start + batch_size]

        first_next_model = batch[0]
        stop_now, elapsed_ms, remaining_ms = should_stop_before_next_model(
            start_time=start_time,
            deadline_ms=deadline_ms,
            next_model=first_next_model,
        )

        logger.info(
            f"[DEADLINE_CHECK] tx={transaction_id} next_batch={batch} "
            f"elapsed_ms={elapsed_ms:.2f} remaining_ms={remaining_ms:.2f} "
            f"first_next_est_ms={float(MODEL_PROFILES[first_next_model]['latency']) * 1000.0:.2f} "
            f"stop={stop_now}"
        )

        if stop_now:
            stop_reason = f"deadline_stop_before_{first_next_model}"
            logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
            break

        logger.info(f"[PARALLEL_BATCH] tx={transaction_id} batch={batch}")

        tasks = [
            asyncio.create_task(send_request(get_stub_for_model(m, stub_map), m, image_b64))
            for m in batch
        ]

        batch_raw = await asyncio.gather(*tasks, return_exceptions=True)

        successful_in_batch = False

        for local_idx, out in enumerate(batch_raw):
            m = batch[local_idx]
            stage_index = start_idx + batch_start + local_idx

            if isinstance(out, asyncio.CancelledError):
                logger.warning(f"[RUN_CANCELLED] tx={transaction_id} model={m}")
                continue

            if isinstance(out, Exception):
                logger.exception(f"[RUN_FAIL] tx={transaction_id} model={m} error={out}")
                continue

            res = out
            if not res.get("success", False):
                logger.warning(f"[RUN_BAD] tx={transaction_id} model={m} success=False")
                continue

            conf = float(res.get("probability", 0.0))
            thr = _get_stage_threshold(stage_index)
            passed = conf >= thr

            logger.info(
                f"[RUN_OK] tx={transaction_id} model={m} label={res.get('label')} conf={conf:.4f} "
                f"rpc_latency_s={float(res.get('latency', -1)):.4f} "
                f"container_state={res.get('container_state')} server={res.get('server_address')}"
            )
            logger.info(
                f"[THRESH] tx={transaction_id} model={m} conf={conf:.4f} "
                f"threshold={thr:.2f} pass={passed}"
            )

            results.append(res)
            successful_in_batch = True

        if successful_in_batch and len(results) >= 2:
            last_stage_idx = start_idx + batch_start + len(batch) - 1
            agg_thr = _get_stage_threshold(last_stage_idx)

            temp_final = combine_outputs(
                results,
                policy="weighted_majority",
                historical_acc=OMEGA,
                model_weights=MODEL_WEIGHTS,
                ground_truth=selected_folder,
                gamma=GAMMA,
                update_weights=False,
                label_matcher=wnid_matches_text_label,
                rho=RHO,
            )

            agg_conf = float(temp_final.get("accuracy", 0.0))
            agg_pass = agg_conf >= agg_thr

            logger.info(
                f"[AGG_CHECK] tx={transaction_id} models={[r['model'] for r in results]} "
                f"agg_label={temp_final.get('label')} agg_conf={agg_conf:.4f} "
                f"threshold={agg_thr:.2f} pass={agg_pass}"
            )

            if agg_pass:
                stop_reason = f"early_exit_aggregate_pass_after_batch={batch}"
                logger.info(f"[EARLY_EXIT] tx={transaction_id} stop_reason={stop_reason}")
                break

    return results, stop_reason


# -----------------------------
# Main invoke
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

    now = time.perf_counter()
    record_request(now, QPS_WINDOW_SEC)
    qps_est = get_qps(QPS_WINDOW_SEC)

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
        f"ensemble_size={ENSEMBLE_SIZE} selected_folder={selected_folder} "
        f"cascade_mode={CASCADE_MODE} parallel_first_n={PARALLEL_FIRST_N} "
        f"parallel_batch_size={PARALLEL_BATCH_SIZE} "
        f"use_two_instances={USE_TWO_ILUVATAR_INSTANCES}"
    )

    wait_results = get_wait_results_for_models(M_TOTAL)

    all_wait_vals = [float(v) for v in wait_results.values() if v is not None and v != float("inf")]
    if all_wait_vals:
        logger.info(
            f"[WAIT_SUMMARY] tx={transaction_id} mean_wait={sum(all_wait_vals)/len(all_wait_vals):.4f}s "
            f"max_wait={max(all_wait_vals):.4f}s min_wait={min(all_wait_vals):.4f}s"
        )
    else:
        logger.info(f"[WAIT_SUMMARY] tx={transaction_id} no_wait_data=True")

    M_D, total_estimates = build_model_set_by_mode(
        cascade_mode=CASCADE_MODE,
        wait_results=wait_results,
        deadline_ms=deadline,
        ensemble_size=ENSEMBLE_SIZE,
        alpha_now=alpha_now,
        parallel_first_n=PARALLEL_FIRST_N,
        network_latency=NETWORK_LATENCY,
        logger=logger,
    )

    if not M_D:
        fastest_model = min(MODEL_PROFILES, key=lambda m: float(MODEL_PROFILES[m]["latency"]))
        M_D = [fastest_model]
        total_estimates = {fastest_model: wait_results.get(fastest_model, float("inf"))}
        logger.warning(f"[SELECT_EMPTY] tx={transaction_id} fallback_fastest={fastest_model}")

    selected_est_latency = estimate_selected_set_latency_for_mode(
        cascade_mode=CASCADE_MODE,
        selected_models=M_D,
        wait_results=wait_results,
        network_latency=NETWORK_LATENCY,
        parallel_first_n=PARALLEL_FIRST_N,
    )

    deadline_sec = float(deadline) / 1000.0 if deadline is not None else 0.0
    deadline_fast_path_triggered = False

    if (
        USE_DEADLINE_FAST_PATH
        and deadline_sec > 0.0
        and selected_est_latency >= deadline_sec
    ):
        fastest_model = min(MODEL_PROFILES, key=lambda m: float(MODEL_PROFILES[m]["latency"]))
        logger.warning(
            f"[DEADLINE_FAST_PATH] tx={transaction_id} "
            f"mode={CASCADE_MODE} selected_models={M_D} "
            f"selected_est_latency={selected_est_latency:.4f}s "
            f"deadline={deadline_sec:.4f}s "
            f"fallback_fastest={fastest_model}"
        )
        M_D = [fastest_model]
        total_estimates = {fastest_model: wait_results.get(fastest_model, float('inf'))}
        selected_est_latency = estimate_selected_set_latency_for_mode(
            cascade_mode=CASCADE_MODE,
            selected_models=M_D,
            wait_results=wait_results,
            network_latency=NETWORK_LATENCY,
            parallel_first_n=PARALLEL_FIRST_N,
        )
        deadline_fast_path_triggered = True

    logger.info(f"[SELECT] tx={transaction_id} selected_models={M_D}")
    logger.info(
        f"[SELECT_WAITS] tx={transaction_id} waits_selected="
        f"{ {m: float(total_estimates.get(m, -1)) for m in M_D} }"
    )
    logger.info(
        f"[SELECT_ROUTE] tx={transaction_id} routes="
        f"{ {m: get_server_address_for_model(m) for m in M_D} }"
    )

    channel_map, stub_map = build_stub_map_for_selected_models(M_D)

    try:
        mode = str(CASCADE_MODE).lower()

        if mode == "sequential":
            results, stop_reason = await execute_sequential_cascade(
                stub_map=stub_map,
                transaction_id=transaction_id,
                model_list=M_D,
                image_b64=image_b64,
                start_time=start_time,
                deadline_ms=deadline,
            )
        elif mode in ("mode_s", "full_parallel"):
            results, stop_reason = await execute_mode_s_cascade(
                stub_map=stub_map,
                transaction_id=transaction_id,
                model_list=M_D,
                image_b64=image_b64,
            )
        else:
            results, stop_reason = await execute_parallel_first_finish_cascade(
                stub_map=stub_map,
                transaction_id=transaction_id,
                model_list=M_D,
                image_b64=image_b64,
                parallel_first_n=PARALLEL_FIRST_N,
                parallel_batch_size=PARALLEL_BATCH_SIZE,
                start_time=start_time,
                deadline_ms=deadline,
                selected_folder=selected_folder,
            )
    finally:
        await close_channels(channel_map)

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
            "threshold_stage": THRESHOLD_STAGE,
            "main_policy": POLICY,
            "alpha": alpha_now,
            "alpha_mode": ALPHA_MODE,
            "qps_est": qps_est,
            "stop_reason": stop_reason,
            "log_file": LOG_PATH,
            "cascade_mode": CASCADE_MODE,
            "parallel_first_n": PARALLEL_FIRST_N,
            "parallel_batch_size": PARALLEL_BATCH_SIZE,
            "use_two_instances": USE_TWO_ILUVATAR_INSTANCES,
            "deadline_fast_path_enabled": USE_DEADLINE_FAST_PATH,
            "deadline_fast_path_triggered": deadline_fast_path_triggered,
            "selected_est_latency_s": selected_est_latency,
        }

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
            "server_address": res.get("server_address"),
        }

    end_time = time.perf_counter()
    e2e_ms = (end_time - start_time) * 1000

    logger.info(
        f"[REQ_END] tx={transaction_id} success={final_result.get('success', True)} "
        f"stop_reason={stop_reason} e2e_ms={e2e_ms:.2f} alpha={alpha_now:.3f} "
        f"cascade_mode={CASCADE_MODE}"
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
        "cascade_mode": CASCADE_MODE,
        "parallel_first_n": PARALLEL_FIRST_N,
        "parallel_batch_size": PARALLEL_BATCH_SIZE,
        "use_two_instances": USE_TWO_ILUVATAR_INSTANCES,
        "deadline_fast_path_enabled": USE_DEADLINE_FAST_PATH,
        "deadline_fast_path_triggered": deadline_fast_path_triggered,
        "selected_est_latency_s": selected_est_latency,
    }


###########
#new model selection f  code end
#####