#!/usr/bin/env python3
"""
Konvertiert BauO_BE_2005/content.xml in eine ELI-konforme Turtle-Datei
mit hierarchischen Untergliederungen (Teil/Abschnitt/§/Absatz/Satz/Nummer).

Erkennt und modelliert interne Querverweise mittels eli:cites.

Nutzung:
    python convert_to_eli_rdf.py
    python convert_to_eli_rdf.py --input content.xml --output bauo_be_2005_eli.ttl
"""

from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


ELI = "http://data.europa.eu/eli/ontology#"
BASE_RES = "https://example.org/eli/de/be/bauo/2005"
BASE_VOCAB = "https://example.org/vocab/subdivision/"


# ─────────────────────────────────────────────────────────────────────────────
# Querverweis-Erkennung (eli:cites)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LegalReference:
    """Repräsentiert einen erkannten Verweis auf einen anderen Rechtstext."""
    paragraph: Optional[str] = None      # z.B. "1", "61", "86a"
    absatz: Optional[str] = None         # z.B. "1", "2"
    satz: Optional[str] = None           # z.B. "1", "2"
    nummer: Optional[str] = None         # z.B. "1", "12"
    buchstabe: Optional[str] = None      # z.B. "a", "b"
    external_law: Optional[str] = None   # z.B. "Bundeskleingartengesetzes"
    raw_text: str = ""                   # Original-Textfragment


# Regex für interne Verweise: § X [Abs./Absatz Y] [Satz Z] [Nr./Nummer N] [Buchst./Buchstabe b]
INTERNAL_REF_PATTERN = re.compile(
    r'§\s*(\d+[a-z]?)'                                      # §-Nummer (erforderlich)
    r'(?:\s+(?:Abs\.|Absatz)\s*(\d+[a-z]?))?'               # Absatz (optional)
    r'(?:\s+(?:Satz|Satzes|S\.)\s*(\d+))?'                         # Satz (optional)
    r'(?:\s+(?:Nr\.|Nummer)\s*(\d+))?'                      # Nummer (optional)
    r'(?:\s+(?:Buchst\.|Buchstabe)\s*([a-z]))?',            # Buchstabe (optional)
    re.IGNORECASE
)

# Bereichs-Verweise: §§ X bis Y (generiert Verweise auf alle Paragraphen im Bereich)
RANGE_REF_PATTERN = re.compile(
    r'§§\s*(\d+[a-z]?)\s+bis\s+(\d+[a-z]?)',
    re.IGNORECASE
)

# Sonderfälle: "Satz 1" ohne § (relativer Verweis innerhalb des aktuellen Absatzes)
RELATIVE_SATZ_PATTERN = re.compile(
    r'(?<![§\d])\b(?:Satz|S\.)\s*(\d+)\b',
    re.IGNORECASE
)

# Externe Gesetze: "§ X des Bundeskleingartengesetzes"
EXTERNAL_LAW_PATTERN = re.compile(
    r'§\s*(\d+[a-z]?)\s+(?:des|der)\s+([A-ZÄÖÜ][a-zäöüß]+(?:gesetz(?:es|buchs?)?|ordnung|verordnung))',
    re.IGNORECASE
)


def expand_paragraph_range(start: str, end: str) -> List[str]:
    """Expandiert einen Paragraphen-Bereich (z.B. '54' bis '56') zu einer Liste ['54', '55', '56'].
    
    Unterstützt auch Paragraphen mit Buchstaben-Suffix (z.B. '86a').
    """
    result = []
    
    # Extrahiere numerischen Teil und optionalen Buchstaben
    start_match = re.match(r'^(\d+)([a-z]?)$', start, re.IGNORECASE)
    end_match = re.match(r'^(\d+)([a-z]?)$', end, re.IGNORECASE)
    
    if not start_match or not end_match:
        return [start, end]  # Fallback bei ungültigem Format
    
    start_num = int(start_match.group(1))
    end_num = int(end_match.group(1))
    
    # Wenn beide einen Buchstaben haben und gleiche Nummer, erweitere Buchstaben
    start_letter = start_match.group(2).lower() if start_match.group(2) else ''
    end_letter = end_match.group(2).lower() if end_match.group(2) else ''
    
    if start_num == end_num and start_letter and end_letter:
        # Bereich innerhalb gleicher Nummer (z.B. 86a bis 86c)
        for c in range(ord(start_letter), ord(end_letter) + 1):
            result.append(f"{start_num}{chr(c)}")
    else:
        # Normaler numerischer Bereich
        for n in range(start_num, end_num + 1):
            result.append(str(n))
    
    return result


