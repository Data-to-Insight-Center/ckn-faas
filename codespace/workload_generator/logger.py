# import csv
# import os
# from rich.console import Console
# from rich.table import Table
#
# console = Console()
#
# LOG_HEADER = ["ID", "Deadline", "IAR", "RespTime", "Model", "Accuracy", "Latency", "State", "Success"]
#
#
# def log_result(req_id, deadline, iar, response_time, response):
#     os.makedirs("data", exist_ok=True)
#     log_path = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/iar_results.csv"
#     write_header = not os.path.exists(log_path)
#     with open(log_path, "a", newline="") as f:
#         writer = csv.writer(f)
#         if write_header:
#             writer.writerow(LOG_HEADER)
#         writer.writerow([
#             req_id, deadline, iar, response_time,
#             response.get("model"), response.get("accuracy"),
#             response.get("latency"), response.get("container_state"),
#             response.get("success")
#         ])
#
#     # Rich real-time dashboard logging
#     table = Table(show_header=True, header_style="bold magenta")
#     for col in LOG_HEADER:
#         table.add_column(col)
#     table.add_row(
#         str(req_id), str(deadline), str(iar), f"{response_time:.3f}",
#         str(response.get("model")),
#         f"{response.get('accuracy', 0.0):.4f}",
#         f"{response.get('latency', -1):.3f}",
#         str(response.get("container_state")),
#         str(response.get("success"))
#     )
#     console.print(table)



##2 start

# import csv
# import os
# from rich.console import Console
# from rich.table import Table
#
# console = Console()
#
# # Add per-model wait columns to the header
# LOG_HEADER = [
#     "ID", "Deadline", "IAR", "RespTime","RunTime", "selected_models","label", "Accuracy", "combiner_policy", "e2e_time_ms", "Success", "selected_folder",
#     "random_image", "mobilenet_v3_small_wait", "resnet18_wait", "resnet34_wait",
#     "resnet50_wait", "resnet101_wait", "vit_b_16_wait"
# ]
#
# def log_result(mode, req_id, deadline, iar, response_time,current_time_sec, response):
#     os.makedirs("data", exist_ok=True)
#     if mode == "vary_deadline":
#         log_path = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/deadline_results_M31_I5_D1.csv"
#     else:
#         log_path = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/iar_results_3.csv"
#
#     write_header = not os.path.exists(log_path)
#
#     # Extract wait times from response (dict of model: wait_time)
#     waits = response.get("wait_times", {})
#
#     with open(log_path, "a", newline="") as f:
#         writer = csv.writer(f)
#         if write_header:
#             writer.writerow(LOG_HEADER)
#         writer.writerow([
#             req_id, deadline, iar, response_time,current_time_sec,
#             response.get("selected_models", []), response.get("label",-1),
#             response.get("accuracy"), response.get("combiner_policy"),
#             response.get("e2e_time_ms"), response.get("success"),
#             response.get("selected_folder"),
#             waits.get("mobilenet_v3_small", -1),
#             waits.get("resnet18", -1),
#             waits.get("resnet34", -1),
#             waits.get("resnet50", -1),
#             waits.get("resnet101", -1),
#             waits.get("vit_b_16", -1)
#         ])
#
#     # Rich real-time terminal output
#     table = Table(show_header=True, header_style="bold magenta")
#
#     for col in LOG_HEADER:
#         table.add_column(col)
#
#     table.add_row(
#         str(req_id), str(deadline), str(iar), f"{response_time:.3f}", f"{current_time_sec:.3f}",
#         str(response.get("selected_models", [])),
#         str(response.get("label",-1)),
#         f"{response.get('accuracy', 0.0):.4f}",
#         f"{response.get('latency', -1):.3f}",
#         str(response.get("combiner_policy",-1)),
#         str(response.get("e2e_time_ms",-1)),
#         str(response.get("success")),
#         str(response.get("selected_folder")),
#         f"{waits.get('mobilenet_v3_small', -1):.2f}",
#         f"{waits.get('resnet18', -1):.2f}",
#         f"{waits.get('resnet34', -1):.2f}",
#         f"{waits.get('resnet50', -1):.2f}",
#         f"{waits.get('resnet101', -1):.2f}",
#         f"{waits.get('vit_b_16', -1):.2f}"
#     )
#
#     console.print(table)


    ### 2 end


import csv
import os
from rich.console import Console
from rich.table import Table

console = Console()

# Fixed set of models you use (order matters for CSV and table)
MODEL_LIST = [
    "mobilenet_v3_small",
    "resnet18",
    "resnet34",
    "resnet50",
    "resnet101",
    "vit_b_16",
]

# Build per-model columns for label, probability, wait
PER_MODEL_LABEL_COLS = [f"{m}_label" for m in MODEL_LIST]
PER_MODEL_PROB_COLS  = [f"{m}_prob"  for m in MODEL_LIST]
PER_MODEL_WAIT_COLS  = [f"{m}_wait"  for m in MODEL_LIST]

