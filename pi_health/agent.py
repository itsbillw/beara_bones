#!/usr/bin/env python3
"""LAN-only HTTP agent exposing local health metrics as JSON."""

from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pi_health.config import AgentConfig
from pi_health.metrics import collect_snapshot

LOG = logging.getLogger("pi_health.agent")


class HealthHandler(BaseHTTPRequestHandler):
    hostname: str = "MediaPi"
    mount_paths: list[str] = ["/"]

    def log_message(self, format: str, *args: object) -> None:
        LOG.info("%s - %s", self.address_string(), format % args)

    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(404, "Not found")
            return
        snapshot = collect_snapshot(self.hostname, self.mount_paths)
        payload = json.dumps(snapshot).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_HEAD(self) -> None:
        if self.path != "/health":
            self.send_error(404, "Not found")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = AgentConfig.from_env()
    HealthHandler.hostname = config.hostname
    HealthHandler.mount_paths = config.mount_paths
    server = ThreadingHTTPServer((config.host, config.port), HealthHandler)
    LOG.info("Health agent listening on %s:%s as %s", config.host, config.port, config.hostname)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("Shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
