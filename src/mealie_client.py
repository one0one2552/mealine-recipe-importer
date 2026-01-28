"""
Mealie API Client für den Recipe Importer.
Handhabt alle Kommunikation mit der Mealie API.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Optional
import requests
from requests.exceptions import ConnectionError, Timeout, RequestException

from .config import get_config, MealieConfig

logger = logging.getLogger(__name__)


@dataclass
class MealieError(Exception):
    """Fehler bei der Mealie API Kommunikation."""
    message: str
    status_code: Optional[int] = None
    details: Optional[str] = None
    
    def __str__(self):
        if self.status_code:
            return f"Mealie API Fehler ({self.status_code}): {self.message}"
        return f"Mealie Fehler: {self.message}"


class MealieClient:
    """Client für die Mealie API."""
    
    def __init__(self, config: Optional[MealieConfig] = None):
        """
        Initialisiert den Mealie Client.
        
        Args:
            config: Optionale Konfiguration, sonst wird die globale verwendet.
        """
        self.config = config or get_config().mealie
        self._headers = {
            "Authorization": f"Bearer {self.config.api_token}",
            "Content-Type": "application/json"
        }
        
    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Führt einen HTTP Request aus mit einheitlichem Error Handling.
        
        Args:
            method: HTTP Methode (GET, POST, PUT, PATCH, DELETE)
            endpoint: API Endpunkt (ohne Basis-URL)
            **kwargs: Weitere Argumente für requests
            
        Returns:
            Response Objekt
            
        Raises:
            MealieError: Bei API oder Verbindungsfehlern
        """
        url = f"{self.config.url}{endpoint}"
        kwargs.setdefault("headers", self._headers)
        kwargs.setdefault("timeout", self.config.timeout)
        
        try:
            response = requests.request(method, url, **kwargs)
            return response
        except ConnectionError:
            raise MealieError(
                message=f"Verbindung zu Mealie ({self.config.url}) fehlgeschlagen",
                details="Ist der Server erreichbar?"
            )
        except Timeout:
            raise MealieError(
                message="Zeitüberschreitung bei Mealie-Anfrage",
                details=f"Timeout nach {self.config.timeout}s"
            )
        except RequestException as e:
            raise MealieError(message=str(e))
    
    def test_connection(self) -> tuple[bool, str]:
        """
        Testet die Verbindung zu Mealie.
        
        Returns:
            Tuple aus (Erfolg, Nachricht)
        """
        try:
            response = self._request("GET", "/api/app/about")
            if response.status_code == 200:
                data = response.json()
                version = data.get("version", "unbekannt")
                return True, f"Verbunden mit Mealie v{version}"
            return False, f"Unerwartete Antwort: {response.status_code}"
        except MealieError as e:
            return False, str(e)
    
    def get_or_create_food(self, name: str) -> Optional[dict]:
        """
        Holt oder erstellt ein Lebensmittel.
        
        Args:
            name: Name des Lebensmittels
            
        Returns:
            Dict mit id und name oder None
        """
        if not name or not name.strip():
            return None
            
        name = name.strip()
        
        try:
            # Suche nach bestehendem Food
            response = self._request("GET", "/api/foods", params={"search": name})
            if response.status_code == 200:
                foods = response.json().get("items", [])
                for food in foods:
                    if food.get("name", "").lower() == name.lower():
                        logger.debug(f"Food gefunden: {name} (ID: {food['id']})")
                        return {"id": food["id"], "name": food["name"]}
            
            # Erstelle neues Food
            response = self._request("POST", "/api/foods", json={"name": name})
            if response.status_code in [200, 201]:
                data = response.json()
                logger.info(f"Food erstellt: {name} (ID: {data['id']})")
                return {"id": data["id"], "name": data["name"]}
                
            logger.warning(f"Food konnte nicht erstellt werden: {name}")
            return None
            
        except MealieError as e:
            logger.error(f"Fehler bei Food '{name}': {e}")
            return None
    
    def get_or_create_unit(self, name: str) -> Optional[dict]:
        """
        Holt oder erstellt eine Einheit.
        
        Args:
            name: Name oder Abkürzung der Einheit
            
        Returns:
            Dict mit id und name oder None
        """
        if not name or not name.strip():
            return None
            
        name = name.strip()
        
        try:
            # Suche nach bestehender Unit
            response = self._request("GET", "/api/units", params={"search": name})
            if response.status_code == 200:
                units = response.json().get("items", [])
                for unit in units:
                    unit_name = unit.get("name", "").lower()
                    unit_abbr = unit.get("abbreviation", "").lower()
                    if unit_name == name.lower() or unit_abbr == name.lower():
                        logger.debug(f"Unit gefunden: {name} (ID: {unit['id']})")
                        return {"id": unit["id"], "name": unit["name"]}
            
            # Erstelle neue Unit
            response = self._request("POST", "/api/units", json={
                "name": name,
                "abbreviation": name
            })
            if response.status_code in [200, 201]:
                data = response.json()
                logger.info(f"Unit erstellt: {name} (ID: {data['id']})")
                return {"id": data["id"], "name": data["name"]}
                
            logger.warning(f"Unit konnte nicht erstellt werden: {name}")
            return None
            
        except MealieError as e:
            logger.error(f"Fehler bei Unit '{name}': {e}")
            return None
    
    def create_recipe(self, recipe_data: dict, thumbnail_data: bytes = None, source_url: str = None) -> tuple[bool, str]:
        """
        Erstellt ein Rezept in Mealie.
        
        Args:
            recipe_data: Rezeptdaten von der KI
            thumbnail_data: Optionales Thumbnail als Bytes
            source_url: Optionaler Original-Link zum Video
            
        Returns:
            Tuple aus (Erfolg, Nachricht/Slug)
        """
        try:
            # Schritt 1: Rezept erstellen (nur mit Name)
            name = recipe_data.get("name", "Unbenanntes Rezept")
            response = self._request("POST", "/api/recipes", json={"name": name})
            
            if response.status_code not in [200, 201]:
                return False, f"Erstellen fehlgeschlagen ({response.status_code}): {response.text}"
            
            # Slug aus der Antwort holen
            response_data = response.json()
            if isinstance(response_data, str):
                slug = response_data
            elif isinstance(response_data, dict):
                slug = response_data.get("slug") or response_data.get("id")
            else:
                return False, f"Unerwartete API-Antwort: {response_data}"
            
            if not slug:
                return False, "Kein Slug in der API-Antwort erhalten"
            
            logger.info(f"Rezept erstellt: {name} (Slug: {slug})")
            
            # Schritt 2: Aktuelles Rezept abrufen
            response = self._request("GET", f"/api/recipes/{slug}")
            if response.status_code != 200:
                return False, f"Abrufen fehlgeschlagen ({response.status_code}): {response.text}"
            
            existing_recipe = response.json()
            
            # Schritt 3: Rezept mit Details aktualisieren
            description = recipe_data.get("description", "")
            
            # Source-URL zur Beschreibung hinzufügen
            if source_url:
                if description:
                    description = f"{description}\n\n📹 Quelle: {source_url}"
                else:
                    description = f"📹 Quelle: {source_url}"
                # Auch das orgURL Feld setzen
                existing_recipe["orgURL"] = source_url
            
            existing_recipe["description"] = description
            existing_recipe["recipeYield"] = recipe_data.get("recipeYield", "1 Portion")
            
            # Zutaten formatieren
            ingredients = self._format_ingredients(recipe_data.get("recipeIngredient", []))
            existing_recipe["recipeIngredient"] = ingredients
            
            # Anweisungen formatieren
            instructions = self._format_instructions(recipe_data.get("recipeInstructions", []))
            existing_recipe["recipeInstructions"] = instructions
            
            # Schritt 4: PUT mit dem kompletten Rezept
            response = self._request("PUT", f"/api/recipes/{slug}", json=existing_recipe)
            
            if response.status_code in [200, 201]:
                logger.info(f"Rezept aktualisiert: {slug}")
                
                # Schritt 5: Thumbnail hochladen (falls vorhanden)
                if thumbnail_data:
                    self.upload_recipe_image(slug, thumbnail_data)
                
                return True, slug
            else:
                return False, f"Update fehlgeschlagen ({response.status_code}): {response.text}"
                
        except MealieError as e:
            return False, str(e)
        except Exception as e:
            logger.exception("Unerwarteter Fehler beim Erstellen des Rezepts")
            return False, f"Fehler: {e}"
    
    def _format_ingredients(self, ingredients: list) -> list:
        """
        Formatiert Zutaten für die Mealie API.
        
        Args:
            ingredients: Liste von Zutatendaten
            
        Returns:
            Formatierte Zutatenliste
        """
        formatted = []
        
        for ing in ingredients:
            if isinstance(ing, dict):
                qty = ing.get("quantity", "")
                unit_name = ing.get("unit", "")
                food_name = ing.get("food", "")
                note = ing.get("note", "")
                
                # Quantity parsen
                quantity = None
                if qty:
                    try:
                        quantity = float(qty)
                    except (ValueError, TypeError):
                        quantity = None
                
                # Unit und Food holen oder erstellen
                unit_ref = self.get_or_create_unit(unit_name) if unit_name else None
                food_ref = self.get_or_create_food(food_name) if food_name else None
                
                formatted.append({
                    "quantity": quantity,
                    "unit": unit_ref,
                    "food": food_ref,
                    "note": note or None
                })
            else:
                # Fallback: Nur note
                formatted.append({"note": str(ing)})
                
        return formatted
    
    def _format_instructions(self, instructions: list) -> list:
        """
        Formatiert Anweisungen für die Mealie API.
        
        Args:
            instructions: Liste von Anweisungen
            
        Returns:
            Formatierte Anweisungsliste
        """
        formatted = []
        
        for step in instructions:
            text = step.get("text", step) if isinstance(step, dict) else str(step)
            formatted.append({
                "id": str(uuid.uuid4()),
                "text": text
            })
            
        return formatted
    
    def upload_recipe_image(self, slug: str, image_data: bytes, filename: str = "cover.jpg") -> bool:
        """
        Lädt ein Bild für ein Rezept hoch.
        
        Args:
            slug: Slug des Rezepts
            image_data: Bild als Bytes
            filename: Dateiname für das Bild
            
        Returns:
            True wenn erfolgreich
        """
        try:
            logger.info(f"Lade Bild hoch für {slug} ({len(image_data) / 1024:.1f} KB)")
            
            # Content-Type basierend auf Daten erkennen
            content_type = "image/jpeg"
            ext = "jpg"
            if image_data[:8] == b'\x89PNG\r\n\x1a\n':
                content_type = "image/png"
                ext = "png"
            elif image_data[:4] == b'RIFF' and image_data[8:12] == b'WEBP':
                content_type = "image/webp"
                ext = "webp"
            
            # Multipart-Upload für Bild
            files = {
                "image": (f"cover.{ext}", image_data, content_type),
                "extension": (None, ext)
            }
            
            # Spezielle Headers ohne Content-Type (wird von requests gesetzt)
            headers = {"Authorization": f"Bearer {self.config.api_token}"}
            
            response = requests.put(
                f"{self.config.url}/api/recipes/{slug}/image",
                headers=headers,
                files=files,
                timeout=self.config.timeout
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Bild erfolgreich hochgeladen für Rezept: {slug}")
                return True
            else:
                logger.warning(f"Bild-Upload fehlgeschlagen ({response.status_code}): {response.text[:200]}")
                return False
                
        except Exception as e:
            logger.error(f"Fehler beim Bild-Upload: {e}")
            return False
