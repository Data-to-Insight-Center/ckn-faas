import grpc
import iluvatar_rpc_pb2 as pb2
import iluvatar_rpc_pb2_grpc as pb2_grpc
import uuid

channel = grpc.insecure_channel("127.0.0.1:8079")
worker = pb2_grpc.IluvatarWorkerStub(channel)
# print(pb2.RegisterRequest.DESCRIPTOR.fields_by_name.keys())
# request = pb2.RegisterRequest(
#     function_name="hello1",
#     function_version="1",
#     image_name="docker.io/sunbaixi96/hello-iluvatar-action-unix:latest",
#     memory=128,
#     cpus=1,
#     parallel_invokes=1,
#     transaction_id="tx-001",
#     language=pb2.LanguageRuntime.PYTHON3,
#     compute=1,        # or appropriate platform ID
#     isolate=1,
#     container_server=0
# )

request = pb2.RegisterRequest(
    function_name="resnet152",
    function_version="1",
    image_name="docker.io/sunbaixi96/ckn_switch_middleware-iluvatar-action-unix:latest",
    memory=128,
    cpus=1,
    parallel_invokes=1,
    transaction_id=str(uuid.uuid4()),
    language=pb2.LanguageRuntime.PYTHON3,
    compute=1,        # or appropriate platform ID
    isolate=1,
    container_server=0
)

# request = pb2.RegisterRequest(
#     function_name="cnn",
#     function_version="1",
#     image_name="docker.io/sunbaixi96/cnn_image_classification-iluvatar-action-unix:latest",
#     memory=128,
#     cpus=1,
#     parallel_invokes=1,
#     transaction_id=str(uuid.uuid4()),
#     language=pb2.LanguageRuntime.PYTHON3,
#     compute=1,        # or appropriate platform ID
#     isolate=1,
#     container_server=0
# )



response = worker.register(request)
print(response)