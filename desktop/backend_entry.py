"""Desktop sidecar. freeze_support must run before importing application code."""
import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()
    import asyncio
    import json
    import socket
    import sys
    import threading
    import os
    import uvicorn
    from cyberarm.server import app

    if sys.platform == 'win32':
        from win_job import create_job
        job = create_job()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', log_level='warning'))

    def watch_parent():
        # Blocking buffered stdin reads prevent Windows spawn from closing stdin.
        # Wait on the Electron process handle instead; workers inherit no reader.
        parent = int(os.environ['CYBERARM_PARENT_PID'])
        if sys.platform == 'win32':
            import ctypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
            kernel.OpenProcess.restype = ctypes.c_void_p
            kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            kernel.CloseHandle.argtypes = [ctypes.c_void_p]
            handle = kernel.OpenProcess(0x00100000, False, parent)
            if handle:
                kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
                kernel.CloseHandle(handle)
            # Closing our job handle on process exit kills every planning worker.
            os._exit(0)
        else:
            import time
            import signal
            while True:
                try: os.kill(parent, 0)
                except ProcessLookupError: os.killpg(os.getpgrp(), signal.SIGKILL)
                time.sleep(1)

    if os.environ.get('CYBERARM_PARENT_PID'):
        threading.Thread(target=watch_parent, daemon=True).start()

    async def run():
        task = asyncio.create_task(server.serve(sockets=[sock]))
        while not server.started:
            if task.done():
                await task
                raise RuntimeError('后端启动失败')
            await asyncio.sleep(.05)
        print(json.dumps({'type': 'ready', 'port': port}), flush=True)
        await task

    asyncio.run(run())
