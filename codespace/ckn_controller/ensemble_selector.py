import itertools
from typing import Dict, List, Tuple

from ckn_controller.ckn_config import (
    M_TOTAL,
    POLICY,
    K,
    C,
    MODEL_PROFILES,
    MODEL_SIZES,
    SELECTION_STRATEGY,
    USE_DEADLINE_FAST_PATH,
)


# -----------------------------
# Basic helpers
# -----------------------------
def get_exit_probability(model_name: str) -> float:
    """
    Approximate early-exit probability using model accuracy.
    """
    try:
        p = float(MODEL_PROFILES[model_name].get("accuracy", 0.5))
    except Exception:
        p = 0.5
    return max(0.0, min(1.0, p))


def get_stage_time(model_name: str, wait_results: Dict[str, float]) -> float:
    wait_t = float(wait_results.get(model_name, float("inf")))
    compute_t = float(MODEL_PROFILES[model_name]["latency"])
    return wait_t + compute_t


def build_maxms(max_models: int) -> Dict[int, int]:
    sorted_by_size = sorted(M_TOTAL, key=lambda m: MODEL_SIZES[m], reverse=True)
    maxms: Dict[int, int] = {}
    rolling_sum = 0

    for i, m in enumerate(sorted_by_size):
        rolling_sum += MODEL_SIZES[m]
        size = i + 1
        if size <= max_models:
            maxms[size] = rolling_sum

    return maxms


def size_cost_for_models(ms: List[str], maxms: Dict[int, int]):
    size = len(ms)
    sum_bytes = sum(MODEL_SIZES[m] for m in ms)
    if sum_bytes <= 0 or size not in maxms:
        return None, sum_bytes
    sc = maxms[size] / sum_bytes
    return sc, sum_bytes


def generate_combinations(models: List[str], max_size: int):
    all_sets = []
    for k in range(1, max_size + 1):
        all_sets.extend(list(itertools.combinations(models, k)))
    return all_sets


def _fastest_model() -> str:
    return min(M_TOTAL, key=lambda m: float(MODEL_PROFILES[m]["latency"]))


# -----------------------------
# Sequential / E[T] helpers
# -----------------------------
def reorder_for_sequential(models: List[str], wait_results: Dict[str, float]) -> List[str]:
    """
    Rank by exit-probability-per-unit-time.
    """
    def rank(m: str):
        p_exit = get_exit_probability(m)
        t = max(get_stage_time(m, wait_results), 1e-9)
        return p_exit / t

    return sorted(models, key=rank, reverse=True)


def estimate_expected_latency_sequential(
    ordered_models: List[str],
    wait_results: Dict[str, float],
    network_latency: float,
) -> float:
    """
    E[T] = T(m1)
         + (1-P1) * (T(m2)+network_latency)
         + (1-P1)(1-P2) * (T(m3)+network_latency)
         + ...
    """
    if not ordered_models:
        return 0.0

    expected_time = 0.0
    prob_reach = 1.0

    for i, m in enumerate(ordered_models):
        stage_time = get_stage_time(m, wait_results)
        if stage_time == float("inf"):
            return float("inf")

        if i > 0:
            stage_time += float(network_latency)

        expected_time += prob_reach * stage_time
        prob_reach *= (1.0 - get_exit_probability(m))

    return expected_time


# -----------------------------
# Parallel-first-finish / E[T] helpers
# -----------------------------
def estimate_batch_exit_probability(batch_models: List[str]) -> float:
    """
    Approximate probability that the request stops after the first batch.

    Uses:
        P(stop after first batch) ≈ 1 - Π(1 - p_m)

    where p_m is the model-wise exit probability.
    """
    if not batch_models:
        return 0.0

    fail_prob = 1.0
    for m in batch_models:
        fail_prob *= (1.0 - get_exit_probability(m))

    return 1.0 - fail_prob


