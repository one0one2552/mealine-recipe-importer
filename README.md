# 🍳 Mealie Recipe Importer

Eine Webanwendung zum automatischen Importieren von Rezepten aus **PDFs** und **Videos** in [Mealie](https://mealie.io/) mittels **Google Gemini KI**.

![Python](https://img.shields.io/badge/Python-3.12+-blue)
![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## ✨ Features

- 📄 **PDF Import** - Extrahiert Rezepte aus PDF-Dokumenten
- 📹 **Video Import** - Analysiert Rezept-Videos (max. 2 Min empfohlen)
- 🤖 **KI-Analyse** - Nutzt Google Gemini für intelligente Extraktion
- 🇩🇪 **Deutsche Übersetzung** - Videos werden automatisch auf Deutsch übersetzt
- 📊 **1-Portion-Umrechnung** - Alle Mengen werden auf 1 Portion normalisiert
- 🥕 **Strukturierte Zutaten** - Anzahl, Einheit und Lebensmittel werden separat erfasst
- 🔄 **Auto-Erstellung** - Fehlende Einheiten und Lebensmittel werden in Mealie angelegt

## 📋 Voraussetzungen

- [Mealie](https://mealie.io/) Installation mit API-Zugang
- [Google Gemini API Key](https://aistudio.google.com/apikey) (kostenlos)
- Docker & Docker Compose (für Container-Installation)
- Oder: Python 3.12+

## 🚀 Installation

### Option 1: Docker (Empfohlen)

1. **Repository klonen**
   ```bash
   git clone https://github.com/yourusername/mealie-recipe-importer.git
   cd mealie-recipe-importer
   ```

2. **Umgebungsvariablen konfigurieren**
   ```bash
   cp .env.example .env
   nano .env  # oder Editor deiner Wahl
   ```

3. **Container starten**
   ```bash
   docker-compose up -d
   ```

4. **Öffne im Browser**
   ```
   http://localhost:8501
   ```

### Option 2: Lokale Installation

1. **Repository klonen**
   ```bash
   git clone https://github.com/yourusername/mealie-recipe-importer.git
   cd mealie-recipe-importer
   ```

2. **Virtual Environment erstellen**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # oder: venv\Scripts\activate  # Windows
   ```

3. **Dependencies installieren**
   ```bash
   pip install -r requirements.txt
   ```

4. **Umgebungsvariablen setzen**
   ```bash
   cp .env.example .env
   # Bearbeite .env mit deinen Werten
   ```

5. **Anwendung starten**
   ```bash
   streamlit run app.py
   ```

## ⚙️ Konfiguration

### Umgebungsvariablen

| Variable | Beschreibung | Pflicht | Default |
|----------|--------------|---------|---------|
| `MEALIE_URL` | URL zu deiner Mealie-Instanz | ✅ | `http://localhost:9000` |
| `MEALIE_API_TOKEN` | API Token aus Mealie | ✅ | - |
| `MEALIE_TIMEOUT` | Timeout für API-Anfragen (Sekunden) | ❌ | `30` |
| `GEMINI_API_KEY` | Google Gemini API Key | ✅ | - |
| `GEMINI_MODEL` | Standard KI-Modell | ❌ | `gemini-2.5-flash` |

### Mealie API Token erstellen

1. Öffne Mealie → Einstellungen → API Tokens
2. Klicke auf "Token erstellen"
3. Kopiere den Token in deine `.env` Datei

### Gemini API Key erstellen

1. Gehe zu [Google AI Studio](https://aistudio.google.com/apikey)
2. Erstelle einen neuen API Key
3. Kopiere den Key in deine `.env` Datei

## 📖 Verwendung

### PDF Import

1. Wähle den Tab "📄 PDF"
2. Lade ein PDF mit einem Rezept hoch
3. Die KI extrahiert automatisch:
   - Rezeptname und Beschreibung
   - Zutaten (aufgeteilt in Menge, Einheit, Lebensmittel)
   - Zubereitungsschritte
4. Prüfe die Vorschau
5. Klicke auf "🚀 In Mealie speichern"

### Video Import

1. Wähle den Tab "📹 Video"
2. Lade ein Rezept-Video hoch (max. 2 Min empfohlen)
3. Das Video wird zu Google hochgeladen und analysiert
4. Die KI extrahiert das Rezept auf Deutsch
5. Prüfe die Vorschau
6. Klicke auf "🚀 In Mealie speichern"

### Modell wechseln

Bei Quota-Fehlern oder Überlastung:
1. Öffne die Sidebar (⚙️ Einstellungen)
2. Wähle ein anderes KI-Modell
3. Klicke auf "🔄 Neu analysieren"

## 🏗️ Projektstruktur

```
mealie-recipe-importer/
├── app.py                 # Streamlit Hauptanwendung
├── src/
│   ├── __init__.py
│   ├── config.py          # Konfigurationsmanagement
│   ├── gemini_client.py   # Google Gemini API Client
│   ├── mealie_client.py   # Mealie API Client
│   └── pdf_processor.py   # PDF Text-Extraktion
├── requirements.txt       # Python Dependencies
├── Dockerfile            # Container-Definition
├── docker-compose.yml    # Container-Orchestrierung
├── .env.example          # Beispiel-Konfiguration
├── .gitignore
└── README.md
```

## 🔧 Entwicklung

### Lokale Entwicklung

```bash
# Virtual Environment aktivieren
source venv/bin/activate

# Anwendung mit Auto-Reload starten
streamlit run app.py

# Tests ausführen (wenn vorhanden)
pytest tests/
```

### Docker Development Build

```bash
# Image neu bauen
docker-compose build --no-cache

# Container mit Logs starten
docker-compose up

# In Container Shell
docker exec -it mealie-recipe-importer bash
```

## 🐛 Fehlerbehebung

### "Quota erschöpft"
- Wähle ein anderes Modell in der Sidebar
- Warte die angezeigte Zeit oder bis zum nächsten Tag
- Erstelle einen neuen API Key für ein frisches Quota

### "Modell nicht verfügbar"
- Wähle ein anderes Modell aus der Liste
- Die verfügbaren Modelle ändern sich bei Google regelmäßig

### "Verbindung zu Mealie fehlgeschlagen"
- Prüfe ob Mealie erreichbar ist
- Prüfe die `MEALIE_URL` in der `.env`
- Bei Docker: Prüfe das Netzwerk-Setup

### "API Token ungültig"
- Erstelle einen neuen Token in Mealie
- Prüfe ob der Token vollständig kopiert wurde

## 📜 Lizenz

MIT License - siehe [LICENSE](LICENSE) Datei.

## 🙏 Credits

- [Mealie](https://mealie.io/) - Rezeptverwaltung
- [Google Gemini](https://ai.google.dev/) - KI API
- [Streamlit](https://streamlit.io/) - Web Framework
- [PyMuPDF](https://pymupdf.readthedocs.io/) - PDF Verarbeitung
