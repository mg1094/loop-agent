from __future__ import annotations

import pytest

from loop_agent.orchestration.dag import topological_layers, validate_dag


def _inst(id: str, depends_on: list[str] | None = None):
    """Minimal duck-typed instance for testing the DAG engine."""
    from types import SimpleNamespace

    return SimpleNamespace(id=id, depends_on=list(depends_on or []))


def test_topological_layers_linear_chain():
    instances = [_inst("a"), _inst("b", ["a"]), _inst("c", ["b"])]
    layers = topological_layers(instances)
    assert [[n.id for n in layer] for layer in layers] == [["a"], ["b"], ["c"]]


def test_topological_layers_fan_out_fan_in():
    instances = [
        _inst("root"),
        _inst("a", ["root"]),
        _inst("b", ["root"]),
        _inst("merge", ["a", "b"]),
    ]
    layers = topological_layers(instances)
    assert layers[0] == [instances[0]]
    assert set(n.id for n in layers[1]) == {"a", "b"}
    assert layers[2] == [instances[3]]


def test_topological_layers_empty_list():
    assert topological_layers([]) == []


def test_topological_layers_single_node():
    instances = [_inst("only")]
    assert [[n.id for n in layer] for layer in topological_layers(instances)] == [["only"]]


def test_validate_dag_detects_cycle():
    instances = [_inst("a", ["b"]), _inst("b", ["a"])]
    with pytest.raises(ValueError, match="cycle detected"):
        validate_dag(instances)


def test_validate_dag_detects_self_loop():
    instances = [_inst("a", ["a"])]
    with pytest.raises(ValueError, match="cycle detected"):
        validate_dag(instances)
