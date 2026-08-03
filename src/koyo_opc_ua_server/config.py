"""Configuration loading for the OPC UA server."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerConfig:
    plc_host: str
    plc_port: int
    tags_csv: Path | None
    tags_database: Path
    backup_directory: Path
    endpoint: str
    poll_interval: float
    write_subscription_interval_ms: int
    receive_timeout: float
    read_block_words: int
    log_level: str


def load_config(path: Path) -> ServerConfig:
    try:
        with path.open("rb") as file:
            raw = tomllib.load(file)
    except FileNotFoundError as exc:
        raise ValueError(f"Configuration file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML configuration in {path}: {exc}") from exc

    plc = raw.get("plc", {})
    opcua = raw.get("opcua", {})
    polling = raw.get("polling", {})
    logging = raw.get("logging", {})
    csv_value = str(plc.get("tags_csv", "")).strip()
    tags_csv = Path(csv_value) if csv_value else None
    if tags_csv is not None and not tags_csv.is_absolute():
        tags_csv = (path.parent / tags_csv).resolve()
    tags_database = Path(str(plc.get("tags_database", "../data/tags.db")))
    backup_directory = Path(str(plc.get("backup_directory", "../backups")))
    if not tags_database.is_absolute():
        tags_database = (path.parent / tags_database).resolve()
    if not backup_directory.is_absolute():
        backup_directory = (path.parent / backup_directory).resolve()

    config = ServerConfig(
        plc_host=str(plc.get("host", "192.168.0.55")),
        plc_port=int(plc.get("port", 28784)),
        tags_csv=tags_csv,
        tags_database=tags_database,
        backup_directory=backup_directory,
        endpoint=str(opcua.get("endpoint", "opc.tcp://0.0.0.0:4840/freeopcua/server/")),
        poll_interval=float(polling.get("interval_seconds", 0.1)),
        write_subscription_interval_ms=int(polling.get("write_subscription_interval_ms", 10)),
        receive_timeout=float(polling.get("receive_timeout_seconds", 0.8)),
        read_block_words=int(polling.get("read_block_words", 30)),
        log_level=str(logging.get("level", "INFO")).upper(),
    )
    if not config.plc_host or not 1 <= config.plc_port <= 65535:
        raise ValueError("plc.host and plc.port must be valid")
    if config.poll_interval < 0 or config.receive_timeout <= 0:
        raise ValueError("polling intervals must be non-negative and timeout must be positive")
    if not 1 <= config.write_subscription_interval_ms <= 60_000:
        raise ValueError("write_subscription_interval_ms must be between 1 and 60000")
    if not 1 <= config.read_block_words <= 127:
        raise ValueError("read_block_words must be between 1 and 127")
    if not config.endpoint.startswith("opc.tcp://"):
        raise ValueError("opcua.endpoint must start with opc.tcp://")
    return config