def estimate_first_batch_latency(
    batch_models: List[str],
    wait_results: Dict[str, float],
) -> float:
    """
    Approximate first-batch latency.

    Runtime idea:
    - launch first batch in parallel
    - if one model finishes first and passes threshold, stop early
    - otherwise wait for the rest of the first batch and aggregate

    Approximation:
      E[T_first_batch] =
          p_stop_after_first_batch * t_fast
        + (1 - p_stop_after_first_batch) * t_slow

    where:
      t_fast = fastest first-batch model time
      t_slow = slowest first-batch model time
      p_stop_after_first_batch ≈ 1 - Π(1 - p_m)
    """
    if not batch_models:
        return float("inf")

    vals = [get_stage_time(m, wait_results) for m in batch_models]
    if not vals or any(v == float("inf") for v in vals):
        return float("inf")

    t_fast = min(vals)
    t_slow = max(vals)

    p_stop_after_first_batch = estimate_batch_exit_probability(batch_models)

    return (
        p_stop_after_first_batch * t_fast
        + (1.0 - p_stop_after_first_batch) * t_slow
    )


def estimate_expected_latency_parallel_first_finish(
    ordered_models: List[str],
    wait_results: Dict[str, float],
    parallel_first_n: int,
    network_latency: float,
) -> float:
    """
    Approximation:
      E[T] = E[first_batch_time]
           + P(go_to_tail) * (network_latency + tail_expected_latency)

    where:
      P(stop after first batch) ≈ 1 - Π(1 - p_m)
      P(go_to_tail) = 1 - P(stop after first batch)
    """
    if not ordered_models:
        return float("inf")

    first_n = max(1, min(int(parallel_first_n), len(ordered_models)))

    # Reorder so better fast/likely-exit models are earlier
    ordered_models = reorder_for_sequential(ordered_models, wait_results)

    first_batch = ordered_models[:first_n]
    tail_models = ordered_models[first_n:]

    first_batch_latency = estimate_first_batch_latency(first_batch, wait_results)
    if first_batch_latency == float("inf"):
        return float("inf")

    p_stop_after_first_batch = estimate_batch_exit_probability(first_batch)
    p_go_to_tail = 1.0 - p_stop_after_first_batch

    if not tail_models:
        return first_batch_latency

    tail_models = reorder_for_sequential(tail_models, wait_results)
    tail_latency = estimate_expected_latency_sequential(
        ordered_models=tail_models,
        wait_results=wait_results,
        network_latency=network_latency,
    )

    if tail_latency == float("inf"):
        return float("inf")

    return first_batch_latency + p_go_to_tail * (float(network_latency) + tail_latency)