def extract_references(text: str) -> List[LegalReference]:
    """Extrahiert alle Querverweise aus einem Text."""
    refs: List[LegalReference] = []
    
    # Externe Verweise erkennen und markieren (um sie später auszuschließen)
    external_spans: Set[Tuple[int, int]] = set()
    for m in EXTERNAL_LAW_PATTERN.finditer(text):
        external_spans.add((m.start(), m.end()))
        refs.append(LegalReference(
            paragraph=m.group(1),
            external_law=m.group(2),
            raw_text=m.group(0)
        ))
    
    # Bereichs-Verweise: §§ X bis Y
    range_spans: Set[Tuple[int, int]] = set()
    for m in RANGE_REF_PATTERN.finditer(text):
        range_spans.add((m.start(), m.end()))
        start_par = m.group(1)
        end_par = m.group(2)
        raw_text = m.group(0)
        
        # Alle Paragraphen im Bereich als einzelne Referenzen hinzufügen
        for par in expand_paragraph_range(start_par, end_par):
            refs.append(LegalReference(
                paragraph=par,
                raw_text=raw_text
            ))
    
    # Interne Verweise
    for m in INTERNAL_REF_PATTERN.finditer(text):
        # Prüfen, ob dieser Match Teil eines externen Verweises oder Bereichs-Verweises ist
        is_external = any(s <= m.start() < e for s, e in external_spans)
        is_range = any(s <= m.start() < e for s, e in range_spans)
        if is_external or is_range:
            continue
            
        refs.append(LegalReference(
            paragraph=m.group(1),
            absatz=m.group(2),
            satz=m.group(3),
            nummer=m.group(4),
            buchstabe=m.group(5),
            raw_text=m.group(0)
        ))
    
    return refs


def resolve_reference_uri(ref: LegalReference, base: str = BASE_RES) -> Optional[str]:
    """Löst einen LegalReference zu einer URI auf. Gibt None zurück bei externen Verweisen."""
    if ref.external_law:
        return None  # Externe Gesetze können wir nicht auflösen
    
    if not ref.paragraph:
        return None
    
    # URI aufbauen
    uri = f"{base}/par_{slug(ref.paragraph)}"
    
    if ref.absatz:
        uri += f"/abs_{slug(ref.absatz)}"
        
        if ref.satz:
            uri += f"/satz_{slug(ref.satz)}"
            
            if ref.nummer:
                uri += f"/nr_{slug(ref.nummer)}"
                
                if ref.buchstabe:
                    uri += f"/buchst_{ref.buchstabe.lower()}"
    
    return uri


@dataclass
class CitationCollector:
    """Sammelt alle eli:cites Relationen während der Grapherstellung."""
    citations: List[Tuple[str, str, str]] = field(default_factory=list)  # (source_uri, target_uri, raw_text)
    known_uris: Set[str] = field(default_factory=set)
    descriptions: Dict[str, str] = field(default_factory=dict)  # uri -> description
    
    def register_uri(self, uri: str, description: Optional[str] = None) -> None:
        """Registriert eine bekannte URI mit optionaler Beschreibung."""
        self.known_uris.add(uri)
        if description:
            self.descriptions[uri] = description
    
    def add_citation(self, source_uri: str, target_uri: str, raw_text: str) -> None:
        """Fügt eine Zitation hinzu, wenn beide URIs bekannt sind."""
        self.citations.append((source_uri, target_uri, raw_text))
    
    def extract_and_add(self, source_uri: str, text: str) -> None:
        """Extrahiert Verweise aus Text und fügt Zitationen hinzu."""
        for ref in extract_references(text):
            target_uri = resolve_reference_uri(ref)
            if target_uri and target_uri != source_uri:
                self.add_citation(source_uri, target_uri, ref.raw_text)
    
    def get_valid_citations(self) -> List[Tuple[str, str, str]]:
        """Gibt nur Zitationen zurück, deren Ziel existiert."""
        return [
            (src, tgt, raw)
            for src, tgt, raw in self.citations
            if tgt in self.known_uris
        ]
    
    def generate_triples(self) -> List[str]:
        """Erzeugt eli:cites Triples für alle validen Zitationen."""
        triples = []
        seen = set()  # Deduplizierung
        for src, tgt, _ in self.get_valid_citations():
            key = (src, tgt)
            if key not in seen:
                seen.add(key)
                triples.append(f"<{src}> eli:cites <{tgt}> .")
        return triples
    
    def _extract_label(self, uri: str) -> str:
        """Extrahiert ein lesbares Label ab 'par_' aus der URI."""
        # Suche nach 'par_' im Pfad und nimm alles danach
        if "/par_" in uri:
            idx = uri.index("/par_")
            return uri[idx + 1:]  # +1 um den führenden / zu entfernen
        # Fallback: letztes Segment
        return uri.split("/")[-1]
    
    def export_for_visualization(self) -> Dict:
        """Exportiert die Zitationen für die Visualisierung mit Beschreibungen."""
        valid = self.get_valid_citations()
        nodes = set()
        for src, tgt, _ in valid:
            nodes.add(src)
            nodes.add(tgt)
        
        return {
            "nodes": [
                {
                    "id": uri,
                    "label": self._extract_label(uri),
                    "description": self.descriptions.get(uri, "")
                }
                for uri in sorted(nodes)
            ],
            "links": [
                {"source": src, "target": tgt, "label": raw}
                for src, tgt, raw in valid
            ]
        }


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
    citations: Optional[CitationCollector] = None,
    extract_citations: bool = True,
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
    
    # URI registrieren mit Beschreibung und optional Zitationen extrahieren
    if citations:
        citations.register_uri(uri, description)
        if description and extract_citations:
            citations.extract_and_add(uri, description)


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


