"""Environment-driven configuration for health agent and poller."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _split_paths(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass(frozen=True)
class AgentConfig:
    host: str
    port: int
    hostname: str
    mount_paths: list[str]

    @classmethod
    def from_env(cls) -> AgentConfig:
        bind = os.getenv("HEALTH_AGENT_BIND", "0.0.0.0:9105")
        host, _, port_raw = bind.rpartition(":")
        port = int(port_raw or "9105")
        mounts = _split_paths(os.getenv("HEALTH_MOUNT_PATHS", "/,/mnt/SeaGate"))
        return cls(
            host=host or "0.0.0.0",  # nosec B104
            port=port,
            hostname=os.getenv("HEALTH_HOSTNAME", "MediaPi"),
            mount_paths=mounts,
        )


@dataclass(frozen=True)
class PollerConfig:
    db_path: str
    local_hostname: str
    remote_hostname: str
    remote_url: str
    remote_enabled: bool
    local_mount_paths: list[str]
    raw_retention_hours: int
    rollup_retention_days: int
    request_timeout: float

    @classmethod
    def from_env(cls) -> PollerConfig:
        return cls(
            db_path=os.getenv("HEALTH_DB_PATH", "/var/lib/health-monitor/health.sqlite"),
            local_hostname=os.getenv("HEALTH_LOCAL_HOSTNAME", "DietPiServer"),
            remote_hostname=os.getenv("HEALTH_REMOTE_HOSTNAME", "MediaPi"),
            remote_url=os.getenv(
                "HEALTH_REMOTE_URL",
                "http://192.168.68.100:9105/health",
            ),
            remote_enabled=_env_bool("HEALTH_REMOTE_ENABLED", True),
            local_mount_paths=_split_paths(os.getenv("HEALTH_LOCAL_MOUNT_PATHS", "/")),
            raw_retention_hours=int(os.getenv("HEALTH_RAW_RETENTION_HOURS", "48")),
            rollup_retention_days=int(os.getenv("HEALTH_ROLLUP_RETENTION_DAYS", "30")),
            request_timeout=float(os.getenv("HEALTH_REQUEST_TIMEOUT", "5")),
        )
