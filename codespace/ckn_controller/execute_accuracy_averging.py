import grpc
import iluvatar_rpc_pb2 as pb2
import iluvatar_rpc_pb2_grpc as pb2_grpc
import json
import os
import uuid
import base64
import time
import multiprocessing
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from ckn_controller.ckn_config import (
    USE_TWO_ILUVATAR_INSTANCES,
    SERVER_ADDRESS,
    SMALL_MODEL_SERVER_ADDRESS,
    LARGE_MODEL_SERVER_ADDRESS,
    SMALL_INSTANCE_MODELS,
    LARGE_INSTANCE_MODELS,
)

# -----------------------------
# Configuration
# -----------------------------
image_dir = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/ckn_data/images/tem"
model_list = [
    "mobilenet_v3_small",
    "resnet18",
    "resnet34",
    "resnet50",
    "resnet101",
    "vit_b_16",
]

# -----------------------------
# Routing helpers
# -----------------------------
def get_server_address_for_model(model_name: str) -> str:
    if not USE_TWO_ILUVATAR_INSTANCES:
        return SERVER_ADDRESS

    if model_name in SMALL_INSTANCE_MODELS:
        return SMALL_MODEL_SERVER_ADDRESS

    if model_name in LARGE_INSTANCE_MODELS:
        return LARGE_MODEL_SERVER_ADDRESS

    raise ValueError(f"Model {model_name} is not assigned to any Iluvatar instance.")


# -----------------------------
# Shared worker cache
# -----------------------------
_worker_map = {}
_channel_map = {}
_worker_lock = Lock()


def get_worker_for_model(model_name: str):
    """
    Reuse one gRPC stub per server address.
    """
    address = get_server_address_for_model(model_name)

    with _worker_lock:
        if address not in _worker_map:
            channel = grpc.insecure_channel(address)
            worker = pb2_grpc.IluvatarWorkerStub(channel)
            _channel_map[address] = channel
            _worker_map[address] = worker

    return _worker_map[address], address


# -----------------------------
# Utilities
# -----------------------------
def read_image_as_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def send_request(model_name: str, image_path: str):
    try:
        worker, address = get_worker_for_model(model_name)

        image_b64 = read_image_as_base64(image_path)
        request = pb2.InvokeRequest(
            function_name=model_name,
            function_version="1",
            json_args=json.dumps({
                "model_name": model_name,
                "image_data": image_b64
            }),
            transaction_id=str(uuid.uuid4()),
        )

        start = time.perf_counter()
        response = worker.invoke(request)
        end = time.perf_counter()

        latency_ms = (end - start) * 1000.0
        result_json = json.loads(response.json_result)
        prob = float(result_json["body"]["Probability"])
        label = result_json["body"].get("Prediction Class", "UNKNOWN")

        return {
            "model_name": model_name,
            "image_path": image_path,
            "probability": prob,
            "label": label,
            "latency_ms": latency_ms,
            "server_address": address,
            "error": None,
        }

    except Exception as e:
        return {
            "model_name": model_name,
            "image_path": image_path,
            "probability": None,
            "label": None,
            "latency_ms": None,
            "server_address": None,
            "error": str(e),
        }


def main():
    probability_results = defaultdict(list)
    latency_results = defaultdict(list)
    route_results = defaultdict(list)

    tasks = []
    for filename in sorted(os.listdir(image_dir)):
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue

        image_path = os.path.join(image_dir, filename)
        for model_name in model_list:
            tasks.append((model_name, image_path))

    print("=== Routing Summary ===")
    for model_name in model_list:
        addr = get_server_address_for_model(model_name)
        print(f"{model_name:<20} -> {addr}")

    start = time.perf_counter()

    # Adjust max_workers as needed
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = [executor.submit(send_request, m, i) for m, i in tasks]

        for future in as_completed(futures):
            result = future.result()

            model_name = result["model_name"]
            image_path = result["image_path"]
            prob = result["probability"]
            label = result["label"]
            latency = result["latency_ms"]
            address = result["server_address"]
            error = result["error"]

            if error:
                print(f"❌ {model_name} on {os.path.basename(image_path)}: {error}")
            else:
                probability_results[model_name].append(prob)
                latency_results[model_name].append(latency)
                route_results[model_name].append(address)

                print(
                    f"✅ {model_name} on {os.path.basename(image_path)}: "
                    f"label={label}, prob={prob:.4f}, latency={latency:.2f} ms, server={address}"
                )

    end = time.perf_counter()
    print(f"\n⏱️ Total time: {(end - start):.2f} seconds")

    print("\n📊 Average Latency per Model:")
    for model, latencies in latency_results.items():
        avg_latency = sum(latencies) / len(latencies)
        print(f"{model:<20}: {avg_latency:.2f} ms")

    print("\n📍 Route per Model:")
    for model, addresses in route_results.items():
        unique_addresses = sorted(set(addresses))
        print(f"{model:<20}: {unique_addresses}")

    with open("model_latencies.json", "w") as f:
        json.dump(latency_results, f, indent=2)

    with open("model_probabilities.json", "w") as f:
        json.dump(probability_results, f, indent=2)

    with open("model_routes.json", "w") as f:
        json.dump(route_results, f, indent=2)

    print("✅ Results saved to model_latencies.json, model_probabilities.json, model_routes.json")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()