def split_sentences(text: str) -> List[str]:
    text = norm_text(text)
    if not text:
        return []

    # Protect common legal abbreviations from sentence splitting.
    dot_token = "<DOT>"
    abbreviations = [
        "Abs.",
        "Nr.",
        "Art.",
        "Buchst.",
        "S.",
        "BGBl.",
        "z.B.",
        "u.a.",
        "bzw.",
        "d.h.",
        "i.V.m.",
    ]

    protected = text
    for abbr in abbreviations:
        protected = protected.replace(abbr, abbr.replace(".", dot_token))

    # Protect dates like "24. Juli 2007" from being split after the day.
    protected = re.sub(
        r"\b([0-3]?\d)\.\s+(Januar|Februar|März|Maerz|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\b",
        lambda m: f"{m.group(1)}{dot_token} {m.group(2)}",
        protected,
        flags=re.IGNORECASE,
    )

    parts = re.split(r"(?<=[.!?])\s+", protected)
    sentences: List[str] = []
    for part in parts:
        restored = part.replace(dot_token, ".").strip()
        if restored:
            sentences.append(restored)
    return sentences


def add_satz_node(
    triples: List[str],
    parent_absatz_uri: str,
    satz_idx_by_absatz: dict[str, int],
    text: str,
    citations: Optional[CitationCollector] = None,
) -> None:
    text = norm_text(text)
    if not text:
        return
    satz_idx_by_absatz[parent_absatz_uri] = (
        satz_idx_by_absatz.get(parent_absatz_uri, 0) + 1
    )
    satz_no = str(satz_idx_by_absatz[parent_absatz_uri])
    satz_uri = f"{parent_absatz_uri}/satz_{slug(satz_no)}"
    make_subdivision(
        triples=triples,
        uri=satz_uri,
        parent_uri=parent_absatz_uri,
        type_name="satz",
        number=satz_no,
        description=text,
        citations=citations,
    )


def ends_with_sentence_punctuation(text: str) -> bool:
    return bool(re.search(r"[.!?]\s*$", norm_text(text)))


