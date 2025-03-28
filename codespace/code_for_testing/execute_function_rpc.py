import grpc
import iluvatar_rpc_pb2 as pb2
import iluvatar_rpc_pb2_grpc as pb2_grpc
import json
import os
import uuid
import base64

def read_image_as_bytes(path):
    with open(path, "rb") as f:
        return f.read()

# Connect to the worker
channel = grpc.insecure_channel("127.0.0.1:8079")
worker = pb2_grpc.IluvatarWorkerStub(channel)

# Get your username (same as `whoami`)
username = os.getlogin()  # or os.environ["USER"]

# Create the InvokeRequest
# request = pb2.InvokeRequest(
#     function_name="hello",
#     function_version="1",
#     json_args=json.dumps({"name": username}),
#     transaction_id=str(uuid.uuid4()),  # unique transaction ID
# )

image_bytes = read_image_as_bytes("/home/exouser/ckn-faas/codespace/ckn/jetsons/device/data/images/d2iedgeai3/cat.2.jpg")
image_b64 = base64.b64encode(image_bytes).decode("utf-8")
request = pb2.InvokeRequest(
    function_name="resnet152",
    function_version="1",
    json_args=json.dumps({"model_name": 'resnet152','image_data':image_b64}),
    transaction_id=str(uuid.uuid4()),  # unique transaction ID
)

# request = pb2.InvokeRequest(
#     function_name="cnn",
#     function_version="1",
#     transaction_id=str(uuid.uuid4()),  # unique transaction ID
# )


# Invoke the function
response = worker.invoke(request)

# Print the result
print("✅ Invocation response:")
print("Success:", response.success)
print("Result:", response.json_result)
print("Duration (μs):", response.duration_us)
print("Compute:", response.compute)
print("Container state:", pb2.ContainerState.Name(response.container_state))