"""
Gemini AI Client für den Recipe Importer.
Handhabt alle KI-Operationen für Rezeptextraktion.
"""

import base64
import json
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

from google import genai

from .config import get_config, GeminiConfig

logger = logging.getLogger(__name__)


# Prompts als Konstanten
RECIPE_PROMPT_PDF = """
Analysiere diesen Rezept-Text und wandle ihn in ein valides JSON für die Mealie API um.
Antworte NUR mit dem JSON-Objekt, ohne Erklärungen oder Markdown.

WICHTIG: Rechne ALLE Zutatenmengen auf 1 PORTION um!
Wenn das Rezept z.B. für 4 Portionen ist, teile alle Mengen durch 4.

Das JSON muss exakt dieses Format haben:
{{
    "name": "Rezeptname",
    "description": "Eine kurze Beschreibung des Rezepts",
    "recipeYield": "1 Portion",
    "recipeIngredient": [
        {{"quantity": 50, "unit": "g", "food": "Mehl", "note": ""}},
        {{"quantity": 25, "unit": "ml", "food": "Milch", "note": ""}},
        {{"quantity": 0.25, "unit": "TL", "food": "Salz", "note": ""}},
        {{"quantity": 0.5, "unit": "EL", "food": "Olivenöl", "note": "extra vergine"}},
        {{"quantity": 0.25, "unit": "", "food": "Ei", "note": ""}}
    ],
    "recipeInstructions": [
        {{"text": "Schritt 1 Beschreibung"}},
        {{"text": "Schritt 2 Beschreibung"}}
    ]
}}

WICHTIG für recipeIngredient (IMMER für 1 Portion!):
- "quantity": Anzahl als Zahl für 1 PORTION (z.B. 50, 0.25, 0.5). Bei "etwas" oder "nach Geschmack" nutze 0.
- "unit": Einheit als Text (g, kg, ml, l, TL, EL, Prise, Stück, Bund, Dose, Packung, etc.). Leer lassen wenn keine Einheit.
- "food": Das Lebensmittel selbst (Mehl, Salz, Karotten, etc.)
- "note": Zusätzliche Hinweise (z.B. "gehackt", "frisch", "optional"). Leer lassen wenn keine.

Hier ist der Rezept-Text:
---
{text}
---
"""

RECIPE_PROMPT_VIDEO = """
Analysiere dieses Rezept-Video und extrahiere alle Informationen.
WICHTIG: Antworte komplett auf DEUTSCH, auch wenn das Video in einer anderen Sprache ist.
Übersetze alle Zutaten und Zubereitungsschritte ins Deutsche.

WICHTIG: Rechne ALLE Zutatenmengen auf 1 PORTION um!
Wenn das Rezept z.B. für 4 Portionen ist, teile alle Mengen durch 4.

Antworte NUR mit einem validen JSON-Objekt, ohne Erklärungen oder Markdown.

Das JSON muss exakt dieses Format haben:
{{
    "name": "Rezeptname auf Deutsch",
    "description": "Eine kurze Beschreibung des Rezepts auf Deutsch",
    "recipeYield": "1 Portion",
    "recipeIngredient": [
        {{"quantity": 50, "unit": "g", "food": "Mehl", "note": ""}},
        {{"quantity": 25, "unit": "ml", "food": "Milch", "note": ""}},
        {{"quantity": 0.25, "unit": "TL", "food": "Salz", "note": ""}},
        {{"quantity": 0.5, "unit": "EL", "food": "Olivenöl", "note": "extra vergine"}},
        {{"quantity": 0.25, "unit": "", "food": "Ei", "note": ""}}
    ],
    "recipeInstructions": [
        {{"text": "Schritt 1 Beschreibung auf Deutsch"}},
        {{"text": "Schritt 2 Beschreibung auf Deutsch"}}
    ]
}}

WICHTIG für recipeIngredient (IMMER für 1 Portion!):
- "quantity": Anzahl als Zahl für 1 PORTION (z.B. 50, 0.25, 0.5). Bei "etwas" oder "nach Geschmack" nutze 0.
- "unit": Einheit als Text (g, kg, ml, l, TL, EL, Prise, Stück, Bund, Dose, Packung, etc.). Leer lassen wenn keine Einheit.
- "food": Das Lebensmittel selbst (Mehl, Salz, Karotten, etc.)
- "note": Zusätzliche Hinweise (z.B. "gehackt", "frisch", "optional"). Leer lassen wenn keine.

Extrahiere alle Zutaten die du siehst oder hörst, rechne auf 1 Portion um, und beschreibe jeden Zubereitungsschritt detailliert auf Deutsch.
"""

