from __future__ import annotations

import argparse
import asyncio
from typing import Any

from amqtt.broker import Broker


def _build_config(host: str, port: int) -> dict[str, Any]:
    return {
        "listeners": {
            "default": {
                "type": "tcp",
                "bind": f"{host}:{port}",
            }
        },
        "sys_interval": 0,
        "auth": {"allow-anonymous": True},
        "topic-check": {"enabled": False},
    }


async def _serve(host: str, port: int) -> None:
    broker = Broker(_build_config(host, port))
    await broker.start()
    print(f"[python-broker] listening on {host}:{port}", flush=True)
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await broker.shutdown()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start a local MQTT broker backed by amqtt.")
    parser.add_argument("--host", default="127.0.0.1", help="Broker host to bind.")
    parser.add_argument("--port", type=int, default=1883, help="Broker port to bind.")
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        asyncio.run(_serve(args.host, args.port))
    except KeyboardInterrupt:
        print("[python-broker] stopping", flush=True)


if __name__ == "__main__":
    main()
