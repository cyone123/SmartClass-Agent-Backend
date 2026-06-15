from __future__ import annotations

import os
from pathlib import Path

from daytona import Daytona, DaytonaConfig, Image, CreateSnapshotParams
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_ROOT / ".env")


SNAPSHOT_NAME = os.getenv("DAYTONA_SNAPSHOT_NAME", "smartclass-node-workspace")
REMOTE_ROOT = os.getenv("DAYTONA_REMOTE_ROOT", "/smartclass").rstrip("/")
REMOTE_WORKSPACE = f"{REMOTE_ROOT}/workspace"
NODE_PACKAGES = [
    os.getenv("DAYTONA_PPTXGENJS_PACKAGE", "pptxgenjs@4.0.1"),
    os.getenv("DAYTONA_DOCX_PACKAGE", "docx@9.6.1"),
]


def main() -> None:
    api_key = os.getenv("DAYTONA_API_KEY")
    api_url = os.getenv("DAYTONA_API_URL", "https://app.daytona.io/api")
    target = os.getenv("DAYTONA_TARGET")
    if not api_key or not target:
        raise RuntimeError("DAYTONA_API_KEY and DAYTONA_TARGET must be configured in backend/.env")

    daytona = Daytona(
        DaytonaConfig(
            api_key=api_key,
            api_url=api_url,
            target=target,
        )
    )

    packages = " ".join(NODE_PACKAGES)
    image = (
        Image.base("node:20-bookworm-slim")
        .run_commands(
            "apt-get update && "
            "apt-get install -y --no-install-recommends python3 python3-pip python3-venv "
            "ca-certificates && "
            "ln -sf /usr/bin/python3 /usr/local/bin/python && "
            "rm -rf /var/lib/apt/lists/*",
            f"mkdir -p {REMOTE_WORKSPACE} {REMOTE_ROOT}/run/outputs",
            f"cd {REMOTE_WORKSPACE} && npm init -y && npm install {packages}",
            (
                f"cd {REMOTE_WORKSPACE} && "
                "node -e \"require('pptxgenjs'); require('docx'); "
                "console.log('node packages ok')\""
            ),
            "python --version && node --version && npm --version",
        )
        .workdir(REMOTE_WORKSPACE)
    )

    print(f"Creating Daytona snapshot: {SNAPSHOT_NAME}")
    print(f"Remote workspace: {REMOTE_WORKSPACE}")
    print(f"Node packages: {', '.join(NODE_PACKAGES)}")
    daytona.snapshot.create(
        CreateSnapshotParams(
            name=SNAPSHOT_NAME,
            image=image,
        ),
        on_logs=lambda chunk: print(chunk, end=""),
    )
    print(f"\nSnapshot creation requested: {SNAPSHOT_NAME}")
    print("After it becomes Active, set this in backend/.env:")
    print(f"DAYTONA_SNAPSHOT={SNAPSHOT_NAME}")
    print("DAYTONA_IMAGE=")


if __name__ == "__main__":
    main()