RECIPE_PROMPT_VIDEO_WITH_CAPTION = """
Analysiere dieses Rezept-Video zusammen mit der dazugehörigen Beschreibung/Caption.
WICHTIG: Antworte komplett auf DEUTSCH, auch wenn das Video in einer anderen Sprache ist.
Übersetze alle Zutaten und Zubereitungsschritte ins Deutsche.

WICHTIG: Rechne ALLE Zutatenmengen auf 1 PORTION um!
Wenn das Rezept z.B. für 4 Portionen ist, teile alle Mengen durch 4.

=== VIDEO-BESCHREIBUNG / CAPTION ===
{caption}
=== ENDE DER BESCHREIBUNG ===

Nutze BEIDE Informationsquellen:
1. Das Video selbst (visuelle Informationen, gesprochene Anweisungen)
2. Die Caption/Beschreibung (oft enthält diese Mengenangaben, Tipps oder zusätzliche Infos)

Wenn die Caption Mengenangaben enthält, die im Video nicht genannt werden, nutze diese!
Wenn Video und Caption unterschiedliche Informationen haben, bevorzuge das Video für Schritte und die Caption für Mengen.

Antworte NUR mit einem validen JSON-Objekt, ohne Erklärungen oder Markdown.

Das JSON muss exakt dieses Format haben:
{{
    "name": "Rezeptname auf Deutsch",
    "description": "Eine kurze Beschreibung des Rezepts auf Deutsch",
    "recipeYield": "1 Portion",
    "recipeIngredient": [
        {{"quantity": 50, "unit": "g", "food": "Mehl", "note": ""}},
        {{"quantity": 25, "unit": "ml", "food": "Milch", "note": ""}},
        {{"quantity": 0.25, "unit": "TL", "food": "Salz", "note": ""}},
        {{"quantity": 0.5, "unit": "EL", "food": "Olivenöl", "note": "extra vergine"}},
        {{"quantity": 0.25, "unit": "", "food": "Ei", "note": ""}}
    ],
    "recipeInstructions": [
        {{"text": "Schritt 1 Beschreibung auf Deutsch"}},
        {{"text": "Schritt 2 Beschreibung auf Deutsch"}}
    ]
}}

WICHTIG für recipeIngredient (IMMER für 1 Portion!):
- "quantity": Anzahl als Zahl für 1 PORTION (z.B. 50, 0.25, 0.5). Bei "etwas" oder "nach Geschmack" nutze 0.
- "unit": Einheit als Text (g, kg, ml, l, TL, EL, Prise, Stück, Bund, Dose, Packung, etc.). Leer lassen wenn keine Einheit.
- "food": Das Lebensmittel selbst (Mehl, Salz, Karotten, etc.)
- "note": Zusätzliche Hinweise (z.B. "gehackt", "frisch", "optional"). Leer lassen wenn keine.

Extrahiere alle Zutaten die du siehst, hörst oder in der Caption findest. Rechne auf 1 Portion um und beschreibe jeden Zubereitungsschritt detailliert auf Deutsch.
"""

