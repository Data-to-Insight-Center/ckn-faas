import asyncio
from generator import generate_workload

if __name__ == "__main__":
    # Choose "short", "medium", or "long"
    asyncio.run(generate_workload("short", duration_sec=0.01 , mode="vary_deadline"))
    # asyncio.run(generate_workload("short", duration_sec=0.02, mode="vary_iar"))