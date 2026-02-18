import grpc
import iluvatar_rpc_pb2 as pb2
import iluvatar_rpc_pb2_grpc as pb2_grpc
import ckn_controller.iluvatar_rpc_pb2 as pb2
import ckn_controller.iluvatar_rpc_pb2_grpc as pb2_grpc
import json
import uuid
import base64
import time
import random
import asyncio
from datetime import datetime
from ckn_controller.ckn_config  import SERVER_ADDRESS, M_TOTAL, POLICY, K, C, ALPHA, ETA,MODEL_PROFILES,COLD_PENALTY, OMEGA, MAX_MODEL_SIZE, DEFAULT_WEIGHTS, GAMMA, RHO, WEIGHTS_STATE_PATH, MODEL_SIZES
import wait_time_iluvatar
from ckn_controller.output_combiner import combine_outputs
from ckn_controller.weights_io import load_model_weights, save_model_weights_atomic, diff_weights
import logging
import os
import itertools
from ckn_controller.label_utils import wnid_matches_text_label

MODEL_WEIGHTS = load_model_weights(WEIGHTS_STATE_PATH, DEFAULT_WEIGHTS)
active_models = set()

A = []

import time

def read_image_as_bytes(path):
    with open(path, "rb") as f:
        return f.read()

async def send_request(stub, model_name, image_b64):
    request = pb2.InvokeRequest(
        function_name=model_name,
        function_version="1",
        json_args=json.dumps({"model_name": model_name, "image_data": image_b64}),
        transaction_id=str(uuid.uuid4()),
    )
    try:
        response = await stub.invoke(request)
        result_json = json.loads(response.json_result)
        print("result_json........", result_json)
        return {
            "model": model_name,
            "label": result_json["body"]["Prediction Class"],
            "probability": float(result_json["body"]["Probability"]),
            "latency": response.duration_us / 1e6,
            "success": response.success,
            "container_state": pb2.ContainerState.Name(response.container_state),
        }
    except Exception as e:
        logging.error(f"send_request failed for model {model_name}: {e}")
        raise

