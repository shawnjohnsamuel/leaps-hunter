"""Minimal YAML-subset parser for the v7 §20 config.

Supports exactly what that document uses: block mappings (consistent-width
indentation), inline flow lists `[a, b]`, inline flow maps `{k: v, ...}`, and
scalar null/bool/int/float/quoted-or-bare string. No block sequences
(`- item`), anchors, multi-doc, or multi-line strings.

This exists so the engine has zero third-party dependencies (ADR 0010): the
cloud routine sandbox is not guaranteed to have PyYAML installed, and there is
no setup-script step to install it as of Phase 0. If §20 ever needs a YAML
feature outside this subset, extend this parser rather than adding a
dependency and hoping it is present at runtime.
"""
from __future__ import annotations

_NULLS = {"null", "Null", "NULL", "~", ""}
_TRUE = {"true", "True", "TRUE"}
_FALSE = {"false", "False", "FALSE"}


def _strip_comment(line: str) -> str:
    in_quote = None
    for i, ch in enumerate(line):
        if in_quote:
            if ch == in_quote:
                in_quote = None
        elif ch in ("'", '"'):
            in_quote = ch
        elif ch == "#":
            return line[:i]
    return line


def _split_top_level(inner: str) -> list[str]:
    """Split on commas that are not inside a quoted string."""
    items: list[str] = []
    cur: list[str] = []
    in_quote = None
    for ch in inner:
        if in_quote:
            cur.append(ch)
            if ch == in_quote:
                in_quote = None
        elif ch in ("'", '"'):
            in_quote = ch
            cur.append(ch)
        elif ch == ",":
            items.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        items.append("".join(cur))
    return items


def _parse_scalar(raw: str):
    s = raw.strip()
    if s in _NULLS:
        return None
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [] if not inner else [_parse_scalar(x) for x in _split_top_level(inner)]
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1].strip()
        if not inner:
            return {}
        out = {}
        for item in _split_top_level(inner):
            k, _, v = item.partition(":")
            out[k.strip()] = _parse_scalar(v.strip())
        return out
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def load(text: str) -> dict:
    root: dict = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw_line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            raise ValueError(f"line {lineno}: expected 'key: value', got {raw_line!r}")
        key, _, value = stripped.partition(":")
        key, value = key.strip(), value.strip()

        while indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if value == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)
    return root
