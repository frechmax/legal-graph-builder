#!/usr/bin/env python3
"""
Konvertiert HHBauO/HHBauO.html in eine ELI-konforme Turtle-Datei
mit hierarchischen Untergliederungen (Teil/Abschnitt/§/Absatz/Nummer).

Nutzung:
    python convert_to_eli_rdf.py
    python convert_to_eli_rdf.py --input HHBauO.html --output hbauo_2025_eli.ttl
"""

from __future__ import annotations

import argparse
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple


ELI = "http://data.europa.eu/eli/ontology#"
BASE_RES = "https://example.org/eli/de/hh/hbauo/2025"


def norm_text(value: str) -> str:
    # Normalize all whitespace (including non-breaking spaces from HTML entities).
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()


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
    return value.replace("\\", "\\\\").replace('"', '\\"')


def parse_absatz(text: str) -> Tuple[Optional[str], str]:
    text = norm_text(text)
    m = re.match(r"^\((\d+[a-z]?)\)\s*(.*)$", text, flags=re.IGNORECASE)
    if not m:
        return None, text
    return m.group(1), norm_text(m.group(2))


def split_heading_lines(text: str) -> List[str]:
    lines = [norm_text(x) for x in re.split(r"[\r\n]+", text)]
    return [x for x in lines if x]


class HBauOParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.units: List[dict] = []
        self.document_title = "Hamburgische Bauordnung (HBauO) vom 6. Januar 2025"

        self._in_heading: Optional[str] = None
        self._heading_chunks: List[str] = []

        self._capture_kind: Optional[str] = None  # p, dt, dd
        self._capture_chunks: List[str] = []

        self._current_paragraph: Optional[dict] = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in {"h3", "h4", "h5", "h6"}:
            self._flush_current_paragraph()
            self._in_heading = tag
            self._heading_chunks = []
            return

        if self._in_heading and tag == "br":
            self._heading_chunks.append("\n")
            return

        if self._current_paragraph and tag in {"p", "dt", "dd"} and self._capture_kind is None:
            self._capture_kind = tag
            self._capture_chunks = []
            return

        if self._capture_kind and tag == "br":
            self._capture_chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._in_heading == tag:
            text = "".join(self._heading_chunks)
            self._consume_heading(text)
            self._in_heading = None
            self._heading_chunks = []
            return

        if self._capture_kind == tag:
            text = norm_text("".join(self._capture_chunks))
            if text and self._current_paragraph is not None:
                self._current_paragraph["elements"].append((self._capture_kind, text))
            self._capture_kind = None
            self._capture_chunks = []

    def handle_data(self, data: str) -> None:
        if self._in_heading:
            self._heading_chunks.append(data)
            return

        if self._capture_kind:
            self._capture_chunks.append(data)

    def close(self) -> None:
        super().close()
        self._flush_current_paragraph()

    def _flush_current_paragraph(self) -> None:
        if self._current_paragraph is not None:
            self.units.append(self._current_paragraph)
            self._current_paragraph = None

    def _consume_heading(self, text: str) -> None:
        if not text:
            return

        lines = split_heading_lines(text)
        if not lines:
            return

        heading = norm_text(" ".join(lines))

        if "Hamburgische Bauordnung" in heading and "(HBauO)" in heading:
            self.document_title = norm_text(re.sub(r"\*\)?$", "", heading))
            return

        if heading == "Nichtamtliches Inhaltsverzeichnis":
            return

        if lines[0].startswith("§"):
            number, title = self._parse_paragraph_heading(lines)
            if not number:
                return
            self._current_paragraph = {
                "kind": "paragraph",
                "number": number,
                "title": title or f"§ {number}",
                "elements": [],
            }
            return

        if re.search(r"\bTeil\b", lines[0], flags=re.IGNORECASE):
            self.units.append(
                {
                    "kind": "part",
                    "number": lines[0],
                    "title": lines[1] if len(lines) > 1 else lines[0],
                }
            )
            return

        if re.search(r"\bAbschnitt\b", lines[0], flags=re.IGNORECASE):
            self.units.append(
                {
                    "kind": "section",
                    "number": lines[0],
                    "title": lines[1] if len(lines) > 1 else lines[0],
                }
            )

    @staticmethod
    def _parse_paragraph_heading(lines: List[str]) -> Tuple[str, str]:
        combined = " ".join(lines)
        m = re.match(r"^§\s*([0-9]+[a-zA-Z]?)\s*(.*)$", combined)
        if not m:
            return "", ""
        number = m.group(1)

        title = ""
        if len(lines) >= 2:
            title = lines[1]
        elif m.group(2):
            title = m.group(2)

        title = norm_text(title)
        if title.lower().startswith(number.lower()):
            title = norm_text(title[len(number) :])
        return number, title


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


