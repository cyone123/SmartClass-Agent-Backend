from __future__ import annotations

import argparse
import asyncio
import selectors
import sys
from pathlib import Path
from socket import socket

import uvicorn
from uvicorn.main import STARTUP_FAILURE
from uvicorn.server import Server
from uvicorn.supervisors import ChangeReload

BASE_DIR = Path(__file__).resolve().parent


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


class SelectorServer(Server):
    def run(self, sockets: list[socket] | None = None) -> None:
        return asyncio.run(
            self.serve(sockets=sockets),
            loop_factory=selector_loop_factory,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the FastAPI backend with a SelectorEventLoop.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--log-level", default="info")
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> uvicorn.Config:
    return uvicorn.Config(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=[str(BASE_DIR)],
        log_level=args.log_level,
    )


def main() -> None:
    args = parse_args()
    config = build_config(args)
    server = SelectorServer(config=config)

    try:
        if config.should_reload:
            sock = config.bind_socket()
            ChangeReload(config, target=server.run, sockets=[sock]).run()
        else:
            server.run()
    except KeyboardInterrupt:
        pass
    finally:
        if config.uds:
            import os

            if os.path.exists(config.uds):
                os.remove(config.uds)

    if not server.started and not config.should_reload:
        sys.exit(STARTUP_FAILURE)


if __name__ == "__main__":
    main()