# -----------------------------
#  MODE-S selection
# -----------------------------
def build_model_set_mode_s(
    wait_results: Dict[str, float],
    deadline_ms: int,
    ensemble_size: int,
    alpha_now: float,
    logger=None,
) -> Tuple[List[str], Dict[str, float]]:
    """
    Original MODE-S greedy selection.
    """
    d_sec = deadline_ms / 1000.0
    if d_sec <= 0:
        return [], {}

    max_parallel_models = min(ensemble_size, K // C, len(M_TOTAL))
    if max_parallel_models <= 0:
        return [], {}

    maxms = build_maxms(max_parallel_models)

    def estimate_te(ms: List[str]) -> float:
        times = []
        for m in ms:
            wait_t = float(wait_results.get(m, float("inf")))
            compute_t = float(MODEL_PROFILES[m]["latency"])
            times.append(wait_t + compute_t)
        return max(times) if times else float("inf")

    def latency_term_for(ms: List[str]):
        te = estimate_te(ms)
        raw = te / d_sec
        if raw >= 1.0:
            return None, te, raw
        lt = min(max(raw, 0.1), 0.9)
        return lt, te, raw

    if POLICY.startswith("best_acc_"):
        k = int(POLICY.split("_")[-1])
        k = min(k, max_parallel_models, len(M_TOTAL))

        def get_acc(m: str) -> float:
            if m in MODEL_PROFILES and "accuracy" in MODEL_PROFILES[m]:
                return float(MODEL_PROFILES[m]["accuracy"])
            return float("-inf")

        sorted_by_acc = sorted(M_TOTAL, key=get_acc, reverse=True)
        selected = sorted_by_acc[:k]
        return selected, {m: wait_results.get(m, float("inf")) for m in selected}

    if POLICY == "randomized":
        import random
        k = max_parallel_models
        selected = random.sample(M_TOTAL, k)
        return selected, {m: wait_results.get(m, float("inf")) for m in selected}

    ms: List[str] = []
    remaining = list(M_TOTAL)

    for _ in range(max_parallel_models):
        best_candidate = None
        best_cost = float("inf")

        for m in remaining:
            trial = ms + [m]

            if len(trial) * C > K:
                continue

            lt, _, _ = latency_term_for(trial)
            if lt is None:
                continue

            sc, _ = size_cost_for_models(trial, maxms)
            if sc is None:
                continue

            cost = ((1.0 - alpha_now) * lt) + (alpha_now * sc)

            if cost < best_cost:
                best_cost = cost
                best_candidate = m

        if best_candidate is None:
            break

        ms.append(best_candidate)
        remaining.remove(best_candidate)

    if not ms:
        fastest = _fastest_model()
        ms = [fastest]

    return ms, {m: wait_results.get(m, float("inf")) for m in ms}


# -----------------------------
# Sequential selection - GREEDY
# -----------------------------
def build_model_set_sequential_greedy(
    wait_results: Dict[str, float],
    deadline_ms: int,
    ensemble_size: int,
    network_latency: float,
    logger=None,
) -> Tuple[List[str], Dict[str, float]]:
    d_sec = deadline_ms / 1000.0
    if d_sec <= 0:
        return [], {}

    max_models = min(ensemble_size, K // C, len(M_TOTAL))
    if max_models <= 0:
        return [], {}

    built_sets: List[Tuple[List[str], float]] = []

    best_single = None
    best_single_et = float("inf")

    for m in M_TOTAL:
        trial = [m]
        ordered = reorder_for_sequential(trial, wait_results)
        et = estimate_expected_latency_sequential(ordered, wait_results, network_latency)

        if et < best_single_et:
            best_single_et = et
            best_single = ordered

    if best_single is None:
        fastest = _fastest_model()
        return [fastest], {fastest: wait_results.get(fastest, float("inf"))}

    current_best = list(best_single)
    built_sets.append((list(current_best), best_single_et))

    remaining = [m for m in M_TOTAL if m not in current_best]

    while len(current_best) < max_models and remaining:
        best_trial = None
        best_trial_et = float("inf")

        for m in remaining:
            trial = current_best + [m]

            if len(trial) * C > K:
                continue

            ordered = reorder_for_sequential(trial, wait_results)
            et = estimate_expected_latency_sequential(ordered, wait_results, network_latency)

            if et < best_trial_et:
                best_trial_et = et
                best_trial = ordered

        if best_trial is None:
            break

        current_best = list(best_trial)
        built_sets.append((list(current_best), best_trial_et))
        remaining = [m for m in M_TOTAL if m not in current_best]

    if USE_DEADLINE_FAST_PATH:
        feasible_sets = [(ms, et) for ms, et in built_sets if et < d_sec]
        if feasible_sets:
            feasible_sets.sort(key=lambda x: (len(x[0]), -x[1]), reverse=True)
            chosen_ms, _ = feasible_sets[0]
            return chosen_ms, {m: wait_results.get(m, float("inf")) for m in chosen_ms}

        fastest = _fastest_model()
        return [fastest], {fastest: wait_results.get(fastest, float("inf"))}

    chosen_ms, _ = built_sets[-1]
    return chosen_ms, {m: wait_results.get(m, float("inf")) for m in chosen_ms}


# -----------------------------
# Sequential selection - EXHAUSTIVE
# -----------------------------
def build_model_set_sequential_exhaustive(
    wait_results: Dict[str, float],
    deadline_ms: int,
    ensemble_size: int,
    network_latency: float,
    logger=None,
) -> Tuple[List[str], Dict[str, float]]:
    d_sec = deadline_ms / 1000.0
    if d_sec <= 0:
        return [], {}

    max_models = min(ensemble_size, K // C, len(M_TOTAL))
    if max_models <= 0:
        return [], {}

    all_sets = generate_combinations(M_TOTAL, max_models)
    candidates: List[Tuple[List[str], float]] = []

    for subset in all_sets:
        subset = list(subset)

        if len(subset) * C > K:
            continue

        ordered = reorder_for_sequential(subset, wait_results)
        et = estimate_expected_latency_sequential(
            ordered_models=ordered,
            wait_results=wait_results,
            network_latency=network_latency,
        )
        candidates.append((ordered, et))

    if not candidates:
        fastest = _fastest_model()
        return [fastest], {fastest: wait_results.get(fastest, float("inf"))}

    if USE_DEADLINE_FAST_PATH:
        feasible = [(ms, et) for ms, et in candidates if et < d_sec]
        if feasible:
            feasible.sort(key=lambda x: (len(x[0]), -x[1]), reverse=True)
            chosen_ms, _ = feasible[0]
            return chosen_ms, {m: wait_results.get(m, float("inf")) for m in chosen_ms}

        fastest = _fastest_model()
        return [fastest], {fastest: wait_results.get(fastest, float("inf"))}

    exact_size_candidates = [(ms, et) for ms, et in candidates if len(ms) == max_models]
    if exact_size_candidates:
        chosen_ms, _ = min(exact_size_candidates, key=lambda x: x[1])
        return chosen_ms, {m: wait_results.get(m, float("inf")) for m in chosen_ms}

    fastest = _fastest_model()
    return [fastest], {fastest: wait_results.get(fastest, float("inf"))}


# -----------------------------
# Parallel-first-finish selection - GREEDY
# -----------------------------
def build_model_set_parallel_first_greedy(
    wait_results: Dict[str, float],
    deadline_ms: int,
    ensemble_size: int,
    parallel_first_n: int,
    network_latency: float,
    logger=None,
) -> Tuple[List[str], Dict[str, float]]:
    d_sec = deadline_ms / 1000.0
    if d_sec <= 0:
        return [], {}

    max_models = min(ensemble_size, K // C, len(M_TOTAL))
    if max_models <= 0:
        return [], {}

    built_sets: List[Tuple[List[str], float]] = []

    best_single = None
    best_single_et = float("inf")

    for m in M_TOTAL:
        trial = [m]
        ordered = reorder_for_sequential(trial, wait_results)
        et = estimate_expected_latency_parallel_first_finish(
            ordered, wait_results, parallel_first_n, network_latency
        )
        if et < best_single_et:
            best_single_et = et
            best_single = ordered

    if best_single is None:
        fastest = _fastest_model()
        return [fastest], {fastest: wait_results.get(fastest, float("inf"))}

    current_best = list(best_single)
    built_sets.append((list(current_best), best_single_et))

    remaining = [m for m in M_TOTAL if m not in current_best]

    while len(current_best) < max_models and remaining:
        best_trial = None
        best_trial_et = float("inf")

        for m in remaining:
            trial = current_best + [m]

            if len(trial) * C > K:
                continue

            ordered = reorder_for_sequential(trial, wait_results)

            et = estimate_expected_latency_parallel_first_finish(
                ordered, wait_results, parallel_first_n, network_latency
            )

            if et < best_trial_et:
                best_trial_et = et
                best_trial = ordered

        if best_trial is None:
            break

        current_best = list(best_trial)
        built_sets.append((list(current_best), best_trial_et))
        remaining = [m for m in M_TOTAL if m not in current_best]

    if USE_DEADLINE_FAST_PATH:
        feasible_sets = [(ms, et) for ms, et in built_sets if et < d_sec]
        if feasible_sets:
            feasible_sets.sort(key=lambda x: (len(x[0]), -x[1]), reverse=True)
            chosen_ms, _ = feasible_sets[0]
            return chosen_ms, {m: wait_results.get(m, float("inf")) for m in chosen_ms}

        fastest = _fastest_model()
        return [fastest], {fastest: wait_results.get(fastest, float("inf"))}

    chosen_ms, _ = built_sets[-1]
    return chosen_ms, {m: wait_results.get(m, float("inf")) for m in chosen_ms}


# -----------------------------
# Parallel-first-finish selection - EXHAUSTIVE
# -----------------------------
def build_model_set_parallel_first_exhaustive(
    wait_results: Dict[str, float],
    deadline_ms: int,
    ensemble_size: int,
    parallel_first_n: int,
    network_latency: float,
    logger=None,
) -> Tuple[List[str], Dict[str, float]]:
    d_sec = deadline_ms / 1000.0
    if d_sec <= 0:
        return [], {}

    max_models = min(ensemble_size, K // C, len(M_TOTAL))
    if max_models <= 0:
        return [], {}

    all_sets = generate_combinations(M_TOTAL, max_models)
    candidates: List[Tuple[List[str], float]] = []

    for subset in all_sets:
        subset = list(subset)

        if len(subset) * C > K:
            continue

        ordered = reorder_for_sequential(subset, wait_results)

        et = estimate_expected_latency_parallel_first_finish(
            ordered, wait_results, parallel_first_n, network_latency
        )
        candidates.append((ordered, et))

    if not candidates:
        fastest = _fastest_model()
        return [fastest], {fastest: wait_results.get(fastest, float("inf"))}

    if USE_DEADLINE_FAST_PATH:
        feasible = [(ms, et) for ms, et in candidates if et < d_sec]
        if feasible:
            feasible.sort(key=lambda x: (len(x[0]), -x[1]), reverse=True)
            chosen_ms, _ = feasible[0]
            return chosen_ms, {m: wait_results.get(m, float("inf")) for m in chosen_ms}

        fastest = _fastest_model()
        return [fastest], {fastest: wait_results.get(fastest, float("inf"))}

    exact_size_candidates = [(ms, et) for ms, et in candidates if len(ms) == max_models]
    if exact_size_candidates:
        chosen_ms, _ = min(exact_size_candidates, key=lambda x: x[1])
        return chosen_ms, {m: wait_results.get(m, float("inf")) for m in chosen_ms}

    fastest = _fastest_model()
    return [fastest], {fastest: wait_results.get(fastest, float("inf"))}


# -----------------------------
# Public latency estimator
# -----------------------------
def estimate_selected_set_latency_for_mode(
    cascade_mode: str,
    selected_models: List[str],
    wait_results: Dict[str, float],
    network_latency: float,
    parallel_first_n: int,
) -> float:
    mode = str(cascade_mode).lower()

    if mode in ("mode_s", "full_parallel"):
        vals = []
        for m in selected_models:
            wait_t = float(wait_results.get(m, float("inf")))
            compute_t = float(MODEL_PROFILES[m]["latency"])
            vals.append(wait_t + compute_t)
        return max(vals) if vals else float("inf")

    if mode == "sequential":
        return estimate_expected_latency_sequential(
            ordered_models=selected_models,
            wait_results=wait_results,
            network_latency=network_latency,
        )

    return estimate_expected_latency_parallel_first_finish(
        ordered_models=selected_models,
        wait_results=wait_results,
        parallel_first_n=parallel_first_n,
        network_latency=network_latency,
    )


# -----------------------------
# Dispatcher
# -----------------------------
def build_model_set_by_mode(
    cascade_mode: str,
    wait_results: Dict[str, float],
    deadline_ms: int,
    ensemble_size: int,
    alpha_now: float,
    parallel_first_n: int,
    network_latency: float,
    logger=None,
) -> Tuple[List[str], Dict[str, float]]:
    mode = str(cascade_mode).lower()
    strategy = str(SELECTION_STRATEGY).lower()

    if mode in ("mode_s", "full_parallel"):
        return build_model_set_mode_s(
            wait_results=wait_results,
            deadline_ms=deadline_ms,
            ensemble_size=ensemble_size,
            alpha_now=alpha_now,
            logger=logger,
        )

    if mode == "sequential":
        if strategy == "exhaustive":
            return build_model_set_sequential_exhaustive(
                wait_results=wait_results,
                deadline_ms=deadline_ms,
                ensemble_size=ensemble_size,
                network_latency=network_latency,
                logger=logger,
            )
        return build_model_set_sequential_greedy(
            wait_results=wait_results,
            deadline_ms=deadline_ms,
            ensemble_size=ensemble_size,
            network_latency=network_latency,
            logger=logger,
        )

    if strategy == "exhaustive":
        return build_model_set_parallel_first_exhaustive(
            wait_results=wait_results,
            deadline_ms=deadline_ms,
            ensemble_size=ensemble_size,
            parallel_first_n=parallel_first_n,
            network_latency=network_latency,
            logger=logger,
        )

    return build_model_set_parallel_first_greedy(
        wait_results=wait_results,
        deadline_ms=deadline_ms,
        ensemble_size=ensemble_size,
        parallel_first_n=parallel_first_n,
        network_latency=network_latency,
        logger=logger,
    )