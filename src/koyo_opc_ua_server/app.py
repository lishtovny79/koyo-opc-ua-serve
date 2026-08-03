"""Application entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from .config import load_config
from .opc_server import OpcServerManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Koyo / DirectLOGIC OPC UA server")
    parser.add_argument("--config", type=Path, default=Path("config/config.toml"))
    args = parser.parse_args()
    try:
        config = load_config(args.config.resolve())
    except ValueError as exc:
        parser.error(str(exc))
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logging.getLogger("asyncua").setLevel(logging.WARNING)
    try:
        asyncio.run(OpcServerManager(config).run())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Server stopped")


if __name__ == "__main__":
    main()
