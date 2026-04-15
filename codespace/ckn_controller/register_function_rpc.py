# import grpc
# import iluvatar_rpc_pb2 as pb2
# import iluvatar_rpc_pb2_grpc as pb2_grpc
# import uuid
#
# channel = grpc.insecure_channel("149.165.175.242:8079")
# worker = pb2_grpc.IluvatarWorkerStub(channel)
# # print(pb2.RegisterRequest.DESCRIPTOR.fields_by_name.keys())
# # request = pb2.RegisterRequest(
# #     function_name="Baixi",
# #     function_version="1",
# #     image_name="docker.io/sunbaixi96/hello-iluvatar-action-http:latest",
# #     # image_name = "docker.io/alfuerst/hello-iluvatar-action:latest",
# #     memory=128,
# #     cpus=1,
# #     parallel_invokes=1,
# #     transaction_id="tx-001",
# #     language=pb2.LanguageRuntime.PYTHON3,
# #     compute=1,        # or appropriate platform ID
# #     isolate=1,
# #     container_server=0
# # )
#
# # request = pb2.RegisterRequest(
# #     function_name="mobilenet_v3_small",
# #     function_version="1",
# #     image_name="docker.io/sunbaixi96/ckn_faas_mobilenet_v3_small-iluvatar-action-http:latest",
# #     memory=512,
# #     cpus=1,
# #     parallel_invokes=1,
# #     transaction_id=str(uuid.uuid4()),
# #     language=pb2.LanguageRuntime.PYTHON3,
# #     compute=1,        # or appropriate platform ID
# #     isolate=1,
# #     container_server=0
# # )
# # model_name="resnet18"
#
# # request = pb2.RegisterRequest(
# #         function_name=model_name,
# #         function_version="1",
# #         image_name="docker.io/sunbaixi96/ckn_faas_{}-iluvatar-action-http:latest".format(model_name),
# #         memory=1024,
# #         cpus=1,
# #         parallel_invokes=1,
# #         transaction_id=str(uuid.uuid4()),
# #         language=pb2.LanguageRuntime.PYTHON3,
# #         compute=1,        # or appropriate platform ID
# #         isolate=1,
# #         container_server=0
# #     )
#
#
#
# model_list = ["mobilenet_v3_small","resnet18","resnet34","resnet50","resnet101","vit_b_16"]
# # model_list = ["shufflenet_v2_x0_5"]
#
# for model_name in model_list:
#     if model_name == "resnet101" or model_name == "vit_b_16":
#         request = pb2.RegisterRequest(
#             function_name=model_name,
#             function_version="1",
#             image_name="docker.io/iud2i/ckn_faas_{}-iluvatar-action-http:latest".format(model_name),
#             memory=1024,
#             cpus=2,
#             parallel_invokes=1,
#             transaction_id=str(uuid.uuid4()),
#             language=pb2.LanguageRuntime.PYTHON3,
#             compute=1,
#             isolate=1,
#             container_server=0
#         )
#     else:
#         request = pb2.RegisterRequest(
#             function_name=model_name,
#             function_version="1",
#             image_name="docker.io/iud2i/ckn_faas_{}-iluvatar-action-http:latest".format(model_name),
#             memory=512,
#             cpus=2,
#             parallel_invokes=1,
#             transaction_id=str(uuid.uuid4()),
#             language=pb2.LanguageRuntime.PYTHON3,
#             compute=1,
#             isolate=1,
#             container_server=0
#         )
#
#     response = worker.register(request)
#     print(response)



import uuid
import grpc

import iluvatar_rpc_pb2 as pb2
import iluvatar_rpc_pb2_grpc as pb2_grpc

from ckn_controller.ckn_config import (
    SERVER_ADDRESS,
    USE_TWO_ILUVATAR_INSTANCES,
    SMALL_MODEL_SERVER_ADDRESS,
    LARGE_MODEL_SERVER_ADDRESS,
)

model_list = [
    "mobilenet_v3_small",
    "resnet18",
    "resnet34",
    "resnet50",
    "resnet101",
    "vit_b_16",
]

SMALL_INSTANCE_MODELS = {"mobilenet_v3_small", "resnet18", "resnet34", "resnet50"}
LARGE_INSTANCE_MODELS = {"resnet101", "vit_b_16"}


def get_server_address_for_model(model_name: str) -> str:
    if not USE_TWO_ILUVATAR_INSTANCES:
        return SERVER_ADDRESS
    if model_name in SMALL_INSTANCE_MODELS:
        return SMALL_MODEL_SERVER_ADDRESS
    return LARGE_MODEL_SERVER_ADDRESS


def get_worker_map():
    addresses = {get_server_address_for_model(m) for m in model_list}
    worker_map = {}

    for addr in addresses:
        channel = grpc.insecure_channel(addr)
        worker_map[addr] = pb2_grpc.IluvatarWorkerStub(channel)

    return worker_map


def build_register_request(model_name: str) -> pb2.RegisterRequest:
    if model_name in {"resnet101", "vit_b_16"}:
        memory_mb = 1024
        cpus = 3
    else:
        memory_mb = 512
        cpus = 3

    return pb2.RegisterRequest(
        function_name=model_name,
        function_version="1",
        image_name=f"docker.io/plalelab/ckn_faas_{model_name}-iluvatar-action-http:latest",
        memory=memory_mb,
        cpus=cpus,
        parallel_invokes=1,
        transaction_id=str(uuid.uuid4()),
        language=pb2.LanguageRuntime.PYTHON3,
        compute=1,
        isolate=1,
        container_server=0,
    )


def main():
    worker_map = get_worker_map()

    for model_name in model_list:
        address = get_server_address_for_model(model_name)
        worker = worker_map[address]

        request = build_register_request(model_name)

        try:
            response = worker.register(request)
            print(f"[REGISTER_OK] model={model_name} server={address} response={response}")
        except grpc.RpcError as e:
            print(f"[REGISTER_FAIL] model={model_name} server={address} error={e.details()}")
        except Exception as e:
            print(f"[REGISTER_FAIL] model={model_name} server={address} error={e}")


if __name__ == "__main__":
    main()