from __future__ import annotations

import pytest

from loop_agent.orchestration.specs import StepInstance, expand_fanout


def test_expand_fanout_creates_instances():
    instances = expand_fanout(
        "scout",
        [{"symbol": "AAPL"}, {"symbol": "GOOG"}],
        id_prefix="s",
    )
    assert len(instances) == 2
    assert instances[0].id == "s_0"
    assert instances[0].step == "scout"
    assert instances[0].user_vars == {"symbol": "AAPL"}
    assert instances[1].id == "s_1"
    assert instances[1].user_vars == {"symbol": "GOOG"}


def test_expand_fanout_empty_items():
    assert expand_fanout("scout", [], id_prefix="s") == []


def test_expand_fanout_validates_prefix():
    with pytest.raises(ValueError):
        expand_fanout("scout", [{}], id_prefix="")
