# Schulmanager Online MCP Server

Ein lokaler [MCP](https://modelcontextprotocol.io/)-Server (Model Context Protocol) für den Zugriff auf [Schulmanager Online](https://schulmanager-online.de/) Daten. Ermöglicht LLMs wie Claude den direkten Zugriff auf Stundenplan, Hausaufgaben, Prüfungen, Noten, Elternbriefe und mehr.

> **Hinweis:** Dies ist ein inoffizielles Community-Projekt. Es besteht keine Verbindung zu Schulmanager Online GmbH. Nutzung auf eigene Verantwortung.

## Features

| Tool | Beschreibung |
|------|-------------|
| `schulmanager_daily_report` | **Eltern-Briefing**: Komplettueberblick pro Kind -- neue Nachrichten, Stundenplan morgen, Klassenarbeiten (7 Tage), Hausaufgaben (7 Tage) |
| `schulmanager_get_students` | Alle Kinder/Schueler des Accounts auflisten |
| `schulmanager_get_schedule` | Stundenplan abrufen (Zeitraum waehlbar) |
| `schulmanager_get_homework` | Aktuelle Hausaufgaben |
| `schulmanager_get_exams` | Anstehende Pruefungen und Klassenarbeiten |
| `schulmanager_get_grades` | Noten pro Fach (sofern von der Schule freigeschaltet) |
| `schulmanager_get_letters` | Elternbriefe und Benachrichtigungen |
| `schulmanager_get_institution` | Schulinformationen |
| `schulmanager_raw_call` | Beliebiger API-Aufruf fuer nicht abgedeckte Endpunkte |

## Voraussetzungen

- Python 3.11+
- Ein Eltern- oder Schüler-Account bei [Schulmanager Online](https://login.schulmanager-online.de/)

## Installation

```bash
git clone https://github.com/kohlsalem/schulmanager-mcp.git
cd schulmanager-mcp

python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Konfiguration

### 1. Zugangsdaten hinterlegen

```bash
cp .env.example .env
```

Bearbeite `.env` mit deinen Schulmanager-Zugangsdaten:

```
SCHULMANAGER_EMAIL=deine-email@example.com
SCHULMANAGER_PASSWORD=dein-passwort
```

### 2. Claude Code einrichten

Füge folgendes in deine Claude Code Projekt-Settings (`.claude/settings.json`) oder globale Settings (`~/.claude/settings.json`) ein:

```json
{
  "mcpServers": {
    "schulmanager": {
      "command": "/absoluter/pfad/zu/schulmanager-mcp/start.sh",
      "args": []
    }
  }
}
```

Alternativ kannst du die Credentials direkt als Umgebungsvariablen setzen (ohne `.env`-Datei):

```json
{
  "mcpServers": {
    "schulmanager": {
      "command": "/absoluter/pfad/zu/schulmanager-mcp/.venv/bin/python",
      "args": ["-m", "schulmanager_mcp.server"],
      "env": {
        "SCHULMANAGER_EMAIL": "deine-email@example.com",
        "SCHULMANAGER_PASSWORD": "dein-passwort"
      }
    }
  }
}
```

## Nutzung

Starte Claude Code im Projektverzeichnis (oder jedem Verzeichnis mit passender MCP-Konfiguration) und frage einfach:

```
> Gib mir das Eltern-Briefing
> Welche Hausaufgaben hat mein Kind?
> Zeig mir den Stundenplan fuer naechste Woche
> Welche Klassenarbeiten stehen in den naechsten 4 Wochen an?
> Gibt es neue Elternbriefe?
> Was steht morgen auf dem Stundenplan?
```

### Standalone Daily Report

Das Eltern-Briefing kann auch ohne MCP direkt im Terminal ausgegeben werden:

```bash
./daily_report.sh
```

### Beispiel-Report

```markdown
# Eltern-Briefing (20.03.2026)

## Max Mustermann

### Auf einen Blick
- **1 ungelesene Nachricht** -- "Elternabend am 25.03."
- Stundenplan Mo: **1. Stunde faellt aus** (Deutsch), danach Englisch, Musik, Kunst
- **2 Arbeiten diese Woche** -- Di Englisch (Klassenarbeit), Mi Mathe (Klassenarbeit)
- Hausaufgaben fuer Mo: Englisch (+2 weitere diese Woche)

### Neue Nachrichten (1)
- **Elternabend am 25.03.** (2026-03-18)
  https://login.schulmanager-online.de/#/modules/letters/view/12345

### Stundenplan Mo 23.03.2026
- **1. Stunde**: ~~Deutsch~~ -- Entfall
- **2. Stunde**: Englisch (Mueller), Raum 201
- **3. Stunde**: Englisch (Mueller), Raum 201
- **4. Stunde**: Musik (Schmidt), Raum 110
- **5. Stunde**: Kunst (Schmidt), Raum 215

### Klassenarbeiten & Tests (naechste 7 Tage)
- **2026-03-24**: Englisch (Klassenarbeit)
- **2026-03-25**: Mathematik (Klassenarbeit) -- "Lineare Funktionen"

### Hausaufgaben (naechste 7 Tage)
- **Mo 23.03. Englisch**: Workbook S. 45, Nr. 3-5
- **Mi 25.03. Deutsch**: Aufsatz zu Ende schreiben
- **Do 26.03. Mathematik**: Aufgabenblatt Funktionen
```

## Technische Details

### Authentifizierung

Der Server nutzt die inoffizielle Schulmanager-Online-API:

1. **Salt abrufen** via `POST /api/get-salt`
2. **Passwort hashen** mit PBKDF2-SHA512 (99.999 Iterationen, 512 Byte Output)
3. **Login** via `POST /api/login` -- liefert ein JWT-Token
4. **Daten abrufen** via `POST /api/calls` mit Bearer-Token

### API-Endpunkte

Alle Datenabfragen laufen ueber den zentralen `/api/calls`-Endpunkt als Batch-Requests:

| Modul | Endpunkt | Beschreibung |
|-------|----------|-------------|
| `schedules` | `get-actual-lessons` | Stundenplan mit Vertretungen |
| `classbook` | `get-homework` | Hausaufgaben |
| `exams` | `get-exams` | Klassenarbeiten & Tests |
| `grades` | `get-grades` | Noten |
| `letters` | `get-letters` | Elternbriefe |
| `main` | `get-institution` | Schulinformationen |

Ueber das `schulmanager_raw_call`-Tool koennen beliebige weitere Endpunkte angesprochen werden.

## Danksagung

Die API-Struktur wurde durch Analyse bestehender Open-Source-Projekte ermittelt, insbesondere:

- [rwunsch/schulmanager-online-hass](https://github.com/rwunsch/schulmanager-online-hass) -- Home Assistant Integration
- [SchmueI/Schulmanager-API](https://github.com/SchmueI/Schulmanager-API) -- Python Scraping-Client

## Lizenz

Dieses Projekt steht unter der [Unlicense](LICENSE) -- gemeinfrei, ohne jede Gewaehr.
