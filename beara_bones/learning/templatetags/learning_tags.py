"""Template tags for the learning vault."""

from __future__ import annotations

from django import template

register = template.Library()


@register.filter
def filesizeformat_bytes(value: object) -> str:
    """Format a byte count for display in the file browser."""
    if isinstance(value, bool):
        return "—"
    if isinstance(value, (int, float)):
        num = int(value)
    elif isinstance(value, str) and value.isdigit():
        num = int(value)
    else:
        return "—"
    if num < 0:
        return "—"
    if num == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"