LOG_HEADER = [
    "ID", "Deadline", "IAR", "RespTime", "RunTime",
    "selected_models", "label", "Accuracy", "combiner_policy",
    "e2e_time_ms", "Success", "selected_folder",
    "ModelSize",
    # per-model labels
    *PER_MODEL_LABEL_COLS,
    # per-model probabilities
    *PER_MODEL_PROB_COLS,
    # per-model wait times
    *PER_MODEL_WAIT_COLS,

    "main_policy", "alpha"
]

def _get_per_model_fields(response):
    """
    Returns:
      labels:  list[str] aligned with MODEL_LIST
      probs:   list[float] aligned with MODEL_LIST
    """
    per_model = response.get("per_model", {}) or {}
    labels = []
    probs  = []
    for m in MODEL_LIST:
        info = per_model.get(m, {}) or {}
        labels.append(str(info.get("label", "")))
        p = info.get("probability", None)
        try:
            probs.append(float(p) if p is not None else -1.0)
        except Exception:
            probs.append(-1.0)
    return labels, probs

def _get_per_model_waits(response):
    waits = response.get("wait_times", {}) or {}
    vals = []
    for m in MODEL_LIST:
        w = waits.get(m, None)
        try:
            vals.append(float(w) if w is not None else -1.0)
        except Exception:
            vals.append(-1.0)
    return vals

def _get_model_size(response):
    """
    Accept multiple possible keys for safety:
      - 'model_Size' (your example)
      - 'MAX_MODEL_SIZE' (common alt)
      - 'model_size' (lowercase)
    Returns a number if available, else -1.
    """
    for k in ("model_Size", "MAX_MODEL_SIZE", "model_size"):
        if k in response:
            try:
                return float(response[k])
            except Exception:
                return response[k]  # if it’s a string like "LARGE"
    return -1

def log_result(mode, req_id, deadline, iar, response_time, current_time_sec, response):
    os.makedirs("data", exist_ok=True)
    if mode == "vary_deadline":
        log_path = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/accuracy_confidence_logs_2_3_S.csv"
    else:
        log_path = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/codespace/workload_generator/data/accuracy_confidence_logs_2_3_S.csv"

    write_header = not os.path.exists(log_path)

    # Pull fields from response
    selected_models = response.get("selected_models", [])
    label           = response.get("label", -1)
    accuracy        = response.get("accuracy", None)
    combiner        = response.get("combiner_policy", "")
    e2e_ms          = response.get("e2e_time_ms", -1)
    success         = response.get("success", False)
    selected_folder = response.get("selected_folder", "")
    model_size      = _get_model_size(response)
    main_policy        = response.get("main_policy", "")
    alpha   = response.get("alpha", "")

    # Per-model fields
    model_labels, model_probs = _get_per_model_fields(response)
    model_waits = _get_per_model_waits(response)

    # ---- CSV write ----
    with open(log_path, "a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(LOG_HEADER)

        row = [
            req_id, deadline, iar, response_time, current_time_sec,
            selected_models, label, accuracy, combiner,
            e2e_ms, success, selected_folder,
            model_size,  # <--- NEW FIELD
            *model_labels,
            *model_probs,
            *model_waits,
            main_policy,
            alpha
        ]
        writer.writerow(row)

    # ---- Rich table (one row per request) ----
    table = Table(show_header=True, header_style="bold magenta")
    for col in LOG_HEADER:
        table.add_column(col)

    # pretty strings
    sm_str  = str(selected_models)
    acc_str = f"{accuracy:.4f}" if isinstance(accuracy, (int, float)) and accuracy >= 0 else str(accuracy)
    e2e_str = f"{e2e_ms:.2f}" if isinstance(e2e_ms, (int, float)) else str(e2e_ms)
    rt_str  = f"{response_time:.3f}"
    ct_str  = f"{current_time_sec:.3f}"
    ms_str  = f"{model_size:.2f}" if isinstance(model_size, (int, float)) else str(model_size)

    model_probs_str = [f"{p:.4f}" if isinstance(p, (int, float)) and p >= 0 else str(p) for p in model_probs]
    model_waits_str = [f"{w:.2f}"  if isinstance(w, (int, float)) and w >= 0 else str(w) for w in model_waits]

    table.add_row(
        str(req_id), str(deadline), str(iar), rt_str, ct_str,
        sm_str, str(label), acc_str, str(combiner),
        e2e_str, str(success), str(selected_folder),
        ms_str,  # <--- NEW FIELD
        *[str(x) for x in model_labels],
        *model_probs_str,
        *model_waits_str,
        str(main_policy),
        str(alpha),
    )

    # console.print(table)

