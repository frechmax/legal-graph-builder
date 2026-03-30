# Parsing Summary — convert_to_eli_rdf.py

This document summarizes how text is parsed by the script [BauO_BE_2005/convert_to_eli_rdf.py](BauO_BE_2005/convert_to_eli_rdf.py).

## Overview
- Purpose: convert `content.xml` into an ELI-conformant Turtle file with hierarchical subdivisions (Teil/Abschnitt/§/Absatz/Satz/Nummer).
- Main entry points:
  - `read_xml_without_doctype()` — read and strip DOCTYPE
  - `build_graph()` — orchestration that walks XML, creates subdivision nodes and text nodes
  - `write_ttl()` — writes Turtle output

## Input / Output
- Input: XML file with repeated `<norm>` elements containing `<metadaten>` and `<textdaten>`.
- Output: Turtle triples describing `eli:LegalResource` and hierarchical `eli:LegalResourceSubdivision` nodes.

## High-level parsing flow (in `build_graph`)
1. Iterate over each `<norm>` (via `iter_norms`).
2. Read metadata: `enbez` (enumeration label, e.g. "§ 1") and `gliederungseinheit` (`gliederungsbez`, `gliederungstitel`).
3. If `gliederungsbez` exists and `enbez` is empty: treat as structural division (Teil / Abschnitt / generic gliederung):
   - If `gliederungsbez` contains "TEIL" → create `teil` node and reset section index.
   - If contains "ABSCHNITT" → create `abschnitt` under current `teil` (create `teil` first if missing).
   - Otherwise create a `gliederung` node under base resource.
4. If `enbez` starts with `§` → process as a paragraph (legal paragraph node):
   - Create `paragraph` subdivision node under current section/part/base.
   - Parse its `<textdaten>` children to create `absatz`, `satz`, and `nummer` subdivisions and descriptions.

## XML and text normalization helpers
- `read_xml_without_doctype(path)`: removes inline DOCTYPE sections using a regex before parsing with ElementTree.
- `norm_text(value)`: collapse whitespace and trim.
- `slug(value)`: lowercases, replaces German chars (`ä`→`ae`, `ß`→`ss`, `§`→`par`), removes non-alphanumerics and replaces with `-`. Falls back to `node`.
- `escape_ttl(value)`: escapes backslashes, quotes and newlines for Turtle literals.

## Key parsing helpers
- `first_text(elem, tag)`: returns normalized text content of first child `tag`, or empty string.
- `iter_norms(root)`: yields all `<norm>` children of the document root.
- `make_subdivision(...)`: central helper that appends Turtle triples for a subdivision and links parent ↔ child using `eli:is_part_of` and `eli:has_part`. Also adds `eli:title` and `eli:description` when present.

## Paragraph / Absatz / Satz / Nummer parsing details
- Paragraph detection:
  - `enbez` must start with `§` to be considered a paragraph.
  - `par_no` is `enbez` with `§` removed.
  - Parent for a `paragraph` node is `current_section` or `current_part` or the base resource.

- Absatz (`p` tags):
  - `parse_absatz(text)` detects leading numbered absatz forms of the form `(1)` or `(1a)` using regex `^\((\d+[a-z]?)\)\s*(.*)$`.
  - If an explicit absatz number is found, a new `absatz` node is created with that number. Otherwise text without number is appended to the current absatz (or a default `1` is created if none exists yet).

- Sentence splitting (`split_sentences`):
  - Normalizes whitespace and returns sentence fragments split by `(?<=[.!?])\s+`.
  - Protects common legal abbreviations by temporarily replacing `.` with a token `<DOT>` so abbreviations like `Abs.` / `Nr.` / `Art.` / `z.B.` / `i.V.m.` don't cause wrong splits.
  - Abbreviations list: `Abs.`, `Nr.`, `Art.`, `Buchst.`, `S.`, `z.B.`, `u.a.`, `bzw.`, `d.h.`, `i.V.m.`

- Satz creation and numbering:
  - `add_satz_node(triples, parent_absatz_uri, satz_idx_by_absatz, text)` increments a per-absatz counter, builds a `satz` URI `.../satz_<slug(n)>`, and stores the satz as a `LegalResourceSubdivision` with `eli:number` and `eli:description`.
  - `satz_idx_by_absatz` tracks numbering per-absatz.

