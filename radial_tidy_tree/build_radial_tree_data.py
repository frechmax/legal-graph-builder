#!/usr/bin/env python3
"""Build a D3-friendly hierarchy JSON from an ELI Turtle file.

The generated JSON keeps this hierarchy shape where present:
Teil -> Abschnitt -> Paragraph -> Absatz -> Satz -> Nummer
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List

URI_RE = r"<([^>]+)>"


def decode_ttl_string(value: str) -> str:
    return (
        value.replace("\\n", "\n")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
        .strip()
    )


def parse_ttl(ttl_text: str) -> tuple[Dict[str, dict], Dict[str, List[str]], str]:
    nodes: Dict[str, dict] = {}
    children: Dict[str, List[str]] = {}
    root_uri = ""

    for block in ttl_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue

        m_subject = re.match(URI_RE, block)
        if not m_subject:
            continue
        subject = m_subject.group(1)

        nodes.setdefault(
            subject,
            {
                "uri": subject,
                "type": "",
                "number": "",
                "title": "",
                "description": "",
                "is_legal_resource": False,
            },
        )

        if "a eli:LegalResource ;" in block:
            nodes[subject]["is_legal_resource"] = True
            root_uri = subject

        m_type = re.search(r"eli:type_subdivision\s+exvocab:([a-zA-Z0-9_\-]+)", block)
        if m_type:
            nodes[subject]["type"] = m_type.group(1).lower()

        m_number = re.search(r'eli:number\s+"((?:\\.|[^"])*)"', block)
        if m_number:
            nodes[subject]["number"] = decode_ttl_string(m_number.group(1))

        m_title = re.search(r'eli:title\s+"((?:\\.|[^"])*)"@de', block)
        if m_title:
            nodes[subject]["title"] = decode_ttl_string(m_title.group(1))

        m_description = re.search(r'eli:description\s+"((?:\\.|[^"])*)"@de', block)
        if m_description:
            nodes[subject]["description"] = decode_ttl_string(m_description.group(1))

        m_has_part = re.search(rf"eli:has_part\s+{URI_RE}\s*\.", block)
        if m_has_part:
            target = m_has_part.group(1)
            children.setdefault(subject, []).append(target)

    if not root_uri:
        raise ValueError("No eli:LegalResource node found in the TTL file.")

    return nodes, children, root_uri


def type_rank(node_type: str) -> int:
    order = {
        "teil": 1,
        "abschnitt": 2,
        "paragraph": 3,
        "absatz": 4,
        "satz": 5,
        "nummer": 6,
    }
    return order.get(node_type, 99)


def natural_token(value: str) -> tuple[int, str]:
    m = re.search(r"(\d+)([a-z]*)", value.lower())
    if not m:
        return (10**9, value.lower())
    return (int(m.group(1)), m.group(2))


def uri_rank(uri: str, node_type: str) -> tuple[int, str]:
    if node_type == "teil":
        m = re.search(r"/teil/(\d+)$", uri)
        return (int(m.group(1)), "") if m else (10**9, uri)
    if node_type == "abschnitt":
        m = re.search(r"/abschnitt/(\d+)$", uri)
        return (int(m.group(1)), "") if m else (10**9, uri)
    if node_type == "paragraph":
        m = re.search(r"/par_([^/]+)$", uri)
        return natural_token(m.group(1)) if m else (10**9, uri)
    if node_type == "absatz":
        m = re.search(r"/abs_([^/]+)$", uri)
        return natural_token(m.group(1)) if m else (10**9, uri)
    if node_type == "satz":
        m = re.search(r"/satz_([^/]+)$", uri)
        return natural_token(m.group(1)) if m else (10**9, uri)
    if node_type == "nummer":
        m = re.search(r"/nr_([^/]+)$", uri)
        return natural_token(m.group(1)) if m else (10**9, uri)
    return (10**9, uri)


def build_label(node: dict) -> str:
    if node.get("is_legal_resource"):
        return node.get("title") or node.get("number") or "Dokument"

    node_type = node.get("type", "")
    number = node.get("number", "").strip()
    title = node.get("title", "").strip()

    prefix_by_type = {
        "teil": "",
        "abschnitt": "",
        "paragraph": "§",
        "absatz": "Abs.",
        "satz": "Satz",
        "nummer": "Nr.",
    }

    prefix = prefix_by_type.get(node_type, node_type.capitalize() if node_type else "Knoten")
    head = f"{prefix} {number}".strip()

    if title and node_type in {"teil", "abschnitt", "paragraph"}:
        return f"{head}: {title}"
    return head


def to_tree(node_uri: str, nodes: Dict[str, dict], children: Dict[str, List[str]]) -> dict:
    node = nodes.get(node_uri, {"uri": node_uri})
    kids = children.get(node_uri, [])

    def sort_key(child_uri: str) -> tuple[int, str, str]:
        child = nodes.get(child_uri, {})
        child_type = child.get("type", "")
        uri_key_num, uri_key_suffix = uri_rank(child_uri, child_type)
        return (
            type_rank(child_type),
            uri_key_num,
            uri_key_suffix,
            child.get("number", ""),
            child_uri,
        )

    kids_sorted = sorted(kids, key=sort_key)

    result = {
        "name": build_label(node),
        "uri": node_uri,
        "type": "legalresource" if node.get("is_legal_resource") else node.get("type", "unknown"),
        "number": node.get("number", ""),
        "title": node.get("title", ""),
        "description": node.get("description", ""),
    }

    if kids_sorted:
        result["children"] = [to_tree(child_uri, nodes, children) for child_uri in kids_sorted]

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to input TTL file")
    parser.add_argument("--output", required=True, help="Path to output JSON file")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    ttl_text = input_path.read_text(encoding="utf-8")
    nodes, children, root_uri = parse_ttl(ttl_text)
    tree = to_tree(root_uri, nodes, children)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK: {output_path}")


if __name__ == "__main__":
    main()