def parse_html(path: Path) -> HBauOParser:
    raw = path.read_text(encoding="utf-8", errors="replace")
    parser = HBauOParser()
    parser.feed(raw)
    parser.close()
    return parser


def build_graph(parsed: HBauOParser) -> List[str]:
    triples: List[str] = []
    triples.append(
        f"<{BASE_RES}> a eli:LegalResource ;\n"
        '    eli:number "HBauO 2025" ;\n'
        f'    eli:title "{escape_ttl(parsed.document_title)}"@de .'
    )

    current_part: Optional[str] = None
    current_section: Optional[str] = None
    part_idx = 0
    section_idx = 0
    paragraph_count = 0

    for unit in parsed.units:
        kind = unit["kind"]

        if kind == "part":
            part_idx += 1
            section_idx = 0
            part_uri = f"{BASE_RES}/teil/{part_idx}"
            make_subdivision(
                triples=triples,
                uri=part_uri,
                parent_uri=BASE_RES,
                type_name="teil",
                number=unit["number"],
                title=unit["title"],
            )
            current_part = part_uri
            current_section = None
            continue

        if kind == "section":
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
                number=unit["number"],
                title=unit["title"],
            )
            current_section = section_uri
            continue

        if kind != "paragraph":
            continue

        paragraph_count += 1
        parent = current_section or current_part or BASE_RES

        par_no = unit["number"]
        par_uri = f"{BASE_RES}/par_{slug(par_no)}"
        make_subdivision(
            triples=triples,
            uri=par_uri,
            parent_uri=parent,
            type_name="paragraph",
            number=par_no,
            title=unit["title"],
        )

        current_absatz_uri: Optional[str] = None
        pending_number: Optional[str] = None
        for element_kind, text in unit["elements"]:
            text = norm_text(text)
            if not text:
                continue
            if text.lower().startswith("zur einzelansicht"):
                continue

            if element_kind == "p":
                absatz_no, body = parse_absatz(text)
                if absatz_no:
                    absatz_uri = f"{par_uri}/abs_{slug(absatz_no)}"
                    make_subdivision(
                        triples=triples,
                        uri=absatz_uri,
                        parent_uri=par_uri,
                        type_name="absatz",
                        number=absatz_no,
                        description=body if body else None,
                    )
                    current_absatz_uri = absatz_uri
                elif current_absatz_uri:
                    triples.append(
                        f'<{current_absatz_uri}> eli:description "{escape_ttl(text)}"@de .'
                    )
                continue

            if element_kind == "dt":
                pending_number = text.rstrip(".")
                continue

            if element_kind == "dd" and pending_number and current_absatz_uri:
                num_uri = f"{current_absatz_uri}/nr_{slug(pending_number)}"
                make_subdivision(
                    triples=triples,
                    uri=num_uri,
                    parent_uri=current_absatz_uri,
                    type_name="nummer",
                    number=pending_number,
                    description=text,
                )
                pending_number = None

    triples.append(
        f"<{BASE_RES}> eli:description "
        f'"Automatisch aus HHBauO.html erzeugte Struktur mit {paragraph_count} Paragraphen."@de .'
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
            "@prefix ex: <https://example.org/eli/de/hh/hbauo/2025/> .",
            "@prefix exvocab: <https://example.org/vocab/subdivision/> .",
            "@prefix skos:    <http://www.w3.org/2004/02/skos/core#> .",
            "",
            "<https://example.org/eli/de/hh/hbauo/data>",
            "    a owl:Ontology ;",
            "    owl:imports <http://data.europa.eu/eli/ontology> ;",
            '    dcterms:title "HBauO 2025 Instanzdaten (ABox)"@de ;',
            '    dcterms:description "ELI-konforme ABox-Daten zur Hamburgischen Bauordnung 2025"@de .',
            "",
            "",
        ]
    )
    body = "\n\n".join(triples) + "\n"
    path.write_text(header + body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="HHBauO.html", help="Pfad zur HHBauO.html")
    parser.add_argument(
        "--output",
        default="hbauo_2025_eli.ttl",
        help="Zieldatei für Turtle-Ausgabe",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    parsed = parse_html(input_path)
    triples = build_graph(parsed)
    write_ttl(output_path, triples)
    print(f"OK: {output_path}")


if __name__ == "__main__":
    main()
