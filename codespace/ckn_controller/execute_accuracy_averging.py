# import grpc
# import iluvatar_rpc_pb2 as pb2
# import iluvatar_rpc_pb2_grpc as pb2_grpc
# import json
# import os
# import uuid
# import base64
# import time
# from collections import defaultdict
# from concurrent.futures import ThreadPoolExecutor, as_completed
# from concurrent.futures import ProcessPoolExecutor, as_completed
#
# # Configuration
# image_dir = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/ckn_data/images/tem"
# # model_list = ["shufflenet_v2_x0_5", "mobilenet_v3_small", "googlenet",
# #               "resnext50_32x4d", "densenet201", "resnet152"]
#
# model_list = ["mobilenet_v3_small","resnet18","resnet34","resnet50","resnet101","vit_b_16"]
#
# # Output: {model_name: [prob1, prob2, ...]}
# probability_results = defaultdict(list)
# latency_results = defaultdict(list)
#
# # Connect to gRPC
# channel = grpc.insecure_channel("149.165.152.13:8079")
# worker = pb2_grpc.IluvatarWorkerStub(channel)
#
# def read_image_as_base64(path):
#     with open(path, "rb") as f:
#         return base64.b64encode(f.read()).decode("utf-8")
#
# def send_request(model_name, image_path):
#     try:
#         image_b64 = read_image_as_base64(image_path)
#         request = pb2.InvokeRequest(
#             function_name=model_name,
#             function_version="1",
#             json_args=json.dumps({"model_name": model_name, "image_data": image_b64}),
#             transaction_id=str(uuid.uuid4()),
#         )
#         start = time.perf_counter()
#         response = worker.invoke(request)
#         end = time.perf_counter()  # ✅ end timing
#
#         latency_ms = (end - start) * 1000  # milliseconds
#         result_json = json.loads(response.json_result)
#         prob = result_json["body"]["Probability"]
#         return (model_name, prob, image_path,latency_ms, None)
#     except Exception as e:
#         return (model_name, None, image_path,None, str(e))
#
# # Gather all image/model tasks
# tasks = []
# for filename in sorted(os.listdir(image_dir)):
#     if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
#         continue
#     image_path = os.path.join(image_dir, filename)
#     for model_name in model_list:
#         tasks.append((model_name, image_path))
#
# # Run in parallel
# start = time.perf_counter()
# # with ThreadPoolExecutor(max_workers=1) as executor:
# with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
#     futures = [executor.submit(send_request, m, i) for m, i in tasks]
#
#     for future in as_completed(futures):
#         model_name, prob, image_path, latency, error = future.result()
#         if error:
#             print(f"❌ {model_name} on {os.path.basename(image_path)}: {error}")
#         else:
#             probability_results[model_name].append(prob)
#             latency_results[model_name].append(latency)
#             print(f"✅ {model_name} on {os.path.basename(image_path)}: prob={prob:.4f}, latency={latency:.2f} ms")
#             print(f"✅ {model_name} on {os.path.basename(image_path)}: {prob:.4f}")
#
# end = time.perf_counter()
# print(f"\n⏱️ Total time: {(end - start):.2f} seconds")
#
# # === Summary Stats ===
# print("\n📊 Average Latency per Model:")
# for model, latencies in latency_results.items():
#     avg_latency = sum(latencies) / len(latencies)
#     print(f"{model:<20}: {avg_latency:.2f} ms")
#
# # output_path = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/results/model_latencies.json"
# output_path = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/ckn_data/results/model_latencies.json"
# with open("model_latencies.json", "w") as f:
#     json.dump(latency_results, f, indent=2)
#
# # Save results
# with open("model_probabilities.json", "w") as f:
#     json.dump(probability_results, f, indent=2)
# print(probability_results)
# print("✅ Results saved to model_probabilities.json")

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
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configuration
image_dir = "/Users/agamage/Desktop/D2I/Codes Original/clone main/ckn-faas/ckn_data/images/tem"
model_list = ["mobilenet_v3_small", "resnet18", "resnet34", "resnet50", "resnet101", "vit_b_16"]

channel = grpc.insecure_channel("149.165.174.241:8070")
worker = pb2_grpc.IluvatarWorkerStub(channel)

def read_image_as_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def send_request(model_name, image_path):
    try:
        # Re-initialize gRPC connection in each process

        image_b64 = read_image_as_base64(image_path)
        request = pb2.InvokeRequest(
            function_name=model_name,
            function_version="1",
            json_args=json.dumps({"model_name": model_name, "image_data": image_b64}),
            transaction_id=str(uuid.uuid4()),
        )

        start = time.perf_counter()
        response = worker.invoke(request)
        end = time.perf_counter()

        latency_ms = (end - start) * 1000
        result_json = json.loads(response.json_result)
        prob = result_json["body"]["Probability"]
        return (model_name, prob, image_path, latency_ms, None)
    except Exception as e:
        return (model_name, None, image_path, None, str(e))

def main():
    probability_results = defaultdict(list)
    latency_results = defaultdict(list)

    # Prepare tasks: (model_name, image_path) tuples
    tasks = []
    for filename in sorted(os.listdir(image_dir)):
        if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
            continue
        image_path = os.path.join(image_dir, filename)
        for model_name in model_list:
            tasks.append((model_name, image_path))

    start = time.perf_counter()

    # Run parallel inference using multiple cores
    with ThreadPoolExecutor(max_workers=1) as executor:
    # with ProcessPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(send_request, m, i) for m, i in tasks]
        for future in as_completed(futures):
            model_name, prob, image_path, latency, error = future.result()
            if error:
                print(f"❌ {model_name} on {os.path.basename(image_path)}: {error}")
            else:
                probability_results[model_name].append(prob)
                latency_results[model_name].append(latency)
                print(f"✅ {model_name} on {os.path.basename(image_path)}: prob={prob:.4f}, latency={latency:.2f} ms")

    end = time.perf_counter()
    print(f"\n⏱️ Total time: {(end - start):.2f} seconds")

    # === Summary Stats ===
    print("\n📊 Average Latency per Model:")
    for model, latencies in latency_results.items():
        avg_latency = sum(latencies) / len(latencies)
        print(f"{model:<20}: {avg_latency:.2f} ms")

    # Save results
    with open("model_latencies.json", "w") as f:
        json.dump(latency_results, f, indent=2)
    with open("model_probabilities.json", "w") as f:
        json.dump(probability_results, f, indent=2)
    print("✅ Results saved to model_probabilities.json")

# Required for multiprocessing on macOS/Windows
if __name__ == "__main__":
    multiprocessing.freeze_support()  # Optional on macOS; safe to include
    main()
