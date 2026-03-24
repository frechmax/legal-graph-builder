#!/usr/bin/env python3
"""
Konvertiert BauO_BE_2005/content.xml in eine ELI-konforme Turtle-Datei
mit hierarchischen Untergliederungen (Teil/Abschnitt/§/Absatz/Nummer).

Nutzung:
    python convert_to_eli_rdf.py
    python convert_to_eli_rdf.py --input content.xml --output bauo_be_2005_eli.ttl
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


ELI = "http://data.europa.eu/eli/ontology#"
BASE_RES = "https://example.org/eli/de/be/bauo/2005"
BASE_VOCAB = "https://example.org/vocab/subdivision/"


def read_xml_without_doctype(path: Path) -> ET.Element:
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"<!DOCTYPE[^>]*\[[\s\S]*?\]>", "", raw, count=1)
    return ET.fromstring(raw)


def norm_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def slug(value: str) -> str:
    s = norm_text(value).lower()
    replacements = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "§": "par",
    }
    for src, dst in replacements.items():
        s = s.replace(src, dst)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "node"


def escape_ttl(value: str) -> str:
    # Escape backslashes, double quotes and newlines for safe Turtle literals.
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
    )


def first_text(elem: Optional[ET.Element], tag: str) -> str:
    if elem is None:
        return ""
    child = elem.find(tag)
    return norm_text(child.text if child is not None and child.text else "")


def iter_norms(root: ET.Element) -> Iterable[ET.Element]:
    for norm in root.findall("norm"):
        yield norm


def make_subdivision(
    triples: List[str],
    uri: str,
    parent_uri: str,
    type_name: str,
    number: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> None:
    triples.append(
        f"<{uri}> a eli:LegalResourceSubdivision ;\n"
        f"    eli:type_subdivision exvocab:{type_name} ;\n"
        f'    eli:number "{escape_ttl(number)}" ;\n'
        f"    eli:is_part_of <{parent_uri}> ."
    )
    triples.append(f"<{parent_uri}> eli:has_part <{uri}> .")
    if title:
        triples.append(f'<{uri}> eli:title "{escape_ttl(title)}"@de .')
    if description:
        triples.append(f'<{uri}> eli:description "{escape_ttl(description)}"@de .')


def parse_paragraph_title(textdaten: ET.Element, enbez: str) -> str:
    for child in list(textdaten):
        if child.tag.lower().startswith("h"):
            htxt = norm_text("".join(child.itertext()))
            if htxt:
                cleaned = htxt
                cleaned = re.sub(rf"^{re.escape(enbez)}\s*", "", cleaned)
                cleaned = re.sub(r"^\S+\s*", "", cleaned) if cleaned == htxt else cleaned
                return norm_text(cleaned) or enbez
    return enbez


def parse_absatz(text: str) -> Tuple[Optional[str], str]:
    text = norm_text(text)
    m = re.match(r"^\((\d+[a-z]?)\)\s*(.*)$", text, flags=re.IGNORECASE)
    if not m:
        return None, text
    return m.group(1), norm_text(m.group(2))


def parse_list_items(dl: ET.Element) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    current_no = ""
    for node in list(dl):
        if node.tag == "dt":
            current_no = norm_text("".join(node.itertext())).rstrip(".")
        elif node.tag == "dd" and current_no:
            body = norm_text("".join(node.itertext()))
            if body:
                out.append((current_no, body))
            current_no = ""
    return out


def build_graph(root: ET.Element) -> List[str]:
    triples: List[str] = []
    triples.append(
        f"<{BASE_RES}> a eli:LegalResource ;\n"
        '    eli:number "BauO BE 2005" ;\n'
        '    eli:title "Bauordnung für Berlin (BauO Bln) vom 29. September 2005"@de .'
    )

    current_part: Optional[str] = None
    current_section: Optional[str] = None
    paragraph_count = 0
    part_idx = 0
    section_idx = 0

    for norm in iter_norms(root):
        meta = norm.find("metadaten")
        textdaten = norm.find("textdaten")
        enbez = first_text(meta, "enbez")
        gbez = first_text(meta.find("gliederungseinheit") if meta is not None else None, "gliederungsbez")
        gtitel = first_text(meta.find("gliederungseinheit") if meta is not None else None, "gliederungstitel")

        if gbez and not enbez:
            upper = gbez.upper()
            title = gtitel or gbez
            if "TEIL" in upper:
                part_idx += 1
                section_idx = 0
                part_uri = f"{BASE_RES}/teil/{part_idx}"
                make_subdivision(
                    triples=triples,
                    uri=part_uri,
                    parent_uri=BASE_RES,
                    type_name="teil",
                    number=gbez,
                    title=title,
                )
                current_part = part_uri
                current_section = None
            elif "ABSCHNITT" in upper:
                if not current_part:
                    part_idx += 1
                    current_part = f"{BASE_RES}/teil/{part_idx}"
                    make_subdivision(
                        triples=triples,
                        uri=current_part,
                        parent_uri=BASE_RES,
                        type_name="teil",
                        number=f"Teil-{part_idx}",
                        title=f"Teil {part_idx}",
                    )
                section_idx += 1
                section_uri = f"{current_part}/abschnitt/{section_idx}"
                make_subdivision(
                    triples=triples,
                    uri=section_uri,
                    parent_uri=current_part,
                    type_name="abschnitt",
                    number=gbez,
                    title=title,
                )
                current_section = section_uri
            else:
                part_idx += 1
                other_uri = f"{BASE_RES}/gliederung/{part_idx}-{slug(gbez)}"
                make_subdivision(
                    triples=triples,
                    uri=other_uri,
                    parent_uri=BASE_RES,
                    type_name="gliederung",
                    number=gbez,
                    title=title,
                )
                current_part = other_uri
                current_section = None
            continue

        if not enbez.startswith("§"):
            continue
        if textdaten is None:
            continue

        paragraph_count += 1
        par_no = enbez.replace("§", "").strip()
        parent = current_section or current_part or BASE_RES
        par_uri = f"{BASE_RES}/par_{slug(par_no)}"
        par_title = parse_paragraph_title(textdaten, enbez)
        make_subdivision(
            triples=triples,
            uri=par_uri,
            parent_uri=parent,
            type_name="paragraph",
            number=par_no,
            title=par_title,
        )

        current_absatz_uri: Optional[str] = None
        absatz_chunks: dict[str, List[str]] = {}
        for child in list(textdaten):
            if child.tag == "p":
                ptxt = norm_text("".join(child.itertext()))
                absatz_no, body = parse_absatz(ptxt)
                if absatz_no:
                    absatz_uri = f"{par_uri}/abs_{slug(absatz_no)}"
                    make_subdivision(
                        triples=triples,
                        uri=absatz_uri,
                        parent_uri=par_uri,
                        type_name="absatz",
                        number=absatz_no,
                    )
                    current_absatz_uri = absatz_uri
                    absatz_chunks[current_absatz_uri] = [body] if body else []
                elif current_absatz_uri and ptxt:
                    absatz_chunks.setdefault(current_absatz_uri, []).append(ptxt)
            elif child.tag == "dl" and current_absatz_uri:
                for num, body in parse_list_items(child):
                    num_uri = f"{current_absatz_uri}/nr_{slug(num)}"
                    make_subdivision(
                        triples=triples,
                        uri=num_uri,
                        parent_uri=current_absatz_uri,
                        type_name="nummer",
                        number=num,
                        description=body if body else None,
                    )
                    absatz_chunks.setdefault(current_absatz_uri, []).append(
                        f"{num}. {body}"
                    )

        for absatz_uri, chunks in absatz_chunks.items():
            full_text = "\n".join(chunk for chunk in chunks if chunk).strip()
            if full_text:
                triples.append(
                    f'<{absatz_uri}> eli:description "{escape_ttl(full_text)}"@de .'
                )

    triples.append(
        f"<{BASE_RES}> eli:description "
        f"\"Automatisch aus content.xml erzeugte Struktur mit {paragraph_count} Paragraphen.\"@de ."
    )
    return triples


def write_ttl(path: Path, triples: List[str]) -> None:
    header = "\n".join(
        [
            "@prefix owl:     <http://www.w3.org/2002/07/owl#> .",
            "@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .",
            "@prefix rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
            "@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix eli:     <http://data.europa.eu/eli/ontology#> .",
            "@prefix dcterms: <http://purl.org/dc/terms/> .",
            "@prefix ex: <https://example.org/eli/de/be/bauo/2005/> .",
            "@prefix exvocab: <https://example.org/vocab/subdivision/> .",
            "@prefix skos:    <http://www.w3.org/2004/02/skos/core#> .",
            "",
            "<https://example.org/eli/de/be/bauo/data>",
            "    a owl:Ontology ;",
            "    owl:imports <http://data.europa.eu/eli/ontology> ;",
            '    dcterms:title "BauO Berlin 2005 Instanzdaten (ABox)"@de ;',
            '    dcterms:description "ELI-konforme ABox-Daten zur Berliner Bauordnung 2005"@de .',
            "",
            "",
        ]
    )
    body = "\n\n".join(triples) + "\n"
    path.write_text(header + body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="content.xml", help="Pfad zur content.xml")
    parser.add_argument(
        "--output",
        default="bauo_be_2005_eli.ttl",
        help="Zieldatei für Turtle-Ausgabe",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    root = read_xml_without_doctype(input_path)
    triples = build_graph(root)
    write_ttl(output_path, triples)
    print(f"OK: {output_path}")


if __name__ == "__main__":
    main()