- Lists (`dl` / `dt` / `dd`):
  - `parse_list_items(dl)` pairs `dt` (number/label) with following `dd` bodies and returns `(num, body)` list.
  - When a `dl` follows a paragraph whose final fragment does not end with sentence punctuation, the code treats the last sentence fragment as a prefix for the upcoming `dl` entries (stored via `pending_list_prefix_by_absatz`).
  - For each `dl`:
    - A new `satz` node is created (it increments the satz counter for the current absatz and uses that satz as parent for `nummer` entries).
    - For each `(num, body)` a `nummer` node is created under that `satz` with `eli:number` and optional `eli:description`.
    - The `nummer` content is appended to both the `satz` chunks and the parent `absatz` chunks (so descriptions include list items).
  - If a `pending_prefix` exists, it is prepended to the first `satz`'s text; if the list's suffix continues the pending sentence, `awaiting_list_suffix_by_absatz` links that later.

## Chunk accumulation and finalization
- `absatz_chunks` and `satz_chunks` collect fragments while traversing children. After processing a paragraph, the code joins chunks with `\n` and writes them as `eli:description` triples for `absatz` and each `satz`.

## Sentence punctuation helper
- `ends_with_sentence_punctuation(text)`: tests whether normalized text ends with `.`, `!` or `?` using `re.search(r"[.!?]\s*$")`.

## URI and numbering conventions
- Base resource: `BASE_RES = https://example.org/eli/de/be/bauo/2005`.
- Typical URIs produced:
  - Part: `.../teil/<n>`
  - Section: `.../teil/<n>/abschnitt/<m>`
  - Paragraph: `.../par_<slug(par_no)>` (e.g. `par_1` or `par_1-1`)
  - Absatz: `<par_uri>/abs_<slug(no)>`
  - Satz: `<absatz_uri>/satz_<slug(n)>`
  - Nummer: `<satz_uri>/nr_<slug(num)>`

## Regular expressions and patterns used
- DOCTYPE removal: `<!DOCTYPE[^>]*\[[\s\S]*?\]>` (single match removed before XML parse).
- Absatz detection: `^\((\d+[a-z]?)\)\s*(.*)$` (case-insensitive).
- Sentence split: `(?<=[.!?])\s+` with abbreviation protection using `<DOT>` placeholder.
- Slug normalization: `re.sub(r"[^a-z0-9]+", "-", s)` after char replacements.

## Turtle output
- `write_ttl()` writes a header with useful prefixes and an ontology block, then writes the accumulated triples (one paragraph/absatz/satz/nummer triple block per subdivision).

## Edge cases, assumptions and heuristics
- If a `gliederungsbez` like an `ABSCHNITT` appears without an existing `teil`, the code pre-creates a `teil` placeholder.
- When paragraphs contain plain text without explicit `(1)` markers, the script creates a default `absatz` numbered `1`.
- List handling uses heuristics when the trailing fragment of a paragraph forms a prefix for a list; the code carries prefixes across into the first `satz` created for that list.
- The abbreviation list is static and may need extension for other abbreviations in different documents.
- The script expects relatively well-formed HTML-like XML with `p`, `dl`, `dt`, `dd` elements inside `textdaten`.

## Notable functions (one-line)
- `read_xml_without_doctype(path)` — read and strip problematic DOCTYPE sections.
- `norm_text(value)` — collapse whitespace.
- `slug(value)` — build filesystem/URI-safe slug from text.
- `parse_absatz(text)` — detect `(n)`-style absatz numbers and extract body.
- `split_sentences(text)` — split into sentences while protecting known abbreviations.
- `parse_list_items(dl)` — extract `(num, body)` pairs from a `dl` element.
- `add_satz_node(...)` — create and number `satz` nodes under an `absatz`.

## Where to look in code
- Main driver and orchestration: [BauO_BE_2005/convert_to_eli_rdf.py](BauO_BE_2005/convert_to_eli_rdf.py)

## Suggested improvements (optional)
- Expand abbreviation list or make it configurable.
- Add unit tests for `split_sentences`, `parse_absatz`, and `parse_list_items`.
- Consider more robust HTML parsing (e.g., use lxml) if content is irregular.

---
Generated from static analysis of the script on 2026-03-30.
