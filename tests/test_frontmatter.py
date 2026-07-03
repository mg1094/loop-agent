from loop_agent.agent.frontmatter import parse_frontmatter


def test_parse_frontmatter():
    text = """---
name: writing
description: Writing assistant.
category: writing
---

## Workflow
1. Plan
2. Draft
"""
    meta, body = parse_frontmatter(text)
    assert meta["name"] == "writing"
    assert meta["category"] == "writing"
    assert "## Workflow" in body


def test_parse_no_frontmatter():
    text = "# Hello\n\nWorld"
    meta, body = parse_frontmatter(text)
    assert meta == {}
    assert body == text
