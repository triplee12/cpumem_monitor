#!/usr/bin/python3
"""Application layer for the App Monitor."""
import argparse
import asyncio
from random import randint, uniform
from datetime import datetime as dt
from datetime import timezone as tz
from contextlib import suppress
import zmq
import zmq.asyncio
import psutil

ctx = zmq.asyncio.Context()


async def stats_reporter(color: str) -> None:
    """Stats reporter for applications statistics."""
    p = psutil.Process()
    sock = ctx.socket(zmq.PUB)
    sock.setsockopt(zmq.LINGER, 1)
    sock.connect('tcp://127.0.0.1:5555')

    with suppress(asyncio.CancelledError):
        while True:
            await sock.send_json(dict(
                color=color,
                timestamp=dt.now(tz=tz.utc).isoformat(),
                cpu=p.cpu_percent(),
                mem=p.memory_full_info().rss / 1024 / 1024
            ))
            await asyncio.sleep(1)
    sock.close()


async def main(args) -> None:
    """Entry point for the application layer."""
    asyncio.create_task(stats_reporter(args.color))
    leak: list = []

    with suppress(asyncio.CancelledError):
        while True:
            sum(range(randint(1_000, 10_000_000)))
            await asyncio.sleep(uniform(0, 1))
            leak += [0] * args.leak


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--color', type=str)
    parser.add_argument('--leak', type=int, default=0)
    args_ = parser.parse_args()
    try:
        asyncio.run(main(args_))
    except KeyboardInterrupt:
        print('Leaving...')
        ctx.term()
