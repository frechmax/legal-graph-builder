# BauO Berlin - Querverweise Visualisierung

Interaktive Force-Directed Graph Visualisierung der internen Querverweise (`eli:cites`) 
in der Berliner Bauordnung.

## Starten

```bash
cd BauO_BE_2005/citations_viz
python -m http.server 8080
# Browser öffnen: http://localhost:8080
```

## Features

- **Force-Directed Layout**: Knoten werden physikalisch simuliert
- **Filter nach §**: Fokus auf einen bestimmten Paragraphen und dessen Verweise
- **Abstoßungs-Slider**: Anpassung der Knotenabstoßung
- **Zoom & Pan**: Mausrad und Drag für Navigation
- **Knoten-Details**: Klick auf Knoten zeigt eingehende/ausgehende Verweise
- **Farbcodierung**:
  - 🟠 Orange: Nur ausgehende Verweise (Quelle)
  - 🟣 Lila: Nur eingehende Verweise (Ziel)  
  - 🟢 Grün: Sowohl ein- als auch ausgehende Verweise

## Datenquelle

Die Daten werden aus `../citations.json` geladen, die vom Skript 
`convert_to_eli_rdf.py` erzeugt wird.

## Statistik (aktueller Stand)

- **610 eli:cites Triples** zwischen internen Rechtstextstellen
- Verweise werden auf Ebene von Sätzen, Absätzen und Nummern erkannt
