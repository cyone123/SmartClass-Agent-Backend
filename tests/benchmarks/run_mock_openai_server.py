"""Start the benchmark Mock OpenAI-compatible server on Windows."""

from __future__ import annotations

import asyncio
import sys

import uvicorn

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9001
    config = uvicorn.Config(
        "tests.benchmarks.mock_openai_server:app",
        host="127.0.0.1",
        port=port,
        loop="asyncio",
        log_level="warning",
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
