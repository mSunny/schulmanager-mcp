# Schulmanager Online MCP Server

Ein lokaler [MCP](https://modelcontextprotocol.io/)-Server (Model Context Protocol) für den Zugriff auf [Schulmanager Online](https://schulmanager-online.de/) Daten. Ermöglicht LLMs wie Claude den direkten Zugriff auf Stundenplan, Hausaufgaben, Prüfungen, Noten, Elternbriefe und mehr.

> **Hinweis:** Dies ist ein inoffizielles Community-Projekt. Es besteht keine Verbindung zu Schulmanager Online GmbH. Nutzung auf eigene Verantwortung.

## Features

| Tool | Beschreibung |
|------|-------------|
| `schulmanager_get_students` | Alle Kinder/Schüler des Accounts auflisten |
| `schulmanager_get_schedule` | Stundenplan abrufen (Zeitraum wählbar) |
| `schulmanager_get_homework` | Aktuelle Hausaufgaben |
| `schulmanager_get_exams` | Anstehende Prüfungen und Klassenarbeiten |
| `schulmanager_get_grades` | Noten pro Fach (sofern von der Schule freigeschaltet) |
| `schulmanager_get_letters` | Elternbriefe und Benachrichtigungen |
| `schulmanager_get_institution` | Schulinformationen |
| `schulmanager_raw_call` | Beliebiger API-Aufruf für nicht abgedeckte Endpunkte |

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
> Welche Hausaufgaben hat mein Kind?
> Zeig mir den Stundenplan fuer naechste Woche
> Welche Klassenarbeiten stehen in den naechsten 4 Wochen an?
> Gibt es neue Elternbriefe?
> Was steht morgen auf dem Stundenplan?
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
