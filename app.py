"""
Mealie Recipe Importer - Streamlit Web Application
Version: 0.1.0

Eine Webanwendung zum Importieren von Rezepten aus PDFs und Videos
in die Mealie Rezeptverwaltung mittels Google Gemini KI.

Features:
- Import von TikTok, Instagram, YouTube Videos
- PDF-Rezepte extrahieren
- Kochbuch-Fotos scannen
- Automatischer Upload zu Mealie

Author: Mealie Importer Team
"""

# =============================================================================
# IMPORTS
# =============================================================================
import streamlit as st
import logging
import os
from pathlib import Path

# .env Datei laden (für lokale Entwicklung)
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

from src.config import get_config
from src.mealie_client import MealieClient, MealieError
from src.gemini_client import GeminiClient, GeminiError
from src.pdf_processor import extract_text_from_pdf, PDFError
from src.url_processor import (
    download_video_from_url, 
    URLError, 
    is_supported_url,
    format_video_info_for_display
)

# =============================================================================
# KONSTANTEN & LOGGING
# =============================================================================
__version__ = "0.1.0"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# SESSION STATE MANAGEMENT
# =============================================================================
def init_session_state():
    """
    Initialisiert den Streamlit Session State mit allen benötigten Variablen.
    
    Der Session State speichert alle Daten zwischen Reruns der App,
    z.B. hochgeladene Dateien, extrahierte Rezepte, UI-Einstellungen.
    """
    defaults = {
        # Rezeptdaten
        "recipe_json": None,           # Extrahiertes Rezept als Dict
        "file_bytes": None,            # Hochgeladene Datei als Bytes
        "last_filename": None,         # Name der letzten Datei
        "file_type": None,             # Typ: pdf, video, url_video, photo, photos
        "processing_error": None,      # Letzter Fehler
        
        # Video-spezifisch
        "video_caption": None,         # Caption von Social Media Videos
        "video_info": None,            # VideoInfo Objekt mit Metadaten
        
        # KI-Verarbeitung
        "used_model": None,            # Tatsächlich verwendetes Modell
        "model_switches": [],          # Liste von Modellwechseln (Fallbacks)
        
        # Foto-spezifisch
        "photo_images": [],            # Liste aller hochgeladenen Bilder
        "photo_names": None,           # Tuple der Dateinamen (für Change Detection)
        "best_image_index": 0,         # Von KI gewähltes bestes Bild
        
        # UI-Einstellungen
        "auto_upload": False,          # Automatisch zu Mealie hochladen
        "auto_upload_done": False,     # Flag um doppelten Upload zu verhindern
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_session_state():
    """
    Setzt den Session State für ein neues Rezept zurück.
    
    Hinweis: Einige Werte wie Verbindungsstatus und auto_upload
    werden bewusst NICHT zurückgesetzt.
    """
    # Rezeptdaten zurücksetzen
    st.session_state.recipe_json = None
    st.session_state.file_bytes = None
    st.session_state.last_filename = None
    st.session_state.file_type = None
    st.session_state.processing_error = None
    
    # Video-spezifisch
    st.session_state.video_caption = None
    st.session_state.video_info = None
    
    # KI-Verarbeitung
    st.session_state.used_model = None
    st.session_state.model_switches = []
    
    # Foto-spezifisch
    st.session_state.photo_images = []
    st.session_state.photo_names = None
    st.session_state.best_image_index = 0
    
    # Auto-Upload Flag zurücksetzen für nächstes Rezept
    st.session_state.auto_upload_done = False
    
    # NICHT zurücksetzen: mealie_connection_status, auto_upload


# =============================================================================
# UI KOMPONENTEN
# =============================================================================
def render_sidebar(config):
    """
    Rendert die Sidebar mit Einstellungen und Statusanzeigen.
    
    Args:
        config: AppConfig Instanz
        
    Returns:
        str: Ausgewähltes KI-Modell
    """
    with st.sidebar:
        st.header("⚙️ Einstellungen")
        
        # Modell-Auswahl
        selected_model = st.selectbox(
            "🤖 KI-Modell",
            options=config.gemini.available_models,
            index=0,
            help="Wähle ein anderes Modell falls eines nicht verfügbar ist"
        )
        st.caption("💡 Tipp: Bei Quota-Fehlern ein anderes Modell probieren")
        
        st.divider()
        
        # URL-Hinweise
        st.markdown("**🔗 Unterstützte Plattformen:**")
        st.caption("• TikTok")
        st.caption("• Instagram Reels")
        st.caption("• YouTube (Shorts)")
        st.caption("• Facebook")
        st.caption("• Twitter/X")
        
        st.divider()
        
        # Video-Hinweise
        st.markdown("**📹 Video-Hinweise:**")
        st.caption(f"• Max. {config.max_video_duration_minutes} Minuten empfohlen")
        st.caption(f"• Formate: {', '.join(config.supported_video_formats).upper()}")
        st.caption("• Braucht mehr Zeit & Quota")
        
        st.divider()
        
        # Verbindungsstatus (lazy - nur auf Klick prüfen für schnelleres Laden)
        st.markdown("**🔗 Verbindungen:**")
        
        # Verbindungsstatus aus Cache laden oder Button anzeigen
        if "mealie_connection_status" not in st.session_state:
            st.session_state.mealie_connection_status = None
        
        if st.session_state.mealie_connection_status is None:
            if st.button("🔌 Verbindung prüfen", key="check_connection", use_container_width=True):
                with st.spinner("Prüfe..."):
                    mealie_client = MealieClient()
                    success, message = mealie_client.test_connection()
                    st.session_state.mealie_connection_status = (success, message)
                st.rerun()
            st.caption("Tippe zum Prüfen der Mealie-Verbindung")
        else:
            success, message = st.session_state.mealie_connection_status
            if success:
                st.success("Mealie: ✅")
                st.caption(message)
            else:
                st.error("Mealie: ❌")
                st.caption(message)
            if st.button("🔄 Neu prüfen", key="recheck_connection", use_container_width=True):
                st.session_state.mealie_connection_status = None
                st.rerun()
        
        return selected_model


def render_file_upload(config):
    """
    Rendert die File-Upload Tabs mit URL als Default-Tab.
    
    Unterstützte Eingabemethoden:
    - URL: TikTok, Instagram, YouTube, Facebook, Twitter/X
    - Foto: Kochbuch-Seiten fotografieren
    - PDF: Rezept-PDFs hochladen
    - Video: Lokale Video-Dateien
    
    Args:
        config: AppConfig Instanz
    """
    # URL-Tab zuerst für Default (häufigste Nutzung)
    tab_url, tab_photo, tab_pdf, tab_video = st.tabs([
        "🔗 URL (TikTok, Insta...)", 
        "📷 Foto (Kochbuch)", 
        "📄 PDF", 
        "📹 Video Upload"
    ])
    
    with tab_url:
        st.markdown("Füge einen Link zu einem Rezept-Video ein:")
        
        # Form für Enter-Unterstützung
        with st.form(key="url_form", clear_on_submit=False):
            url_input = st.text_input(
                "Video-URL",
                placeholder="https://www.tiktok.com/@user/video/123... oder Instagram/YouTube Link",
                key="url_input",
                label_visibility="collapsed"
            )
            
            # Button und Auto-Upload Option nebeneinander
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                download_btn = st.form_submit_button("📥 Video laden", use_container_width=True)
            with col2:
                auto_upload_checkbox = st.checkbox(
                    "⚡ Auto-Upload",
                    value=st.session_state.get("auto_upload", False),
                    help="Rezept automatisch in Mealie speichern nach Analyse"
                )
        
        # Auto-Upload Status außerhalb des Forms aktualisieren
        if auto_upload_checkbox != st.session_state.get("auto_upload", False):
            st.session_state.auto_upload = auto_upload_checkbox
        
        if download_btn and url_input:
            if not is_supported_url(url_input):
                st.error("❌ Nicht unterstützte URL. Bitte TikTok, Instagram, YouTube, Facebook oder Twitter/X Link verwenden.")
            else:
                try:
                    with st.spinner("⬇️ Lade Video herunter..."):
                        video_info = download_video_from_url(
                            url_input, 
                            max_duration_minutes=config.max_video_duration_minutes
                        )
                    
                    # In Session State speichern
                    st.session_state.file_bytes = video_info.video_data
                    st.session_state.last_filename = f"video_from_{video_info.platform.lower()}.mp4"
                    st.session_state.file_type = "url_video"
                    st.session_state.video_caption = video_info.caption
                    st.session_state.video_info = video_info
                    st.session_state.recipe_json = None
                    st.session_state.processing_error = None
                    st.session_state.auto_upload_done = False  # Reset für neues Video
                    
                    st.success(f"✅ Video von {video_info.platform} geladen!")
                    logger.info(f"Video geladen: {video_info.platform}, {video_info.duration}s")
                    st.rerun()
                    
                except URLError as e:
                    st.error(f"❌ {e}")
                    logger.error(f"URL-Fehler: {e}")
        
        # Zeige geladenes Video
        if st.session_state.file_type == "url_video" and st.session_state.video_info:
            info = st.session_state.video_info
            
            st.divider()
            # Dauer formatieren
            duration_text = ""
            if info.duration:
                mins, secs = divmod(info.duration, 60)
                duration_text = f" ({mins}:{secs:02d})"
            
            # Info Expander (default ausgeklappt)
            with st.expander(f"ℹ️ Video-Info: {info.platform}{duration_text}", expanded=True):
                st.markdown(format_video_info_for_display(info))
            
            # Video Expander
            with st.expander("🎬 Video-Vorschau", expanded=False):
                st.video(st.session_state.file_bytes)
            
            # Caption Expander (nur wenn vorhanden)
            if info.caption:
                with st.expander("📝 Caption / Beschreibung", expanded=False):
                    st.text(info.caption[:1000] + ("..." if len(info.caption) > 1000 else ""))
    
    with tab_photo:
        st.markdown("Fotografiere ein Rezept aus einem Kochbuch oder einer Zeitschrift:")
        st.caption("💡 Du kannst mehrere Bilder hochladen (z.B. Seite mit Zutaten + Seite mit Anleitung)")
        
        uploaded_photos = st.file_uploader(
            "Rezept-Fotos hochladen",
            type=["jpg", "jpeg", "png", "webp"],
            key="photo_uploader",
            accept_multiple_files=True
        )
        
        if uploaded_photos:
            # Prüfen ob sich die Auswahl geändert hat
            current_names = tuple(sorted(p.name for p in uploaded_photos))
            if st.session_state.get("photo_names") != current_names:
                # Alle Bilder laden
                st.session_state.photo_images = [p.read() for p in uploaded_photos]
                st.session_state.photo_names = current_names
                st.session_state.last_filename = uploaded_photos[0].name
                st.session_state.file_type = "photos"  # Plural!
                st.session_state.recipe_json = None
                st.session_state.processing_error = None
                st.session_state.video_caption = None
                st.session_state.video_info = None
                st.session_state.best_image_index = 0
                st.session_state.auto_upload_done = False
                # Für Kompatibilität: erstes Bild in file_bytes
                st.session_state.file_bytes = st.session_state.photo_images[0]
            
            # Bild-Vorschau - alle Bilder anzeigen
            if len(st.session_state.photo_images) == 1:
                st.image(st.session_state.photo_images[0], caption="Hochgeladenes Rezept-Foto", use_container_width=True)
            else:
                st.info(f"📷 {len(st.session_state.photo_images)} Bilder hochgeladen")
                cols = st.columns(min(3, len(st.session_state.photo_images)))
                for i, img_bytes in enumerate(st.session_state.photo_images):
                    with cols[i % 3]:
                        st.image(img_bytes, caption=f"Bild {i+1}", use_container_width=True)
    
    with tab_pdf:
        uploaded_pdf = st.file_uploader(
            "Rezept-PDF hochladen",
            type=config.supported_document_formats,
            key="pdf_uploader"
        )
        
        if uploaded_pdf is not None:
            if st.session_state.last_filename != uploaded_pdf.name:
                st.session_state.file_bytes = uploaded_pdf.read()
                st.session_state.last_filename = uploaded_pdf.name
                st.session_state.file_type = "pdf"
                st.session_state.recipe_json = None
                st.session_state.processing_error = None
                st.session_state.video_caption = None
                st.session_state.video_info = None
                st.session_state.auto_upload_done = False
    
    with tab_video:
        uploaded_video = st.file_uploader(
            f"Rezept-Video hochladen (max. {config.max_video_duration_minutes} Min)",
            type=config.supported_video_formats,
            key="video_uploader"
        )
        
        if uploaded_video is not None:
            if st.session_state.last_filename != uploaded_video.name:
                st.session_state.file_bytes = uploaded_video.read()
                st.session_state.last_filename = uploaded_video.name
                st.session_state.file_type = "video"
                st.session_state.recipe_json = None
                st.session_state.processing_error = None
                st.session_state.video_caption = None
                st.session_state.video_info = None
                st.session_state.auto_upload_done = False
            
            # Video-Vorschau
            with st.expander(f"📹 Video: {st.session_state.last_filename}", expanded=False):
                st.video(st.session_state.file_bytes)


# =============================================================================
# VERARBEITUNGSLOGIK
# =============================================================================
def process_file(selected_model: str):
    """
    Verarbeitet die hochgeladene Datei mit der Gemini KI.
    
    Je nach file_type wird die entsprechende Extraktionsmethode aufgerufen:
    - pdf: Text extrahieren → KI analysieren
    - photo/photos: Bild(er) direkt an KI senden
    - video/url_video: Video an KI senden (mit optionaler Caption)
    
    Args:
        selected_model: Name des zu verwendenden Gemini-Modells
    
    Setzt bei Erfolg: st.session_state.recipe_json
    Setzt bei Fehler: st.session_state.processing_error
    """
    # Nichts zu tun wenn keine Datei oder bereits verarbeitet
    if not st.session_state.file_bytes or st.session_state.recipe_json is not None:
        return
    
    gemini_client = GeminiClient()
    
    # Callback für Modellwechsel (wird bei Quota-Fehlern aufgerufen)
    def on_model_switch(new_model: str, reason: str):
        st.session_state.model_switches.append({"model": new_model, "reason": reason})
        st.toast(f"⚠️ {reason} → Wechsle zu {new_model}", icon="🔄")
    
    try:
        if st.session_state.file_type == "pdf":
            # PDF: Erst Text extrahieren, dann KI analysieren
            with st.spinner("🔍 Extrahiere Text aus PDF..."):
                raw_text = extract_text_from_pdf(st.session_state.file_bytes)
            
            with st.expander("📜 Extrahierter Text (Debug)", expanded=False):
                display_text = raw_text[:2000] + "..." if len(raw_text) > 2000 else raw_text
                st.text(display_text)
            
            with st.spinner("🤖 Frage Gemini KI..."):
                recipe, used_model = gemini_client.extract_recipe_from_text(
                    raw_text, selected_model, on_model_switch=on_model_switch
                )
                st.session_state.recipe_json = recipe
                st.session_state.used_model = used_model
        
        elif st.session_state.file_type == "photo":
            # Einzelnes Foto
            with st.spinner("🤖 Analysiere Foto mit KI..."):
                recipe, used_model = gemini_client.extract_recipe_from_image(
                    st.session_state.file_bytes, 
                    selected_model,
                    on_model_switch=on_model_switch
                )
                st.session_state.recipe_json = recipe
                st.session_state.used_model = used_model
        
        elif st.session_state.file_type == "photos":
            # Mehrere Bilder (z.B. mehrseitiges Kochbuch-Rezept)
            num_images = len(st.session_state.photo_images)
            with st.spinner(f"🤖 Analysiere {num_images} Foto(s) mit KI..."):
                recipe, used_model, best_idx = gemini_client.extract_recipe_from_images(
                    st.session_state.photo_images, 
                    selected_model,
                    on_model_switch=on_model_switch
                )
                st.session_state.recipe_json = recipe
                st.session_state.used_model = used_model
                st.session_state.best_image_index = best_idx
                # Das beste Bild für Mealie speichern
                st.session_state.file_bytes = st.session_state.photo_images[best_idx]
                if num_images > 1:
                    st.info(f"📷 KI hat Bild {best_idx + 1} als Rezeptbild ausgewählt")
        
        elif st.session_state.file_type in ["video", "url_video"]:
            # Video-Analyse (dauert länger)
            status_placeholder = st.empty()
            
            def update_status(message):
                status_placeholder.info(message)
            
            # Caption von URL-Videos verwenden (enthält oft Mengenangaben)
            caption = st.session_state.video_caption if st.session_state.file_type == "url_video" else None
            
            with st.spinner("🎬 Analysiere Video (kann 1-2 Minuten dauern)..."):
                recipe, used_model = gemini_client.extract_recipe_from_video(
                    st.session_state.file_bytes,
                    st.session_state.last_filename,
                    selected_model,
                    caption=caption,
                    progress_callback=update_status,
                    on_model_switch=on_model_switch
                )
                st.session_state.recipe_json = recipe
                st.session_state.used_model = used_model
            
            status_placeholder.empty()
            
    except (GeminiError, PDFError) as e:
        st.session_state.processing_error = str(e)
        st.error(f"❌ {e}")
        logger.error(f"Verarbeitungsfehler: {e}")


def auto_save_to_mealie(recipe: dict) -> bool:
    """
    Speichert das Rezept automatisch in Mealie (für Auto-Upload Feature).
    
    Args:
        recipe: Extrahiertes Rezept als Dictionary
        
    Returns:
        True wenn erfolgreich, False bei Fehler
    """
    try:
        mealie_client = MealieClient()
        
        # Thumbnail und Source-URL vorbereiten
        thumbnail_data = None
        source_url = None
        
        if st.session_state.file_type == "url_video" and st.session_state.video_info:
            video_info = st.session_state.video_info
            source_url = video_info.original_url
            thumbnail_data = video_info.thumbnail_data
        elif st.session_state.file_type in ["photo", "photos"]:
            thumbnail_data = st.session_state.file_bytes
        
        success, message = mealie_client.create_recipe(
            recipe,
            thumbnail_data=thumbnail_data,
            source_url=source_url
        )
        
        if success:
            logger.info(f"Auto-Upload erfolgreich: {message}")
            return True
        else:
            logger.error(f"Auto-Upload fehlgeschlagen: {message}")
            return False
            
    except Exception as e:
        logger.error(f"Auto-Upload Fehler: {e}")
        return False


def render_recipe_preview(recipe: dict):
    """
    Rendert die Rezept-Vorschau mit allen Details.
    
    Zeigt an:
    - Rezeptname und Beschreibung
    - Portionsangabe
    - Zutatenliste (aufklappbar)
    - Zubereitungsschritte (aufklappbar)
    - JSON-Vorschau für Debugging
    
    Args:
        recipe: Extrahiertes Rezept als Dictionary
    """
    st.success(f"✅ Rezept erkannt: **{recipe.get('name', 'Unbekannt')}**")
    
    # Modellwechsel-Hinweise anzeigen (falls Fallback nötig war)
    if st.session_state.model_switches:
        for switch in st.session_state.model_switches:
            st.warning(f"⚠️ {switch['reason']} → Verwendet: **{switch['model']}**")
    
    # Verwendetes Modell anzeigen
    if st.session_state.used_model:
        st.caption(f"🤖 Analysiert mit: {st.session_state.used_model}")
    
    # Beschreibung
    if recipe.get('description'):
        st.info(recipe['description'])
    
    # Portionen
    st.caption(f"📊 {recipe.get('recipeYield', '1 Portion')}")
    
    # Details in Expander (für übersichtliche UI)
    ingredients = recipe.get('recipeIngredient', [])
    instructions = recipe.get('recipeInstructions', [])
    
    with st.expander(f"🥕 Zutaten ({len(ingredients)} Stück)", expanded=False):
        for ing in ingredients:
            if isinstance(ing, dict):
                qty = ing.get('quantity', '')
                unit = ing.get('unit', '')
                food = ing.get('food', '')
                note = ing.get('note', '')
                
                parts = []
                if qty:
                    parts.append(str(qty))
                if unit:
                    parts.append(unit)
                if food:
                    parts.append(food)
                
                display = " ".join(parts) if parts else note
                if note and food:
                    display += f" ({note})"
                
                st.write(f"• {display}")
            else:
                st.write(f"• {ing}")
    
    with st.expander(f"👨‍🍳 Zubereitung ({len(instructions)} Schritte)", expanded=False):
        for i, step in enumerate(instructions, 1):
            text = step.get('text', step) if isinstance(step, dict) else step
            st.write(f"**{i}.** {text}")
    
    # JSON Vorschau für Debugging/Entwicklung
    with st.expander("🔧 JSON Vorschau (für Mealie)", expanded=False):
        st.json(recipe)


def render_action_buttons(recipe: dict):
    """
    Rendert die Aktions-Buttons für Speichern und Neu-Analyse.
    
    Args:
        recipe: Extrahiertes Rezept als Dictionary
    """
    st.divider()
    
    col_btn1, col_btn2 = st.columns(2)
    
    with col_btn1:
        if st.button("🚀 In Mealie speichern", use_container_width=True, type="primary"):
            mealie_client = MealieClient()
            
            # Thumbnail und Source-URL holen
            thumbnail_data = None
            source_url = None
            
            if st.session_state.file_type == "url_video" and st.session_state.video_info:
                video_info = st.session_state.video_info
                source_url = video_info.original_url
                thumbnail_data = video_info.thumbnail_data
                    
            elif st.session_state.file_type in ["photo", "photos"]:
                # Bei Fotos: das beste Bild als Rezeptbild nehmen
                thumbnail_data = st.session_state.file_bytes
            
            with st.spinner("Speichere in Mealie..."):
                success, message = mealie_client.create_recipe(
                    recipe, 
                    thumbnail_data=thumbnail_data,
                    source_url=source_url
                )
            
            if success:
                st.balloons()
                st.success(f"✅ Erfolgreich gespeichert! Slug: {message}")
                logger.info(f"Rezept gespeichert: {message}")
                reset_session_state()
            else:
                st.error(f"❌ {message}")
                logger.error(f"Speichern fehlgeschlagen: {message}")
    
    with col_btn2:
        if st.button("🔄 Neu analysieren", use_container_width=True):
            st.session_state.recipe_json = None
            st.session_state.processing_error = None
            st.session_state.auto_upload_done = False
            st.rerun()


def render_footer(config, selected_model: str):
    """
    Rendert den Footer mit Verbindungsinfo und Version.
    
    Args:
        config: AppConfig Instanz
        selected_model: Aktuell ausgewähltes KI-Modell
    """
    st.divider()
    col_footer1, col_footer2 = st.columns([2, 1])
    
    with col_footer1:
        st.caption(f"v{__version__} | 🔗 Mealie: `{config.mealie.url}` | 🤖 Modell: `{selected_model}`")
    
    with col_footer2:
        if st.button("🔋 Quota prüfen", use_container_width=True):
            gemini_client = GeminiClient()
            with st.spinner("Prüfe..."):
                ok, msg = gemini_client.check_quota(selected_model)
            if ok:
                st.success(msg)
            else:
                st.error(msg)
                st.markdown("[📊 Quota-Details bei Google](https://aistudio.google.com/app/apikey)")


# =============================================================================
# HAUPTFUNKTION
# =============================================================================
def main():
    """
    Hauptfunktion der Streamlit App.
    
    Ablauf:
    1. Konfiguration laden und validieren
    2. UI initialisieren (Page Config, Session State)
    3. Sidebar mit Einstellungen rendern
    4. File-Upload Tabs anzeigen
    5. Datei verarbeiten (wenn vorhanden)
    6. Rezept-Vorschau und Aktionen anzeigen
    7. Auto-Upload ausführen (wenn aktiviert)
    """
    # Konfiguration laden
    config = get_config()
    
    # Seite konfigurieren
    st.set_page_config(
        page_title="Mealie Importer",
        page_icon="🍳",
        layout="centered"
    )
    
    # Mobile/Safari Optimierungen für bessere Performance auf iOS
    st.markdown("""
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <style>
            /* Bessere Mobile Performance */
            .stApp {
                -webkit-overflow-scrolling: touch;
            }
            /* Verhindere Layout-Shifts beim Laden */
            .element-container {
                min-height: 1px;
            }
            /* Optimierte Touch-Targets für Mobile (Apple HIG: min 44px) */
            .stButton button {
                min-height: 44px;
                touch-action: manipulation;
            }
            /* Safari/iOS Fix für Flexbox */
            .main .block-container {
                -webkit-flex: 1;
                flex: 1;
            }
        </style>
    """, unsafe_allow_html=True)
    
    # Session State initialisieren
    init_session_state()
    
    # Header mit Version
    st.title(config.app_title)
    st.caption("Lade ein PDF oder Video mit einem Rezept hoch und importiere es automatisch in Mealie.")
    
    # Konfigurationsfehler anzeigen
    config_errors = config.validate()
    if config_errors:
        st.error("⚠️ Konfigurationsfehler:")
        for error in config_errors:
            st.warning(f"• {error}")
        st.info("Bitte setze die Umgebungsvariablen in der .env Datei.")
        st.stop()
    
    # Sidebar rendern
    selected_model = render_sidebar(config)
    
    # File Upload Tabs anzeigen
    render_file_upload(config)
    
    # Datei verarbeiten (wenn vorhanden und noch nicht analysiert)
    process_file(selected_model)
    
    # Rezept anzeigen
    if st.session_state.recipe_json:
        # Auto-Upload prüfen (nur einmal pro Rezept)
        if st.session_state.get("auto_upload") and not st.session_state.get("auto_upload_done"):
            st.session_state.auto_upload_done = True
            with st.spinner("⚡ Auto-Upload zu Mealie..."):
                if auto_save_to_mealie(st.session_state.recipe_json):
                    # Erfolg! Ballons und Bestätigung anzeigen
                    st.balloons()
                    st.success(f"✅ **{st.session_state.recipe_json.get('name', 'Rezept')}** automatisch in Mealie gespeichert!")
                    
                    # Button für nächstes Rezept (statt sofortigem rerun)
                    if st.button("🆕 Nächstes Rezept importieren", use_container_width=True, type="primary"):
                        reset_session_state()
                        st.rerun()
                    return  # Nicht weiter rendern, User soll Erfolg genießen
                else:
                    st.error("❌ Auto-Upload fehlgeschlagen. Bitte manuell speichern.")
        
        render_recipe_preview(st.session_state.recipe_json)
        render_action_buttons(st.session_state.recipe_json)
    elif not st.session_state.file_bytes:
        st.info("👆 Wähle oben einen Tab und lade eine PDF oder ein Video hoch.")
    
    # Footer mit Version
    render_footer(config, selected_model)


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    main()