# def build_model_set(wait_results: dict, deadline_ms: int):
#     """
#     Select a model-set MS using  cost function:
#
#         C_r = (T_e / D) + ALPHA * (MaxMS[size] / sum_bytes_MS)
#
#     where:
#       - T_e = estimated service time (sec) for executing x on all models in MS
#       - D   = deadline (sec)
#       - MaxMS[size] = sum of 'size' largest model sizes (max possible accuracy proxy)
#       - sum_bytes_MS = sum of model sizes in the selected set MS
#     """
#     D_sec = deadline_ms / 1000.0
#     print("MODEL_PROFILES:......", MAX_MODEL_SIZE)
#
#     # Max number of models we can run in parallel
#     max_parallel_models = min(MAX_MODEL_SIZE, K // C, len(M_TOTAL))
#
#     print("max_parallel_models:......", max_parallel_models)
#
#
#     sorted_by_size = sorted(M_TOTAL, key=lambda m: MODEL_SIZES[m], reverse=True)
#     MaxMS = {}
#     rolling_sum = 0
#     for i, m in enumerate(sorted_by_size):
#         rolling_sum += MODEL_SIZES[m]
#         size = i + 1
#         if size <= max_parallel_models:
#             MaxMS[size] = rolling_sum
#
#     def estimate_Te(MS):
#         """
#         Estimate service time T_e(MS): wait + compute for each model, then max
#         (since they run logically in parallel).
#         """
#         times = []
#         for m in MS:
#             wait_t = wait_results.get(m, float("inf"))
#             compute_t = MODEL_PROFILES[m]["latency"]
#             times.append(wait_t + compute_t)
#         return max(times) if times else float("inf")
#
#     best_MS = None
#     best_cost = float("inf")
#     best_waits = {}
#
#     if POLICY == "greedy":
#         # Consider all sizes 1..max_parallel_models (no hard preference order).
#         for size in range(1, max_parallel_models + 1):
#             for MS in itertools.combinations(M_TOTAL, size):
#                 MS = list(MS)
#
#                 if size * C > K:
#                     continue
#
#                 T_e = estimate_Te(MS)
#                 raw = T_e / D_sec
#
#                 if raw >= 1.0:
#                     continue
#
#                 latency_term = min(max(raw, 0.1), 0.9)
#
#                 sum_bytes_MS = sum(MODEL_SIZES[m] for m in MS)
#                 if sum_bytes_MS <= 0:
#                     continue
#
#                 max_bytes_for_size = MaxMS[size]
#
#                 accuracy_term = ALPHA * (max_bytes_for_size / sum_bytes_MS)
#                 cost = latency_term + accuracy_term
#
#                 if cost < best_cost:
#                     best_cost = cost
#                     best_MS = MS
#                     best_waits = {
#                         m: wait_results.get(m, float("inf")) for m in MS
#                     }
#
#         # If no ensemble of any size satisfies T_e / D < 1, pick single fastest model
#         if best_MS is None:
#             fastest = min(M_TOTAL, key=lambda m: MODEL_PROFILES[m]["latency"])
#             best_MS = [fastest]
#             best_waits = {fastest: wait_results.get(fastest, float("inf"))}
#
#         M_D = best_MS
#         total_estimates = best_waits
#
#     elif POLICY == "randomized":
#         import random
#         sample_size = min(MAX_MODEL_SIZE, len(M_TOTAL))
#         M_D = random.sample(M_TOTAL, sample_size)
#         total_estimates = {m: wait_results.get(m, float("inf")) for m in M_D}
#         best_cost = float("nan")  # not computed in randomized
#
#     else:
#         M_D = []
#         total_estimates = {}
#         best_cost = float("nan")
#
#     print(
#         f"[build_model_set] Selected: {M_D}, policy={POLICY}, "
#         f"cost={best_cost if POLICY == 'greedy' else 'N/A'}"
#     )
#     return M_D, total_estimates

#!/usr/bin/env python3
"""
Greedy model-set selection (MODE-S style) with FULL step-by-step debug prints.

- Builds the model set incrementally up to max_parallel_models.
- At each step, tries adding each remaining model and computes:
    latency_term = clamp(Te/D, 0.1, 0.9)  (must be < 1 else infeasible)
    accuracy_term = ALPHA * (MaxMS[size] / sum_bytes_MS)
    cost = latency_term + accuracy_term
- Picks the candidate with minimum cost, appends it, repeats.
- Tracks the best set seen so far (in case cost gets worse later).
- Falls back to fastest single model if nothing feasible.

Drop this into your code and replace your current build_model_set.
"""

import itertools
import math

