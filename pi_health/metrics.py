"""Read CPU, memory, temperature, and disk usage from Linux pseudo-filesystems."""

from __future__ import annotations

import json
import os
import time
from typing import Any


def _read_proc_stat() -> tuple[int, int]:
    with open("/proc/stat", encoding="utf-8") as handle:
        line = handle.readline()
    parts = line.split()
    values = [int(value) for value in parts[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    total = sum(values[:10])
    return total, idle


def cpu_percent(interval: float = 0.1) -> float:
    """Return CPU busy percentage over a short interval."""
    total_1, idle_1 = _read_proc_stat()
    time.sleep(interval)
    total_2, idle_2 = _read_proc_stat()
    total_delta = total_2 - total_1
    idle_delta = idle_2 - idle_1
    if total_delta <= 0:
        return 0.0
    busy = 100.0 * (1.0 - idle_delta / total_delta)
    return round(max(0.0, min(100.0, busy)), 1)


def memory_bytes() -> tuple[int, int]:
    """Return (used_bytes, total_bytes) from /proc/meminfo."""
    mem_total = 0
    mem_available = 0
    with open("/proc/meminfo", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) * 1024
            elif line.startswith("MemAvailable:"):
                mem_available = int(line.split()[1]) * 1024
    if mem_total <= 0:
        return 0, 0
    mem_used = max(0, mem_total - mem_available)
    return mem_used, mem_total


def temperature_c() -> float | None:
    """Return SoC temperature in Celsius, or None if unavailable."""
    path = "/sys/class/thermal/thermal_zone0/temp"
    try:
        with open(path, encoding="utf-8") as handle:
            milli_c = int(handle.read().strip())
    except OSError:
        return None
    return round(milli_c / 1000.0, 1)


def filesystem_stats(mount_paths: list[str]) -> list[dict[str, Any]]:
    """Return used/total/avail bytes for each configured mount path."""
    results: list[dict[str, Any]] = []
    for mount in mount_paths:
        try:
            stats = os.statvfs(mount)
        except OSError:
            continue
        total = stats.f_frsize * stats.f_blocks
        avail = stats.f_frsize * stats.f_bavail
        used = max(0, total - avail)
        results.append(
            {
                "mount": mount,
                "total": total,
                "used": used,
                "avail": avail,
            }
        )
    return results


def collect_snapshot(hostname: str, mount_paths: list[str]) -> dict[str, Any]:
    """Build a JSON-serializable health snapshot for one host."""
    mem_used, mem_total = memory_bytes()
    return {
        "host": hostname,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cpu_pct": cpu_percent(),
        "mem_used": mem_used,
        "mem_total": mem_total,
        "temp_c": temperature_c(),
        "filesystems": filesystem_stats(mount_paths),
    }


def filesystems_to_json(filesystems: list[dict[str, Any]]) -> str:
    return json.dumps(filesystems, separators=(",", ":"))


def filesystems_from_json(raw: str) -> list[dict[str, Any]]:
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("filesystems_json must be a JSON list")
    return data
