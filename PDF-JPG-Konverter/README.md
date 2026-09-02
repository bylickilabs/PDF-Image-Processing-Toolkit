# PDF zu JPG Konverter

> Desktop-Anwendung zum Konvertieren kompletter PDF-Dokumente in einzelne JPG-Dateien.

## Kernfunktion

Aus **jeder Seite einer PDF wird exakt eine JPG-Datei**.

Standardausgabe:

```text
PDF_JPG_Export/
└── Mein_Dokument/
    ├── Seite_0001.jpg
    ├── Seite_0002.jpg
    ├── Seite_0003.jpg
    └── ...
```

> Bei mehreren PDFs wird standardmäßig für jedes Dokument ein eigener Unterordner angelegt. 
  - Dadurch können Seiten verschiedener Dokumente nicht versehentlich vermischt werden.

## Funktionen

- Eine oder mehrere PDF-Dateien gleichzeitig laden
- PDF-Dateien per Drag & Drop hinzufügen
- Eine JPG-Datei pro PDF-Seite
- Automatische vierstellige Seitennummerierung
- Frei wählbarer Startwert
- Optional fortlaufende Nummerierung über mehrere PDFs
- Eigener Ausgabeordner pro PDF
- Alternativ gemeinsame Ausgabe mit PDF-Namen im JPG-Dateinamen
- Auflösung: 150 , 200 , 300 , 400 oder 600 DPI
- Einstellbare JPG-Qualität von 1 bis 100
- Unterstützung passwortgeschützter PDFs über ein optionales Passwortfeld
- Schutz vor unbeabsichtigtem Überschreiben
- Fortschrittsanzeige
- Live-Protokoll
- Abbruch einer laufenden Verarbeitung
- Deutsche Benutzeroberfläche

## Empfohlene Einstellung

Für hochwertige Seitenbilder:

```text
DPI:         300
JPG-Qualität: 95
```

## Installation unter Windows

Voraussetzung:

- Python 3.11 oder neuer empfohlen

Anschließend einfach:

```text
start.bat
```

Die Batch-Datei erstellt automatisch eine virtuelle Python-Umgebung und installiert die benötigten Pakete.

Alternativ manuell:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## Abhängigkeiten

- PySide6
- PyMuPDF

> Es ist keine separate Poppler-Installation erforderlich.

## Dateinummerierung

> Bei der Standardkonfiguration startet jedes PDF bei:

```text
Seite_0001.jpg
```

und wird lückenlos fortgesetzt:

```text
Seite_0002.jpg
Seite_0003.jpg
Seite_0004.jpg
...
```

Die Option **Nummerierung über alle geladenen PDFs fortlaufend weiterführen** ermöglicht stattdessen beispielsweise:

```text
PDF 1:
Seite_0001.jpg
Seite_0002.jpg

PDF 2:
Seite_0003.jpg
Seite_0004.jpg
```

## Version

```text
v1.0.0
```
