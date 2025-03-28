# The code tests basic RPC call for iluvatar
import grpc
import iluvatar_rpc_pb2
import iluvatar_rpc_pb2_grpc

# Connect to the Rust gRPC server
channel = grpc.insecure_channel('127.0.0.1:8079')  # Adjust host/port if needed
stub = iluvatar_rpc_pb2_grpc.IluvatarWorkerStub(channel)

# Create and send a PingRequest
request = iluvatar_rpc_pb2.PingRequest(
    message="hello from python!",
    transaction_id="tx-123"
)

response = stub.ping(request)
print("Response from Rust server:", response.message)