# Image Metadata Inspector

**Version:** 1.0.0  
**Typ:** Python Desktop-Anwendung  
**Ziel:** möglichst umfassende, lokale Analyse von Metadaten in Bilddateien

## Funktionen

> Die Anwendung analysiert Bilddateien lokal und verändert die Originaldateien nicht.

### Interner Metadaten-Scanner

- Dateiname, Pfad, Dateigröße und Zeitstempel
- MIME-Typ und Dateiendung
- MD5, SHA-1, SHA-256 und SHA-512
- Bildformat, Farbraum/Modus, Abmessungen, Seitenverhältnis und Frames
- EXIF inklusive verschachtelter IFDs
- GPS-Metadaten inklusive Dezimal-Koordinaten, sofern vorhanden
- IPTC
- XMP/XML-Pakete
- ICC-Farbprofile
- PNG-Text-Chunks und Kommentare
- Pillow-spezifische Containerinformationen

### C2PA / Content Credentials

> Wenn `c2pa-python` installiert ist, versucht die Anwendung vorhandene C2PA-Manifeste auszulesen und zu validieren. Angezeigt werden unter anderem:

- Vorhandensein eines C2PA-Manifests
- aktives Manifest
- Manifest Store
- eingebetteter oder externer Manifest-Status
- Remote-URL, sofern vorhanden
- Validierungsstatus und Validierungsergebnisse, sofern vom SDK geliefert
- detaillierte Manifestdaten, sofern verfügbar

> Die Anwendung erstellt oder verändert keine C2PA-Manifeste. Sie arbeitet in diesem Projekt ausschließlich lesend.

### Optionaler ExifTool Deep-Scan

> Wenn ExifTool installiert ist, wird es zusätzlich mit `-G0:1:2 -a -u -s -struct` aufgerufen. 
  - Dadurch können deutlich mehr hersteller-, kamera-, software- und formatspezifische Metadaten sichtbar werden.

ExifTool kann entweder:

1. über `PATH` erreichbar sein,
2. als `exiftool.exe` neben der Anwendung liegen,
3. unter `tools/exiftool.exe` liegen oder
4. direkt in der Oberfläche ausgewählt werden.

## Unterstützte Bildtypen

> Die Dateiauswahl umfasst unter anderem:

- JPEG / JPG / JFIF
- PNG
- WebP
- TIFF
- BMP
- GIF
- ICO
- PCX
- PPM / PGM / PBM
- AVIF
- HEIC / HEIF
- JPEG XL (`.jxl`)

> Welche Formate tatsächlich intern dekodiert werden können, hängt zusätzlich von der installierten Pillow-Version und deren Codecs ab. 
  - HEIC/HEIF-Unterstützung wird über `pillow-heif` ergänzt. 
  - ExifTool kann auch dann zusätzliche Metadaten liefern, wenn Pillow ein Format nicht dekodieren kann.

## Installation unter Windows

### Vollversion inklusive C2PA

Doppelklick auf:

```text
start.bat
```

> Dabei wird automatisch eine virtuelle Python-Umgebung erstellt und `requirements.txt` installiert.

### Minimalversion

Falls nur der interne Scanner benötigt wird:

```text
start_minimal.bat
```

C2PA ist in dieser Variante nicht installiert. ExifTool kann trotzdem separat verwendet werden.

## Manueller Start

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python app.py
```

## Export

Ergebnisse lassen sich exportieren als:

- JSON – vollständige hierarchische Struktur
- CSV – flach aufbereitete Metadatenpfade

## Datenschutz

> Die interne Analyse erfolgt lokal. 
  - Für C2PA ist der Reader so konfiguriert, dass Remote-Manifest- und OCSP-Abrufe deaktiviert sind. 
    - ExifTool wird lokal als separater Prozess ausgeführt.

## Technischer Hinweis

> Es gibt kein einzelnes Python-Modul, das garantiert jedes proprietäre Metadatenfeld jedes jemals existierenden Bildformats versteht. 
  - Deshalb kombiniert dieses Projekt mehrere Analyseebenen. Für maximale Abdeckung ist der optionale ExifTool Deep-Scan vorgesehen.
