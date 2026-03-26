# Radial Tidy Tree (D3.js)

Visualisiert die hierarchische Struktur aus einer ELI-Turtle-Datei als radialen Baum:

Teil -> Abschnitt -> Paragraph -> Absatz -> Satz -> Nummer

## 1) JSON aus TTL erzeugen

Im Projekt-Root ausfuehren:

```bash
python radial_tidy_tree/build_radial_tree_data.py --input BauO_BE_2005/bauo_be_2005_eli.ttl --output radial_tidy_tree/bauo_be_2005_tree.json
```

## 2) Lokalen Webserver starten

Im Projekt-Root ausfuehren:

```bash
python -m http.server 8000
```

Dann im Browser oeffnen:

http://localhost:8000/radial_tidy_tree/

## Hinweise

- Die Darstellung nutzt D3 v7 via CDN.
- Die Datenquelle ist in `index.html` als Auswahl vorbelegt (`bauo_be_2005_tree.json`).
