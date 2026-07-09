"""DAG topology utilities for the configurable Supervisor.

Provides Kahn-based topological layering and eager cycle/unknown-dep
validation. Instances are treated as opaque nodes with ``.id`` and
``.depends_on`` attributes.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Dict, Iterable, List, Set


def validate_dag(instances: Iterable[Any]) -> None:
    """Validate that ``instances`` form a DAG with no unknown dependencies.

    Raises:
        ValueError: If an id is duplicated, a dependency references an unknown
            id, or a cycle exists.
    """
    instances = list(instances)
    ids: Set[str] = set()
    duplicates: List[str] = []
    for inst in instances:
        if inst.id in ids:
            duplicates.append(inst.id)
        ids.add(inst.id)
    if duplicates:
        raise ValueError(f"Duplicate StepInstance.id detected: {duplicates}")

    for inst in instances:
        for dep in inst.depends_on:
            if dep not in ids:
                raise ValueError(
                    f"StepInstance(id={inst.id!r}) depends on unknown id {dep!r}"
                )

    # Kahn's algorithm: if we cannot remove all nodes, there's a cycle.
    in_degree: Dict[str, int] = {inst.id: 0 for inst in instances}
    dependents: Dict[str, List[str]] = {inst.id: [] for inst in instances}
    for inst in instances:
        for dep in inst.depends_on:
            in_degree[inst.id] += 1
            dependents[dep].append(inst.id)

    queue = deque([inst_id for inst_id, deg in in_degree.items() if deg == 0])
    removed: Set[str] = set()
    while queue:
        current = queue.popleft()
        removed.add(current)
        for dep_id in dependents[current]:
            in_degree[dep_id] -= 1
            if in_degree[dep_id] == 0:
                queue.append(dep_id)

    if len(removed) != len(instances):
        remaining = sorted(ids - removed)
        raise ValueError(f"cycle detected among StepInstance ids: {remaining}")


def topological_layers(instances: Iterable[Any]) -> List[List[Any]]:
    """Return instances grouped into topological layers.

    Layer 0 contains all nodes with no dependencies; each subsequent layer
    contains nodes whose dependencies are all in previous layers. Nodes
    within the same layer are independent and may execute in parallel.
    """
    instances = list(instances)
    validate_dag(instances)

    instance_by_id = {inst.id: inst for inst in instances}
    in_degree = {inst.id: len(inst.depends_on) for inst in instances}
    dependents: Dict[str, List[str]] = {inst.id: [] for inst in instances}
    for inst in instances:
        for dep in inst.depends_on:
            dependents[dep].append(inst.id)

    layers: List[List[Any]] = []
    remaining_ids = set(instance_by_id.keys())
    while remaining_ids:
        current_layer_ids = [
            inst_id for inst_id in remaining_ids if in_degree[inst_id] == 0
        ]
        if not current_layer_ids:
            # Should never happen because validate_dag already rejected cycles.
            raise ValueError("cycle detected")

        current_layer = [instance_by_id[inst_id] for inst_id in current_layer_ids]
        layers.append(current_layer)
        for inst_id in current_layer_ids:
            remaining_ids.remove(inst_id)
            for dependent in dependents[inst_id]:
                in_degree[dependent] -= 1

    return layers