RECIPE_PROMPT_IMAGE = """
Analysiere dieses Foto eines Rezepts (z.B. aus einem Kochbuch oder einer Zeitschrift).
Extrahiere alle Informationen die du auf dem Bild lesen kannst.

WICHTIG: Rechne ALLE Zutatenmengen auf 1 PORTION um!
Wenn das Rezept z.B. für 4 Portionen ist, teile alle Mengen durch 4.

Antworte NUR mit einem validen JSON-Objekt, ohne Erklärungen oder Markdown.

Das JSON muss exakt dieses Format haben:
{{
    "name": "Rezeptname",
    "description": "Eine kurze Beschreibung des Rezepts",
    "recipeYield": "1 Portion",
    "recipeIngredient": [
        {{"quantity": 50, "unit": "g", "food": "Mehl", "note": ""}},
        {{"quantity": 25, "unit": "ml", "food": "Milch", "note": ""}},
        {{"quantity": 0.25, "unit": "TL", "food": "Salz", "note": ""}},
        {{"quantity": 0.5, "unit": "EL", "food": "Olivenöl", "note": "extra vergine"}},
        {{"quantity": 0.25, "unit": "", "food": "Ei", "note": ""}}
    ],
    "recipeInstructions": [
        {{"text": "Schritt 1 Beschreibung"}},
        {{"text": "Schritt 2 Beschreibung"}}
    ],
    "best_image_index": 0
}}

WICHTIG für recipeIngredient (IMMER für 1 Portion!):
- "quantity": Anzahl als Zahl für 1 PORTION (z.B. 50, 0.25, 0.5). Bei "etwas" oder "nach Geschmack" nutze 0.
- "unit": Einheit als Text (g, kg, ml, l, TL, EL, Prise, Stück, Bund, Dose, Packung, etc.). Leer lassen wenn keine Einheit.
- "food": Das Lebensmittel selbst (Mehl, Salz, Karotten, etc.)
- "note": Zusätzliche Hinweise (z.B. "gehackt", "frisch", "optional"). Leer lassen wenn keine.

WICHTIG für best_image_index:
- Wenn mehrere Bilder hochgeladen wurden, wähle das Bild das am besten als Rezeptfoto geeignet ist
- Bevorzuge Bilder die das fertige Gericht zeigen
- Der Index ist 0-basiert (erstes Bild = 0, zweites = 1, etc.)
- Wenn nur ein Bild vorhanden ist, setze 0

Lies den gesamten Text auf dem Bild und extrahiere alle Zutaten und Zubereitungsschritte.
"""

RECIPE_PROMPT_MULTI_IMAGE = """
Analysiere diese Fotos eines Rezepts (z.B. mehrere Seiten aus einem Kochbuch).
Extrahiere alle Informationen die du auf den Bildern lesen kannst und kombiniere sie zu einem vollständigen Rezept.

WICHTIG: Rechne ALLE Zutatenmengen auf 1 PORTION um!
Wenn das Rezept z.B. für 4 Portionen ist, teile alle Mengen durch 4.

Antworte NUR mit einem validen JSON-Objekt, ohne Erklärungen oder Markdown.

Das JSON muss exakt dieses Format haben:
{{
    "name": "Rezeptname",
    "description": "Eine kurze Beschreibung des Rezepts",
    "recipeYield": "1 Portion",
    "recipeIngredient": [
        {{"quantity": 50, "unit": "g", "food": "Mehl", "note": ""}},
        {{"quantity": 25, "unit": "ml", "food": "Milch", "note": ""}}
    ],
    "recipeInstructions": [
        {{"text": "Schritt 1 Beschreibung"}},
        {{"text": "Schritt 2 Beschreibung"}}
    ],
    "best_image_index": 0
}}

WICHTIG für best_image_index:
- Wähle das Bild das am besten als Rezeptfoto/Cover geeignet ist (0-basierter Index)
- Bevorzuge Bilder die das FERTIGE Gericht appetitlich zeigen
- NICHT die Zutatenliste oder Textseiten wählen
- Erstes Bild = 0, zweites = 1, drittes = 2, etc.

Kombiniere die Informationen aus allen Bildern zu einem vollständigen Rezept.
"""