def build_model_set(wait_results: dict, deadline_ms: int):
    """
    Greedy selection using:
        C_r = latency_term + accuracy_term
        latency_term = clamp( (Te(MS)/D), 0.1, 0.9 ), only if Te(MS)/D < 1
        accuracy_term = ALPHA * (MaxMS[size] / sum_bytes_MS)

    where:
      - Te(MS) = max over models in MS of (wait(m) + compute(m))  [parallel completion]
      - D = deadline in seconds
      - MaxMS[size] = sum of the largest `size` model sizes in bytes (proxy max accuracy for that size)
      - sum_bytes_MS = sum of bytes of models in MS
    """
    D_sec = deadline_ms / 1000.0
    print("\n==============================")
    print("[build_model_set] START")
    print(f"Deadline: {deadline_ms} ms  ({D_sec:.3f} s)")
    print(f"POLICY: {POLICY}")
    print(f"MAX_MODEL_SIZE: {MAX_MODEL_SIZE}")
    print("==============================")

    # Max number of models we can run in parallel
    max_parallel_models = min(MAX_MODEL_SIZE, K // C, len(M_TOTAL))
    print(f"[INFO] max_parallel_models = min({MAX_MODEL_SIZE}, {K}//{C}, {len(M_TOTAL)}) = {max_parallel_models}")

    # Precompute MaxMS[size] using model sizes (largest-first)
    sorted_by_size = sorted(M_TOTAL, key=lambda m: MODEL_SIZES[m], reverse=True)
    MaxMS = {}
    rolling_sum = 0
    for i, m in enumerate(sorted_by_size):
        rolling_sum += MODEL_SIZES[m]
        size = i + 1
        if size <= max_parallel_models:
            MaxMS[size] = rolling_sum

    print("\n[INFO] MaxMS (max possible bytes for each set size):")
    for s in range(1, max_parallel_models + 1):
        print(f"  MaxMS[{s}] = {MaxMS.get(s)}")

    def estimate_Te(MS):
        """
        Te(MS) = max(wait+compute) across models in MS (parallel completion time).
        """
        times = []
        for m in MS:
            wait_t = float(wait_results.get(m, float("inf")))
            compute_t = float(MODEL_PROFILES[m]["latency"])
            times.append(wait_t + compute_t)
        return max(times) if times else float("inf")

    def latency_term_for(MS):
        """
        latency_term = clamp(Te/D, 0.1, 0.9), only if Te/D < 1
        """
        T_e = estimate_Te(MS)
        raw = T_e / D_sec
        if raw >= 1.0:
            return None, T_e, raw  # infeasible
        lt = min(max(raw, 0.1), 0.9)
        return lt, T_e, raw

    def accuracy_term_for(MS):
        """
        accuracy_term = ALPHA * (MaxMS[size] / sum_bytes_MS)
        """
        size = len(MS)
        sum_bytes_MS = sum(MODEL_SIZES[m] for m in MS)
        if sum_bytes_MS <= 0:
            return None, sum_bytes_MS
        at = ALPHA * (MaxMS[size] / sum_bytes_MS)
        return at, sum_bytes_MS

    # -----------------------------
    # POLICY SWITCH
    # -----------------------------
    if POLICY == "randomized":
        import random
        sample_size = min(MAX_MODEL_SIZE, len(M_TOTAL))
        M_D = random.sample(M_TOTAL, sample_size)
        total_estimates = {m: wait_results.get(m, float("inf")) for m in M_D}
        print(f"[build_model_set] RANDOMIZED selected: {M_D}")
        return M_D, total_estimates

    def get_acc(m: str) -> float:
        # Option A: accuracy stored in MODEL_PROFILES
        if m in MODEL_PROFILES and "accuracy" in MODEL_PROFILES[m]:
            return float(MODEL_PROFILES[m]["accuracy"])
        # Fallback if missing (pushes it to the end)
        return float("-inf")
    def select_topk_by_accuracy(k: int):
        k = min(k, len(M_TOTAL))
        # Sort models by accuracy (high -> low)
        sorted_by_acc = sorted(M_TOTAL, key=get_acc, reverse=True)
        M_D = sorted_by_acc[:k]

        total_estimates = {m: wait_results.get(m, float("inf")) for m in M_D}
        print(f"[build_model_set] TOP-{k}-ACC selected: {M_D} "
              f"acc={[get_acc(m) for m in M_D]}")
        return M_D, total_estimates

    if POLICY == "best_acc_1":
        return select_topk_by_accuracy(1)

    if POLICY == "best_acc_2":
        return select_topk_by_accuracy(2)

    if POLICY == "best_acc_3":
        return select_topk_by_accuracy(3)

    if POLICY != "greedy":
        print(f"[WARN] Unknown POLICY='{POLICY}', returning empty.")
        return [], {}


    # -----------------------------
    # GREEDY CONSTRUCTION
    # -----------------------------
    MS = []
    remaining = list(M_TOTAL)

    best_cost = float("inf")
    best_MS = None

    print("\n[GREEDY] Begin incremental construction...\n")

    # Try building up to max_parallel_models
    for step in range(1, max_parallel_models + 1):
        best_candidate = None
        best_candidate_cost = float("inf")
        best_candidate_dbg = None

        print(f"--- STEP {step}: current MS={MS} ---")

        for m in remaining:
            trial = MS + [m]

            # Resource constraint (cores)
            if len(trial) * C > K:
                print(f"  SKIP {m:>18} | trial={trial} | reason: cores {len(trial)*C} > K {K}")
                continue

            lt, T_e, raw = latency_term_for(trial)
            if lt is None:
                print(f"  SKIP {m:>18} | trial={trial} | Te={T_e:.3f}s raw={raw:.3f} >= 1 (miss deadline)")
                continue

            at, sum_bytes_MS = accuracy_term_for(trial)
            if at is None:
                print(f"  SKIP {m:>18} | trial={trial} | reason: sum_bytes_MS invalid ({sum_bytes_MS})")
                continue

            cost = lt + at

            print(
                f"  TRY  {m:>18} | trial={trial} | "
                f"wait+compute max Te={T_e:.3f}s | raw=Te/D={raw:.3f} | lt={lt:.3f} | "
                f"sumB={sum_bytes_MS} | MaxMS[{len(trial)}]={MaxMS[len(trial)]} | at={at:.3f} | "
                f"cost={cost:.3f}"
            )

            if cost < best_candidate_cost:
                best_candidate_cost = cost
                best_candidate = m
                best_candidate_dbg = (T_e, raw, lt, sum_bytes_MS, at, cost)

        # If no feasible addition, stop.
        if best_candidate is None:
            print(f"\n[GREEDY] STOP at step {step}: no feasible model can be added.\n")
            break

        # Accept the best addition
        MS.append(best_candidate)
        remaining.remove(best_candidate)

        T_e, raw, lt, sumB, at, cost = best_candidate_dbg
        print(
            f"\n[GREEDY] CHOOSE {best_candidate}  => MS={MS}\n"
            f"        Te={T_e:.3f}s raw={raw:.3f} lt={lt:.3f} sumB={sumB} at={at:.3f} cost={cost:.3f}\n"
        )

        # Track best set seen so far
        # if best_candidate_cost < best_cost:
        #     best_cost = best_candidate_cost
        #     best_MS = list(MS)
        EPS = 0.02  # small tolerance
        if best_candidate_cost < best_cost - EPS:
            best_cost = best_candidate_cost
            best_MS = list(MS)
        elif abs(best_candidate_cost - best_cost) <= EPS:
            # tie-ish -> prefer larger set
            best_cost = best_candidate_cost
            best_MS = list(MS)

            print(f"[GREEDY] BEST so far updated => best_MS={best_MS} best_cost={best_cost:.3f}\n")

    # Fallback: fastest model if nothing feasible at all
    if best_MS is None:
        fastest = min(M_TOTAL, key=lambda m: MODEL_PROFILES[m]["latency"])
        best_MS = [fastest]
        best_cost = float("nan")
        print(f"[GREEDY] No feasible set found. FALLBACK to fastest model: {fastest}")

    best_waits = {m: wait_results.get(m, float("inf")) for m in best_MS}

    print("=====================================")
    print(f"[build_model_set] FINAL selected MS={best_MS}")
    print(f"[build_model_set] FINAL cost={best_cost if not math.isnan(best_cost) else 'N/A'}")
    print("[build_model_set] Wait estimates (selected):")
    for m in best_MS:
        print(f"  - {m}: wait={best_waits[m]}")
    print("=====================================\n")

    return best_MS, best_waits


async def main_ensemble_invoke(
    transaction_id: str,
    deadline: int,
    image_b64: str,
    selected_folder: str | None = None
) -> dict:


    start_time = time.perf_counter()

    #  Step 0: image comes from client
    if not image_b64:
        raise ValueError("image_b64 is required")

    if selected_folder is None:
        selected_folder = "unknown"


    # Step 1: gRPC connection
    async_channel = grpc.aio.insecure_channel(SERVER_ADDRESS)
    stub = pb2_grpc.IluvatarWorkerStub(async_channel)

    # Step 2: Get wait time estimates
    # wait_tasks = {m: asyncio.create_task(get_estimated_wait_async(stub, m)) for m in M_total}
    # wait_results = {m: await t for m, t in wait_tasks.items()}
    wait_results = wait_time_iluvatar.main()

    M_D, total_estimates = build_model_set(wait_results, deadline)
    skip_status = None

    print(f"[Request {transaction_id}] Selected Models: {M_D}")

    if not M_D:
        # Pick the fastest model by latency
        fastest_model = min(MODEL_PROFILES, key=lambda m: MODEL_PROFILES[m]["latency"])
        M_D = [fastest_model]
        skip_status = "Skipped"
        print(f"[Request {transaction_id}] No valid models found — using fastest model: {fastest_model}")

    # Step 4: Send requests
    send_req_start_time_sec = time.perf_counter()
    results = []
    for m in M_D:
        try:
            res = await send_request(stub, m, image_b64)
            results.append(res)
        except Exception as e:
            logging.warning(f"[Request {transaction_id}] Model {m} failed: {e}")
            # append a placeholder result indicating failure
            results.append({
                "model": m,
                "label": -1,
                "probability": 0.0,
                "latency": -1,
                "success": False,
                "container_state": "UNKNOWN"
            })
    # tasks = [asyncio.create_task(send_request(stub, m, image_b64)) for m in M_D]
    # results = await asyncio.gather(*tasks)

    results = [res for res in results if res.get("success", False)]
    if not results:
        print(f"[Request {transaction_id}] No successful model responses.")
        return {  "selected_models": -1, "label": -1, "accuracy": 0.0, "combiner_policy": "FAILED", "e2e_time_ms": -1, "success": False, "wait_times": total_estimates}

    prev_snapshot = dict(MODEL_WEIGHTS)

    # Step 5: Choose best result
    # best = max(results, key=lambda x: x["accuracy"])
    final_result = combine_outputs(
        results,
        policy="weighted_majority",
        historical_acc=OMEGA,
        model_weights=MODEL_WEIGHTS,
        ground_truth=selected_folder,
        gamma=GAMMA,
        update_weights=True,
        label_matcher=wnid_matches_text_label,
        rho=RHO
    )

    save_model_weights_atomic(WEIGHTS_STATE_PATH, MODEL_WEIGHTS)

    # Step 6: Feedback updates
    for res in results:
        OMEGA[res["model"]] = (1 - ETA) * OMEGA[res["model"]] + ETA * res["probability"]
        active_models.add(res["model"])

    # Print all model responses
    per_model = {}
    for res in results:
        model = res.get("model")
        prob = float(res.get("probability", 0.0))
        label = res.get("label")
        lat = float(res.get("latency", -1))
        state = res.get("container_state", "UNKNOWN")
        succ = bool(res.get("success", False))

        print(f"Model: {model} | Accuracy: {prob:.4f} | label: {label} | Latency: {lat:.3f}s | State: {state}")

        per_model[model] = {
            "label": label,
            "probability": prob,
            "latency_s": lat,
            "success": succ,
            "state": state,
        }

    print("--------------------------------------------------------------------------")
    print(f"Final Result {final_result}")
    print("--------------------------------------------------------------------------")

    end_time = time.perf_counter()
    print(f"Request {transaction_id} total time: {(end_time - start_time) * 1000:.2f} ms\n")

    return {
        "selected_models": M_D,
        "label": final_result["label"],
        "accuracy": final_result["accuracy"],
        "combiner_policy": final_result["combiner_policy"],
        "e2e_time_ms": (end_time - start_time) * 1000,
        "success": skip_status or final_result["success"],
        "selected_folder": selected_folder,
        "wait_times": total_estimates,
        "per_model": per_model,
        "model_Size":MAX_MODEL_SIZE,
        "main_policy": POLICY,
        "alpha":ALPHA

    }



# if __name__ == "__main__":
#     asyncio.run(QoED_test())