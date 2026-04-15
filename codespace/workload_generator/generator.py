import asyncio, time

import numpy as np

from config import workload_profiles
from config import deadline_profiles_ms
from client import send_request
from utils import generate_id

import asyncio
import time
from config import workload_profiles, deadline_profiles_ms, iar_profiles_ms
from client import send_request
from utils import generate_id

async def generate_workload(profile_name, duration_sec, mode="vary_deadline"):
    """
    mode = "vary_deadline" → change deadline, keep IAR fixed
    mode = "vary_iar"      → change IAR, keep deadline fixed
    """

    # iar = iar_profiles["short"] / 1000.0

    default_deadline_ms = 2000
    default_air_ms = 100

    req_index = 0
    tasks = []

    if mode == "vary_deadline":
        iar_sec = default_air_ms / 1000.0
        deadlines = deadline_profiles_ms[profile_name]

        for deadline_ms in deadlines:
            start_time = time.time()
            end_time = time.time() + duration_sec
            while time.time() < end_time:
                req_id = generate_id(req_index)
                current_time_sec = time.time() - start_time
                task = asyncio.create_task(send_request(req_id, deadline_ms, default_air_ms, mode,current_time_sec))
                tasks.append(task)
                req_index += 1
                sleep_sec = np.random.exponential(scale=iar_sec)
                await asyncio.sleep(sleep_sec)
                # await asyncio.sleep(iar_sec)

    elif mode == "vary_iar":
        iars = iar_profiles_ms[profile_name]
        for iar_ms in iars:
            iar_sec = iar_ms / 1000.0
            start_time = time.time()
            end_time = time.time() + duration_sec
            while time.time() < end_time:
                req_id = generate_id(req_index)
                current_time_sec = time.time() - start_time
                task = asyncio.create_task(send_request(req_id, default_deadline_ms, iar_ms, mode,current_time_sec))
                tasks.append(task)
                req_index += 1
                sleep_sec = np.random.exponential(scale=iar_sec)
                await asyncio.sleep(sleep_sec)
                # await asyncio.sleep(iar_sec)

    await asyncio.gather(*tasks)
