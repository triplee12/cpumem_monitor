#!/usr/bin/python3
"""Collection layer for the App Monitor."""
import asyncio
from datetime import datetime
from contextlib import suppress
from weakref import WeakSet
import json
import zmq
import zmq.asyncio
from aiohttp import web
from aiohttp_sse import sse_response

ctx = zmq.asyncio.Context()
connections = WeakSet()
day = datetime.now().date()


async def collector():
    """Application statistics collector."""
    sock = ctx.socket(zmq.SUB)
    sock.setsockopt_string(zmq.SUBSCRIBE, '')
    sock.bind('tcp://*:5555')

    with suppress(asyncio.CancelledError):
        while data := await sock.recv_json():
            print(data)
            for q in connections:
                await q.put(data)
    sock.close()


async def feed(request):
    """Send feedback to the frontend."""
    queue = asyncio.Queue()
    connections.add(queue)

    with suppress(asyncio.CancelledError):
        async with sse_response(request) as resp:
            while data := await queue.get():
                with open(
                    f'stats_{day}.json', 'a', encoding='utf-8'
                ) as stats:
                    stats.write(json.dumps(
                        data, indent=4, separators=(',', ':')
                    ))
                print('Sending data: ', data)
                await resp.send(json.dumps(data))
    return resp


async def index(request):
    """Return charts.html."""
    return web.FileResponse('./charts.html')


async def start_collector(app):
    """Start collecting metrics."""
    app['collector'] = asyncio.create_task(collector())


async def stop_collector(app):
    """Stop collecting metrics."""
    print('Stopping collector...')
    app['collector'].cancel()
    await app['collector']
    ctx.term()


if __name__ == '__main__':
    app_ = web.Application()
    app_.router.add_route('GET', '/', index)
    app_.router.add_route('GET', '/feed', feed)
    app_.on_startup.append(start_collector)
    app_.on_cleanup.append(stop_collector)
    web.run_app(app_, host='127.0.0.1', port=8088)
