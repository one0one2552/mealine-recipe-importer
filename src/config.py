"""
Konfigurationsmodul für den Mealie Recipe Importer.
Lädt Einstellungen aus Umgebungsvariablen mit sinnvollen Defaults.
"""

import os
from dataclasses import dataclass, field
from typing import Optional
import logging

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class MealieConfig:
    """Konfiguration für die Mealie API."""
    url: str = field(default_factory=lambda: os.getenv("MEALIE_URL", "http://localhost:9000"))
    api_token: str = field(default_factory=lambda: os.getenv("MEALIE_API_TOKEN", ""))
    timeout: int = field(default_factory=lambda: int(os.getenv("MEALIE_TIMEOUT", "30")))
    
    def __post_init__(self):
        # URL normalisieren (trailing slash entfernen)
        self.url = self.url.rstrip("/")
        
    def is_configured(self) -> bool:
        """Prüft ob die Mealie-Konfiguration vollständig ist."""
        return bool(self.url and self.api_token)


@dataclass
class GeminiConfig:
    """Konfiguration für die Gemini API."""
    api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    default_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    
    # Verfügbare Modelle (schnellste/günstigste zuerst)
    available_models: list = field(default_factory=lambda: [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.5-pro",
        "gemini-flash-lite-latest",
    ])
    
    def is_configured(self) -> bool:
        """Prüft ob die Gemini-Konfiguration vollständig ist."""
        return bool(self.api_key)


@dataclass
class AppConfig:
    """Hauptkonfiguration der Anwendung."""
    mealie: MealieConfig = field(default_factory=MealieConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    
    # App-Einstellungen
    app_title: str = "🍳 Mealie Rezept-Importer"
    max_video_duration_minutes: int = 2
    supported_video_formats: list = field(default_factory=lambda: ["mp4", "mov", "webm", "avi", "mkv"])
    supported_document_formats: list = field(default_factory=lambda: ["pdf"])
    
    def validate(self) -> list[str]:
        """Validiert die Konfiguration und gibt Fehlermeldungen zurück."""
        errors = []
        
        if not self.mealie.is_configured():
            if not self.mealie.url:
                errors.append("MEALIE_URL ist nicht konfiguriert")
            if not self.mealie.api_token:
                errors.append("MEALIE_API_TOKEN ist nicht konfiguriert")
                
        if not self.gemini.is_configured():
            errors.append("GEMINI_API_KEY ist nicht konfiguriert")
            
        return errors
    
    def is_valid(self) -> bool:
        """Prüft ob die Konfiguration gültig ist."""
        return len(self.validate()) == 0


# Singleton-Instanz für globalen Zugriff
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Gibt die globale Konfigurationsinstanz zurück."""
    global _config
    if _config is None:
        _config = AppConfig()
        
        # Validierung loggen
        errors = _config.validate()
        if errors:
            for error in errors:
                logger.warning(f"Konfigurationsfehler: {error}")
        else:
            logger.info("Konfiguration erfolgreich geladen")
            
    return _config


def reload_config() -> AppConfig:
    """Lädt die Konfiguration neu."""
    global _config
    _config = None
    return get_config()
