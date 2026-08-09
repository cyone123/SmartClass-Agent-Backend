"""Start the benchmark backend with a Windows-compatible async event loop."""

from __future__ import annotations

import asyncio
import sys

import uvicorn

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    config = uvicorn.Config("app.main:app", host="127.0.0.1", port=port, loop="asyncio")
    server = uvicorn.Server(config)
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
