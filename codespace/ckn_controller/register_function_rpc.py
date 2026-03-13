import grpc
import iluvatar_rpc_pb2 as pb2
import iluvatar_rpc_pb2_grpc as pb2_grpc
import uuid

channel = grpc.insecure_channel("149.165.174.241:8070")
worker = pb2_grpc.IluvatarWorkerStub(channel)
# print(pb2.RegisterRequest.DESCRIPTOR.fields_by_name.keys())
# request = pb2.RegisterRequest(
#     function_name="Baixi",
#     function_version="1",
#     image_name="docker.io/sunbaixi96/hello-iluvatar-action-http:latest",
#     # image_name = "docker.io/alfuerst/hello-iluvatar-action:latest",
#     memory=128,
#     cpus=1,
#     parallel_invokes=1,
#     transaction_id="tx-001",
#     language=pb2.LanguageRuntime.PYTHON3,
#     compute=1,        # or appropriate platform ID
#     isolate=1,
#     container_server=0
# )

# request = pb2.RegisterRequest(
#     function_name="mobilenet_v3_small",
#     function_version="1",
#     image_name="docker.io/sunbaixi96/ckn_faas_mobilenet_v3_small-iluvatar-action-http:latest",
#     memory=512,
#     cpus=1,
#     parallel_invokes=1,
#     transaction_id=str(uuid.uuid4()),
#     language=pb2.LanguageRuntime.PYTHON3,
#     compute=1,        # or appropriate platform ID
#     isolate=1,
#     container_server=0
# )
# model_name="resnet18"

# request = pb2.RegisterRequest(
#         function_name=model_name,
#         function_version="1",
#         image_name="docker.io/sunbaixi96/ckn_faas_{}-iluvatar-action-http:latest".format(model_name),
#         memory=1024,
#         cpus=1,
#         parallel_invokes=1,
#         transaction_id=str(uuid.uuid4()),
#         language=pb2.LanguageRuntime.PYTHON3,
#         compute=1,        # or appropriate platform ID
#         isolate=1,
#         container_server=0
#     )



model_list = ["mobilenet_v3_small","resnet18","resnet34","resnet50","resnet101","vit_b_16"]
# model_list = ["shufflenet_v2_x0_5"]

for model_name in model_list:
    if model_name == "resnet101" or model_name == "vit_b_16":
        request = pb2.RegisterRequest(
            function_name=model_name,
            function_version="1",
            image_name="docker.io/iud2i/ckn_faas_{}-iluvatar-action-http:latest".format(model_name),
            memory=1024,
            cpus=1,
            parallel_invokes=1,
            transaction_id=str(uuid.uuid4()),
            language=pb2.LanguageRuntime.PYTHON3,
            compute=2,
            isolate=2,
            container_server=0
        )
    else:
        request = pb2.RegisterRequest(
            function_name=model_name,
            function_version="1",
            image_name="docker.io/iud2i/ckn_faas_{}-iluvatar-action-http:latest".format(model_name),
            memory=512,
            cpus=1,
            parallel_invokes=1,
            transaction_id=str(uuid.uuid4()),
            language=pb2.LanguageRuntime.PYTHON3,
            compute=2,
            isolate=2,
            container_server=0
        )

    response = worker.register(request)
    print(response)