# wait_time_client.py
import asyncio
import uuid

import grpc
import json
import sys
from datetime import datetime

import ckn_controller.iluvatar_rpc_pb2 as pb2
import ckn_controller.iluvatar_rpc_pb2_grpc as pb2_grpc


M_total = ["mobilenet_v3_small", "resnet18", "resnet34", "resnet50", "resnet101", "vit_b_16"]

def get_estimated_wait(stub, model_name):
    fqdn = f"{model_name}-1"
    request = pb2.EstInvokeRequest(transaction_id=str(uuid.uuid4()), fqdns=[fqdn])
    try:
        response = stub.est_invoke_time(request)
        return response.est_time[0] if response.est_time else float('inf')
    except grpc.RpcError as e:
        print(f"[{datetime.now()}] Failed to estimate for {model_name}: {e.details()}")
        return float('inf')

def main():
    channel = grpc.insecure_channel("149.165.175.242:8079")
    stub = pb2_grpc.IluvatarWorkerStub(channel)

    wait_results = {}
    for model in M_total:
        wait_time = get_estimated_wait(stub, model)
        wait_results[model] = wait_time

    print(json.dumps(wait_results, indent=2))

    return wait_results

if __name__ == "__main__":
    main()
