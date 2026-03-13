# SERVER_ADDRESS = "149.165.168.72:8079"

# Model and policy settings
M_TOTAL = [
    "mobilenet_v3_small",
    "resnet18",
    "resnet34",
    "resnet50",
    "resnet101",
    "vit_b_16"
]

POLICY = "greedy"  # or "randomized"
K = 12  # total cores
C = 2   # cores per model
ALPHA = 1.0
ETA = 0.1

COLD_PENALTY = {
    "mobilenet_v3_small": 30,
    "resnet18": 40,
    "resnet34": 50,
    "resnet50": 60,
    "resnet101": 70,
    "vit_b_16": 80,
}


MODEL_PROFILES = {
    "mobilenet_v3_small": {"latency": 0.09597, "accuracy": 0.704413581114262},
    "resnet18": {"latency": 0.10618, "accuracy": 0.712173486609011},
    "resnet34": {"latency": 0.16935, "accuracy": 0.775743676409125},
    "resnet50": {"latency": 0.19834, "accuracy": 0.797511352837085},
    "resnet101": {"latency": 0.33677, "accuracy": 0.822238205507397},
    "vit_b_16": {"latency": 0.48291, "accuracy": 0.751089387536048},
}


OMEGA = {
    "mobilenet_v3_small": 2.5,
    "resnet18": 11.7,
    "resnet34": 21.8,
    "resnet50": 25.6,
    "resnet101": 44.5,
    "vit_b_16": 86.4,
}

SERVER_ADDRESS = "149.165.174.241:8079"

MAX_MODEL_SIZE=6