def build_graph(root: ET.Element, citations: Optional[CitationCollector] = None) -> List[str]:
    triples: List[str] = []
    if citations is None:
        citations = CitationCollector()
    
    triples.append(
        f"<{BASE_RES}> a eli:LegalResource ;\n"
        '    eli:number "BauO Bln" ;\n'
        '    eli:title "Bauordnung für Berlin (BauO Bln) Stand: 21.01.2026"@de .'
    )
    citations.register_uri(BASE_RES)

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
                part_uri = f"{BASE_RES}/teil_{part_idx}"
                make_subdivision(
                    triples=triples,
                    uri=part_uri,
                    parent_uri=BASE_RES,
                    type_name="teil",
                    number=gbez,
                    title=title,
                    citations=citations,
                )
                current_part = part_uri
                current_section = None
            elif "ABSCHNITT" in upper:
                if not current_part:
                    part_idx += 1
                    current_part = f"{BASE_RES}/teil_{part_idx}"
                    make_subdivision(
                        triples=triples,
                        uri=current_part,
                        parent_uri=BASE_RES,
                        type_name="teil",
                        number=f"Teil-{part_idx}",
                        title=f"Teil {part_idx}",
                        citations=citations,
                    )
                section_idx += 1
                section_uri = f"{current_part}/abschnitt_{section_idx}"
                make_subdivision(
                    triples=triples,
                    uri=section_uri,
                    parent_uri=current_part,
                    type_name="abschnitt",
                    number=gbez,
                    title=title,
                    citations=citations,
                )
                current_section = section_uri
            else:
                part_idx += 1
                other_uri = f"{BASE_RES}/gliederung_{part_idx}-{slug(gbez)}"
                make_subdivision(
                    triples=triples,
                    uri=other_uri,
                    parent_uri=BASE_RES,
                    type_name="gliederung",
                    number=gbez,
                    title=title,
                    citations=citations,
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
            citations=citations,
        )

        current_absatz_uri: Optional[str] = None
        absatz_chunks: dict[str, List[str]] = {}
        satz_idx_by_absatz: dict[str, int] = {}
        satz_chunks: dict[str, List[str]] = {}
        pending_list_prefix_by_absatz: dict[str, str] = {}
        awaiting_list_suffix_by_absatz: dict[str, str] = {}

        children = list(textdaten)
        for idx, child in enumerate(children):
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
                        citations=citations,
                    )
                    current_absatz_uri = absatz_uri
                    absatz_chunks[current_absatz_uri] = []
                    text_body = body
                elif ptxt:
                    if not current_absatz_uri:
                        default_no = "1"
                        current_absatz_uri = f"{par_uri}/abs_{slug(default_no)}"
                        make_subdivision(
                            triples=triples,
                            uri=current_absatz_uri,
                            parent_uri=par_uri,
                            type_name="absatz",
                            number=default_no,
                            citations=citations,
                        )
                        absatz_chunks.setdefault(current_absatz_uri, [])
                    text_body = ptxt
                else:
                    continue

                target_absatz_uri = current_absatz_uri
                absatz_chunks.setdefault(target_absatz_uri, []).append(text_body)

                sentences = split_sentences(text_body)

                # If the previous list opened a sentence, append the first fitting fragment here.
                awaited_satz_uri = awaiting_list_suffix_by_absatz.get(target_absatz_uri)
                if awaited_satz_uri and sentences:
                    first = sentences[0]
                    if re.match(r"^[a-zäöüß]", first):
                        satz_chunks.setdefault(awaited_satz_uri, []).append(first)
                        sentences = sentences[1:]
                        awaiting_list_suffix_by_absatz.pop(target_absatz_uri, None)

                next_is_dl = idx + 1 < len(children) and children[idx + 1].tag == "dl"
                if next_is_dl and sentences and not ends_with_sentence_punctuation(text_body):
                    for sentence in sentences[:-1]:
                        add_satz_node(
                            triples=triples,
                            parent_absatz_uri=target_absatz_uri,
                            satz_idx_by_absatz=satz_idx_by_absatz,
                            text=sentence,
                            citations=citations,
                        )
                    pending_list_prefix_by_absatz[target_absatz_uri] = sentences[-1]
                else:
                    for sentence in sentences:
                        add_satz_node(
                            triples=triples,
                            parent_absatz_uri=target_absatz_uri,
                            satz_idx_by_absatz=satz_idx_by_absatz,
                            text=sentence,
                            citations=citations,
                        )

            elif child.tag == "dl":
                if not current_absatz_uri:
                    default_no = "1"
                    current_absatz_uri = f"{par_uri}/abs_{slug(default_no)}"
                    make_subdivision(
                        triples=triples,
                        uri=current_absatz_uri,
                        parent_uri=par_uri,
                        type_name="absatz",
                        number=default_no,
                        citations=citations,
                    )
                    absatz_chunks.setdefault(current_absatz_uri, [])

                target_absatz_uri = current_absatz_uri
                satz_idx_by_absatz[target_absatz_uri] = (
                    satz_idx_by_absatz.get(target_absatz_uri, 0) + 1
                )
                satz_no = str(satz_idx_by_absatz[target_absatz_uri])
                satz_uri = f"{target_absatz_uri}/satz_{slug(satz_no)}"
                
                pending_prefix = pending_list_prefix_by_absatz.pop(target_absatz_uri, "")
                
                # Satz-Knoten erstellen (description wird später mit vollem Text gesetzt)
                make_subdivision(
                    triples=triples,
                    uri=satz_uri,
                    parent_uri=target_absatz_uri,
                    type_name="satz",
                    number=satz_no,
                    citations=citations,
                    extract_citations=False,  # Zitationen werden unten separat behandelt
                )
                satz_chunks.setdefault(satz_uri, [])
                
                # Zitationen nur aus dem Einleitungstext extrahieren, nicht aus den Nummern
                if pending_prefix:
                    satz_chunks[satz_uri].append(pending_prefix)
                    if citations:
                        citations.extract_and_add(satz_uri, pending_prefix)

                for num, body in parse_list_items(child):
                    num_uri = f"{satz_uri}/nr_{slug(num)}"
                    make_subdivision(
                        triples=triples,
                        uri=num_uri,
                        parent_uri=satz_uri,
                        type_name="nummer",
                        number=num,
                        description=body if body else None,
                        citations=citations,
                    )
                    satz_chunks.setdefault(satz_uri, []).append(f"{num}. {body}")
                    absatz_chunks.setdefault(target_absatz_uri, []).append(
                        f"{num}. {body}"
                    )

                if pending_prefix:
                    awaiting_list_suffix_by_absatz[target_absatz_uri] = satz_uri

        # Nach dem Sammeln aller Chunks: Beschreibungen hinzufügen
        # WICHTIG: Zitationen werden NICHT aus zusammengesetzten Beschreibungen extrahiert,
        # da diese bereits auf der tiefsten Ebene (add_satz_node, nummer) erfasst wurden.
        # Das vermeidet doppelte Zitationen auf Absatz/Satz-Ebene.
        for satz_uri, chunks in satz_chunks.items():
            full_text = "\n".join(chunk for chunk in chunks if chunk).strip()
            if full_text:
                triples.append(
                    f'<{satz_uri}> eli:description "{escape_ttl(full_text)}"@de .'
                )
                if citations:
                    # Nur registrieren, KEINE Zitationen extrahieren (bereits auf Nummer-Ebene erfasst)
                    citations.register_uri(satz_uri, full_text)

        for absatz_uri, chunks in absatz_chunks.items():
            full_text = "\n".join(chunk for chunk in chunks if chunk).strip()
            if full_text:
                triples.append(
                    f'<{absatz_uri}> eli:description "{escape_ttl(full_text)}"@de .'
                )
                if citations:
                    # Nur registrieren, KEINE Zitationen extrahieren (bereits auf Satz/Nummer-Ebene erfasst)
                    citations.register_uri(absatz_uri, full_text)

    triples.append(
        f"<{BASE_RES}> eli:description "
        f"\"Automatisch aus content.xml erzeugte Struktur mit {paragraph_count} Paragraphen.\"@de ."
    )
    return triples, citations