VIDEO_FRAME_PROMPT = """
Analysiere dieses Rezept-Video und finde den besten Zeitpunkt für ein Rezeptfoto.

Suche nach dem Moment wo das FERTIGE Gericht am appetitlichsten aussieht.
Das sollte idealerweise sein:
- Das angerichtete/servierte Gericht
- Ein schöner Moment beim Anrichten
- Der "Hero Shot" des fertigen Essens

Antworte NUR mit einem JSON-Objekt:
{{
    "best_timestamp_seconds": 45,
    "description": "Kurze Beschreibung warum dieser Moment gewählt wurde"
}}

Gib die Zeit in Sekunden an (z.B. 45 für 0:45, 90 für 1:30).
Wenn kein guter Moment gefunden wird, wähle einen Zeitpunkt in der zweiten Hälfte des Videos.
"""


@dataclass
class GeminiError(Exception):
    """Fehler bei der Gemini API Kommunikation."""
    message: str
    is_quota_error: bool = False
    retry_after: Optional[int] = None
    
    def __str__(self):
        if self.is_quota_error and self.retry_after:
            return f"Quota erschöpft! Warte ~{self.retry_after}s oder wähle ein anderes Modell."
        return f"KI Fehler: {self.message}"


class GeminiClient:
    """Client für die Gemini API."""
    
    # Mapping für Video MIME-Types
    MIME_TYPES = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska"
    }
    
    def __init__(self, config: Optional[GeminiConfig] = None):
        """
        Initialisiert den Gemini Client.
        
        Args:
            config: Optionale Konfiguration, sonst wird die globale verwendet.
        """
        self.config = config or get_config().gemini
        self._client: Optional[genai.Client] = None
        
    @property
    def client(self) -> genai.Client:
        """Lazy-initialisierter Gemini Client."""
        if self._client is None:
            if not self.config.api_key:
                raise GeminiError("GEMINI_API_KEY ist nicht konfiguriert")
            self._client = genai.Client(api_key=self.config.api_key)
        return self._client
    
    def _parse_error(self, error: Exception) -> GeminiError:
        """Parst eine Exception und erstellt einen GeminiError."""
        error_str = str(error)
        
        # Quota-Fehler erkennen
        if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
            # Versuche retry delay zu extrahieren
            match = re.search(r'retry in (\d+)', error_str, re.IGNORECASE)
            retry_after = int(match.group(1)) if match else None
            return GeminiError(
                message="Quota erschöpft",
                is_quota_error=True,
                retry_after=retry_after
            )
        
        # Modell nicht verfügbar
        if "404" in error_str or "not found" in error_str.lower():
            return GeminiError(message="Modell nicht verfügbar. Bitte ein anderes wählen.")
        
        # Server überlastet
        if "503" in error_str or "overloaded" in error_str.lower():
            return GeminiError(message="Server überlastet. Bitte später erneut versuchen.")
            
        return GeminiError(message=error_str)
    
    def _clean_json_response(self, text: str) -> str:
        """Entfernt Markdown-Codeblöcke aus der Antwort."""
        return re.sub(r'```json\s*|```\s*', '', text).strip()
    
    def check_quota(self, model: str) -> tuple[bool, str]:
        """
        Prüft ob API-Quota verfügbar ist.
        
        Args:
            model: Zu prüfendes Modell
            
        Returns:
            Tuple aus (Erfolg, Nachricht)
        """
        try:
            response = self.client.models.generate_content(
                model=model,
                contents="Antworte nur mit: OK"
            )
            return True, f"✅ Quota OK! Modell: {model}"
        except Exception as e:
            error = self._parse_error(e)
            return False, str(error)
    
    def _get_next_model(self, current_model: str) -> Optional[str]:
        """Gibt das nächste verfügbare Modell zurück."""
        models = self.config.available_models
        try:
            idx = models.index(current_model)
            if idx + 1 < len(models):
                return models[idx + 1]
        except ValueError:
            pass
        return None
    
    def _generate_with_fallback(
        self, 
        model: str, 
        contents, 
        on_model_switch: Optional[callable] = None
    ) -> tuple[str, str]:
        """
        Generiert Content mit automatischem Modell-Fallback bei Quota-Fehlern.
        
        Args:
            model: Startmodell
            contents: Inhalt für die API
            on_model_switch: Callback wenn Modell gewechselt wird (model_name, reason)
            
        Returns:
            Tuple aus (response_text, used_model)
        """
        current_model = model
        tried_models = []
        
        while current_model:
            tried_models.append(current_model)
            try:
                logger.info(f"Versuche Modell: {current_model}")
                response = self.client.models.generate_content(
                    model=current_model,
                    contents=contents
                )
                return response.text, current_model
                
            except Exception as e:
                error = self._parse_error(e)
                
                if error.is_quota_error:
                    next_model = self._get_next_model(current_model)
                    if next_model and next_model not in tried_models:
                        logger.warning(f"Quota erschöpft für {current_model}, wechsle zu {next_model}")
                        if on_model_switch:
                            on_model_switch(next_model, f"Quota erschöpft bei {current_model}")
                        current_model = next_model
                        continue
                    else:
                        raise GeminiError(
                            message=f"Quota bei allen Modellen erschöpft: {', '.join(tried_models)}",
                            is_quota_error=True
                        )
                else:
                    raise error
        
        raise GeminiError("Kein Modell verfügbar")
    
    def extract_recipe_from_text(
        self, 
        text: str, 
        model: str,
        on_model_switch: Optional[callable] = None
    ) -> tuple[dict, str]:
        """
        Extrahiert Rezeptdaten aus Text.
        
        Args:
            text: Rezepttext (z.B. aus PDF)
            model: Zu verwendendes Modell
            on_model_switch: Callback bei Modellwechsel
            
        Returns:
            Tuple aus (Rezept-Dictionary, verwendetes Modell)
            
        Raises:
            GeminiError: Bei API-Fehlern
        """
        prompt = RECIPE_PROMPT_PDF.format(text=text)
        
        try:
            logger.info(f"Extrahiere Rezept aus Text mit {model}")
            response_text, used_model = self._generate_with_fallback(
                model, prompt, on_model_switch
            )
            
            clean_json = self._clean_json_response(response_text)
            recipe = json.loads(clean_json)
            logger.info(f"Rezept extrahiert: {recipe.get('name', 'Unbekannt')}")
            return recipe, used_model
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parse Fehler: {e}")
            raise GeminiError(f"Ungültiges JSON von KI: {e}")
        except GeminiError:
            raise
        except Exception as e:
            raise self._parse_error(e)
    
    def _detect_mime_type(self, image_bytes: bytes) -> str:
        """Erkennt den MIME-Type eines Bildes."""
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        elif image_bytes[:4] == b'RIFF' and len(image_bytes) > 12 and image_bytes[8:12] == b'WEBP':
            return "image/webp"
        return "image/jpeg"
    
    def extract_recipe_from_images(
        self,
        images: list[bytes],
        model: str,
        on_model_switch: Optional[callable] = None
    ) -> tuple[dict, str, int]:
        """
        Extrahiert Rezeptdaten aus einem oder mehreren Bildern.
        
        Args:
            images: Liste von Bildern als Bytes
            model: Zu verwendendes Modell
            on_model_switch: Callback bei Modellwechsel
            
        Returns:
            Tuple aus (Rezept-Dictionary, verwendetes Modell, Index des besten Bildes)
            
        Raises:
            GeminiError: Bei API-Fehlern
        """
        if not images:
            raise GeminiError("Keine Bilder zum Analysieren")
        
        logger.info(f"Extrahiere Rezept aus {len(images)} Bild(ern)")
        
        try:
            # Alle Bilder als Parts erstellen
            contents = []
            for i, image_bytes in enumerate(images):
                mime_type = self._detect_mime_type(image_bytes)
                logger.info(f"Bild {i+1}: {len(image_bytes)/1024:.1f} KB, {mime_type}")
                
                image_part = {
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": base64.b64encode(image_bytes).decode('utf-8')
                    }
                }
                contents.append(image_part)
            
            # Passenden Prompt wählen
            prompt = RECIPE_PROMPT_MULTI_IMAGE if len(images) > 1 else RECIPE_PROMPT_IMAGE
            contents.append(prompt)
            
            response_text, used_model = self._generate_with_fallback(
                model, contents, on_model_switch
            )
            
            clean_json = self._clean_json_response(response_text)
            recipe = json.loads(clean_json)
            
            # Best image index extrahieren
            best_image_index = recipe.pop("best_image_index", 0)
            # Sicherstellen dass Index gültig ist
            if not isinstance(best_image_index, int) or best_image_index < 0 or best_image_index >= len(images):
                best_image_index = 0
            
            logger.info(f"Rezept aus Bildern extrahiert: {recipe.get('name', 'Unbekannt')}, bestes Bild: {best_image_index + 1}")
            return recipe, used_model, best_image_index
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parse Fehler: {e}")
            raise GeminiError(f"Ungültiges JSON von KI: {e}")
        except GeminiError:
            raise
        except Exception as e:
            raise self._parse_error(e)
    
    def extract_best_frame_timestamp(
        self,
        video_file,
        model: str,
        on_model_switch: Optional[callable] = None
    ) -> int:
        """
        Lässt die KI den besten Zeitpunkt für ein Rezeptfoto im Video finden.
        
        Args:
            video_file: Hochgeladenes Video-File Object von Google
            model: Zu verwendendes Modell
            on_model_switch: Callback bei Modellwechsel
            
        Returns:
            Zeitstempel in Sekunden
        """
        try:
            logger.info("Suche besten Frame im Video...")
            
            contents = [video_file, VIDEO_FRAME_PROMPT]
            response_text, _ = self._generate_with_fallback(
                model, contents, on_model_switch
            )
            
            clean_json = self._clean_json_response(response_text)
            result = json.loads(clean_json)
            
            timestamp = result.get("best_timestamp_seconds", 0)
            description = result.get("description", "")
            
            logger.info(f"Bester Frame bei {timestamp}s: {description}")
            return int(timestamp)
            
        except Exception as e:
            logger.warning(f"Konnte besten Frame nicht finden: {e}, nutze Fallback")
            return 0
    
    def extract_recipe_from_image(
        self,
        image_bytes: bytes,
        model: str,
        on_model_switch: Optional[callable] = None
    ) -> tuple[dict, str]:
        """
        Extrahiert Rezeptdaten aus einem Bild (z.B. Foto einer Buchseite).
        Wrapper für extract_recipe_from_images mit einem Bild.
        
        Args:
            image_bytes: Bild als Bytes
            model: Zu verwendendes Modell
            on_model_switch: Callback bei Modellwechsel
            
        Returns:
            Tuple aus (Rezept-Dictionary, verwendetes Modell)
            
        Raises:
            GeminiError: Bei API-Fehlern
        """
        recipe, used_model, _ = self.extract_recipe_from_images(
            [image_bytes], model, on_model_switch
        )
        return recipe, used_model
    
    def extract_recipe_from_video(
        self, 
        video_bytes: bytes, 
        filename: str, 
        model: str,
        caption: Optional[str] = None,
        progress_callback: Optional[callable] = None,
        on_model_switch: Optional[callable] = None
    ) -> tuple[dict, str, int]:
        """
        Extrahiert Rezeptdaten aus einem Video.
        
        Args:
            video_bytes: Video als Bytes
            filename: Originaler Dateiname
            model: Zu verwendendes Modell
            caption: Optionale Video-Caption/Beschreibung (z.B. von TikTok)
            progress_callback: Optionale Callback-Funktion für Statusupdates
            on_model_switch: Callback bei Modellwechsel
            
        Returns:
            Tuple aus (Rezept-Dictionary, verwendetes Modell, bester Frame-Timestamp in Sekunden)
            
        Raises:
            GeminiError: Bei API-Fehlern
        """
        def update_progress(message: str):
            if progress_callback:
                progress_callback(message)
            logger.info(message)
        
        # Dateiendung ermitteln - für URL-Videos immer .mp4 verwenden
        ext = os.path.splitext(filename)[1].lower()
        if not ext or ext not in self.MIME_TYPES:
            ext = ".mp4"
        mime_type = self.MIME_TYPES.get(ext, "video/mp4")
        
        # Video temporär speichern
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
            tmp_file.write(video_bytes)
            tmp_path = tmp_file.name
        
        logger.info(f"Video gespeichert: {tmp_path} ({len(video_bytes) / 1024 / 1024:.1f} MB)")
        
        try:
            # Video hochladen
            update_progress("📤 Lade Video zu Google hoch...")
            video_file = self.client.files.upload(file=tmp_path)
            logger.info(f"Upload erfolgreich: {video_file.name}, State: {video_file.state.name}")
            
            # Warten bis Video verarbeitet ist
            update_progress("⏳ Video wird verarbeitet...")
            wait_count = 0
            while video_file.state.name == "PROCESSING":
                time.sleep(3)
                wait_count += 1
                video_file = self.client.files.get(name=video_file.name)
                logger.debug(f"Warte auf Verarbeitung... ({wait_count * 3}s, State: {video_file.state.name})")
                if wait_count > 60:  # Max 3 Minuten warten
                    raise GeminiError("Video-Verarbeitung dauert zu lange (Timeout nach 3 Min)")
            
            if video_file.state.name == "FAILED":
                # Mehr Details zum Fehler
                error_detail = getattr(video_file, 'error', None)
                if error_detail:
                    logger.error(f"Video-Verarbeitung fehlgeschlagen: {error_detail}")
                    raise GeminiError(f"Video-Verarbeitung fehlgeschlagen: {error_detail}")
                else:
                    logger.error(f"Video-Verarbeitung fehlgeschlagen, State: {video_file.state}")
                    raise GeminiError("Video-Verarbeitung bei Google fehlgeschlagen. Versuche ein anderes Video oder lade es manuell herunter.")
            
            logger.info(f"Video bereit: State={video_file.state.name}")
            
            # Zuerst: Besten Frame-Timestamp ermitteln
            best_timestamp = 0
            try:
                update_progress("🎬 Suche bestes Bild im Video...")
                best_timestamp = self.extract_best_frame_timestamp(
                    video_file, model, on_model_switch
                )
            except Exception as e:
                logger.warning(f"Konnte besten Frame nicht ermitteln: {e}")
            
            # Prompt auswählen - mit oder ohne Caption
            if caption and caption.strip():
                prompt = RECIPE_PROMPT_VIDEO_WITH_CAPTION.format(caption=caption)
                update_progress("🤖 Analysiere Video + Caption mit KI...")
            else:
                prompt = RECIPE_PROMPT_VIDEO
                update_progress("🤖 Analysiere Video mit KI...")
            
            # Mit Fallback generieren
            contents = [video_file, prompt]
            response_text, used_model = self._generate_with_fallback(
                model, contents, on_model_switch
            )
            
            # Aufräumen - Video bei Google löschen
            try:
                self.client.files.delete(name=video_file.name)
                logger.debug("Video bei Google gelöscht")
            except Exception as e:
                logger.warning(f"Konnte Video nicht löschen: {e}")
            
            clean_json = self._clean_json_response(response_text)
            recipe = json.loads(clean_json)
            logger.info(f"Rezept aus Video extrahiert: {recipe.get('name', 'Unbekannt')}, bester Frame bei {best_timestamp}s")
            return recipe, used_model, best_timestamp
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON Parse Fehler: {e}")
            raise GeminiError(f"Ungültiges JSON von KI: {e}")
        except GeminiError:
            raise
        except Exception as e:
            raise self._parse_error(e)
        finally:
            # Temporäre Datei löschen
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
