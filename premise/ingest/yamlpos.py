"""YAML helpers that keep line numbers, so every graph fact can point back to the exact source line.

Also contains the line preserving editors used to apply scenario patches and, later, fix PRs:
they change one scalar in place and never re dump the file, so comments and layout survive.
"""
from __future__ import annotations

import json
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode


def compose(text: str) -> Node | None:
    return yaml.compose(text, Loader=yaml.SafeLoader)


def mapping_get(node: Node | None, key: str) -> tuple[ScalarNode | None, Node | None]:
    """Return (key_node, value_node) for a key in a mapping node."""
    if not isinstance(node, MappingNode):
        return None, None
    for k, v in node.value:
        if isinstance(k, ScalarNode) and k.value == key:
            return k, v
    return None, None


def find(node: Node | None, dotted: str) -> tuple[ScalarNode | None, Node | None]:
    """Walk a dotted key path (a.b.c) through nested mappings."""
    key_node: ScalarNode | None = None
    current = node
    for part in dotted.split("."):
        key_node, current = mapping_get(current, part)
        if current is None:
            return None, None
    return key_node, current


def line(node: Node | None, offset: int = 0) -> int | None:
    """1 based line of a node, shifted by offset (for front matter inside a larger file)."""
    if node is None:
        return None
    return node.start_mark.line + 1 + offset


def scalar_value(node: Node | None) -> Any:
    """Convert a scalar node to its Python value using the safe loader's resolution rules."""
    if node is None:
        return None
    return yaml.safe_load(yaml.serialize(node))


def items(node: Node | None) -> list[Node]:
    return list(node.value) if isinstance(node, SequenceNode) else []


def _render(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value))  # a JSON string is a valid YAML double quoted scalar


def set_value(text: str, dotted: str, value: Any) -> str:
    """Replace one scalar value in place. Raises KeyError if the key path does not exist."""
    _, vnode = find(compose(text), dotted)
    if not isinstance(vnode, ScalarNode):
        raise KeyError(dotted)
    return text[: vnode.start_mark.index] + _render(value) + text[vnode.end_mark.index :]


def delete_key(text: str, dotted: str) -> str:
    """Remove the line holding a scalar key. Raises KeyError if absent."""
    knode, vnode = find(compose(text), dotted)
    if knode is None or not isinstance(vnode, ScalarNode):
        raise KeyError(dotted)
    lines = text.splitlines(keepends=True)
    start, end = knode.start_mark.line, vnode.end_mark.line
    return "".join(lines[:start] + lines[end + 1 :])