def write_ttl(path: Path, triples: List[str]) -> None:
    header = "\n".join(
        [
            "@prefix owl:     <http://www.w3.org/2002/07/owl#> .",
            "@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .",
            "@prefix rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .",
            "@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .",
            "@prefix eli:     <http://data.europa.eu/eli/ontology#> .",
            "@prefix dcterms: <http://purl.org/dc/terms/> .",
            "@prefix bauobln: <https://example.org/eli/de/be/bauo/2005/> .",
            "@prefix exvocab: <https://example.org/vocab/subdivision/> .",
            "@prefix skos:    <http://www.w3.org/2004/02/skos/core#> .",
            "",
            "<https://example.org/eli/de/be/bauo/data>",
            "    a owl:Ontology ;",
            "    owl:imports <http://data.europa.eu/eli/ontology> ;",
            '    dcterms:title "BauO Berlin 2005 Instanzdaten (ABox)"@de ;',
            '    dcterms:description "ELI-konforme ABox-Daten zur Berliner Bauordnung Stand: 21.01.2026"@de .',
            "",
            "",
        ]
    )
    body = "\n\n".join(triples) + "\n"
    path.write_text(header + body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="./BauO_BE_2005/content.xml", help="Pfad zur content.xml")
    parser.add_argument(
        "--output",
        default="./BauO_BE_2005/bauo_be_2005_eli.ttl",
        help="Zieldatei für Turtle-Ausgabe",
    )
    parser.add_argument(
        "--citations-json",
        default="./BauO_BE_2005/citations.json",
        help="JSON-Datei für Querverweis-Visualisierung",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    citations_json_path = Path(args.citations_json).resolve()

    root = read_xml_without_doctype(input_path)
    citations = CitationCollector()
    triples, citations = build_graph(root, citations)
    
    # eli:cites Triples hinzufügen
    cites_triples = citations.generate_triples()
    triples.extend(cites_triples)
    
    write_ttl(output_path, triples)
    print(f"OK: {output_path}")
    print(f"    {len(citations.known_uris)} URIs registriert")
    print(f"    {len(citations.citations)} Zitationen erkannt")
    print(f"    {len(cites_triples)} eli:cites Triples erzeugt (valide Ziele)")
    
    # JSON für Visualisierung exportieren
    viz_data = citations.export_for_visualization()
    citations_json_path.write_text(json.dumps(viz_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK: {citations_json_path}")


if __name__ == "__main__":
    main()
