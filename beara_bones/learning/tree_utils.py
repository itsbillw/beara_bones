"""Directory tree helpers for the learning vault sidebar."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from learning.models import LearningDirectory


@dataclass
class DirectoryNode:
    directory: LearningDirectory
    children: list[DirectoryNode] = field(default_factory=list)


def build_directory_tree(directories: list[LearningDirectory]) -> list[DirectoryNode]:
    """Build nested tree from flat directory queryset."""
    by_id: dict[UUID, DirectoryNode] = {d.id: DirectoryNode(directory=d) for d in directories}
    roots: list[DirectoryNode] = []
    for node in by_id.values():
        parent_id = node.directory.parent_id
        if parent_id and parent_id in by_id:
            by_id[parent_id].children.append(node)
        else:
            roots.append(node)

    def sort_nodes(nodes: list[DirectoryNode]) -> None:
        nodes.sort(key=lambda n: n.directory.name.lower())
        for child in nodes:
            sort_nodes(child.children)

    sort_nodes(roots)
    return roots


def active_directory_path(directory: LearningDirectory | None) -> set[UUID]:
    """Return directory IDs on path to current folder (for sidebar highlight)."""
    if directory is None:
        return set()
    return {d.id for d in directory.get_ancestors()} | {directory.id}
