"""
Mealie Recipe Importer - Streamlit Web Application

Eine Webanwendung zum Importieren von Rezepten aus PDFs und Videos
in die Mealie Rezeptverwaltung mittels Google Gemini KI.
"""

import streamlit as st
import logging
import os
from pathlib import Path

# .env Datei laden
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
    format_video_info_for_display,
    extract_frame_from_video
)

# Logging für Streamlit
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_session_state():
    """Initialisiert den Streamlit Session State."""
    defaults = {
        "recipe_json": None,
        "file_bytes": None,
        "last_filename": None,
        "file_type": None,
        "processing_error": None,
        "video_caption": None,
        "video_info": None,
        "used_model": None,
        "model_switches": [],
        "photo_images": [],
        "photo_names": None,
        "best_image_index": 0,
        "best_frame_timestamp": 0,
        "best_frame_data": None
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_session_state():
    """Setzt den Session State zurück."""
    st.session_state.recipe_json = None
    st.session_state.file_bytes = None
    st.session_state.last_filename = None
    st.session_state.file_type = None
    st.session_state.processing_error = None
    st.session_state.video_caption = None
    st.session_state.video_info = None
    st.session_state.used_model = None
    st.session_state.model_switches = []
    st.session_state.photo_images = []
    st.session_state.photo_names = None
    st.session_state.best_image_index = 0
    st.session_state.best_frame_timestamp = 0
    st.session_state.best_frame_data = None


def render_sidebar(config):
    """Rendert die Sidebar mit Einstellungen."""
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
        
        # Verbindungsstatus
        st.markdown("**🔗 Verbindungen:**")
        
        # Mealie Status
        mealie_client = MealieClient()
        success, message = mealie_client.test_connection()
        if success:
            st.success(f"Mealie: ✅")
            st.caption(message)
        else:
            st.error(f"Mealie: ❌")
            st.caption(message)
        
        return selected_model


def render_file_upload(config):
    """Rendert die File-Upload Tabs mit URL als Default."""
    # URL-Tab zuerst für Default
    tab_url, tab_photo, tab_pdf, tab_video = st.tabs(["🔗 URL (TikTok, Insta...)", "📷 Foto (Kochbuch)", "📄 PDF", "📹 Video Upload"])
    
    with tab_url:
        st.markdown("Füge einen Link zu einem Rezept-Video ein:")
        
        url_input = st.text_input(
            "Video-URL",
            placeholder="https://www.tiktok.com/@user/video/123... oder Instagram/YouTube Link",
            key="url_input",
            label_visibility="collapsed"
        )
        
        col1, col2 = st.columns([1, 4])
        with col1:
            download_btn = st.button("📥 Video laden", use_container_width=True)
        
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
                    
                    st.success(f"✅ Video von {video_info.platform} geladen!")
                    st.rerun()
                    
                except URLError as e:
                    st.error(f"❌ {e}")
        
        # Zeige geladenes Video
        if st.session_state.file_type == "url_video" and st.session_state.video_info:
            info = st.session_state.video_info
            
            st.divider()
            st.markdown(format_video_info_for_display(info))
            
            # Video-Vorschau
            st.video(st.session_state.file_bytes)
            
            # Caption anzeigen
            if info.caption:
                with st.expander("📝 Caption / Beschreibung", expanded=True):
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
            
            # Video-Vorschau
            st.video(st.session_state.file_bytes)


def process_file(selected_model):
    """Verarbeitet die hochgeladene Datei."""
    if not st.session_state.file_bytes or st.session_state.recipe_json is not None:
        return
    
    gemini_client = GeminiClient()
    
    # Callback für Modellwechsel
    def on_model_switch(new_model: str, reason: str):
        st.session_state.model_switches.append({"model": new_model, "reason": reason})
        st.toast(f"⚠️ {reason} → Wechsle zu {new_model}", icon="🔄")
    
    try:
        if st.session_state.file_type == "pdf":
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
            with st.spinner("🤖 Analysiere Foto mit KI..."):
                recipe, used_model = gemini_client.extract_recipe_from_image(
                    st.session_state.file_bytes, 
                    selected_model,
                    on_model_switch=on_model_switch
                )
                st.session_state.recipe_json = recipe
                st.session_state.used_model = used_model
        
        elif st.session_state.file_type == "photos":
            # Mehrere Bilder
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
            status_placeholder = st.empty()
            
            def update_status(message):
                status_placeholder.info(message)
            
            # Caption von URL-Videos verwenden
            caption = st.session_state.video_caption if st.session_state.file_type == "url_video" else None
            
            with st.spinner("🎬 Analysiere Video (kann 1-2 Minuten dauern)..."):
                recipe, used_model, best_timestamp = gemini_client.extract_recipe_from_video(
                    st.session_state.file_bytes,
                    st.session_state.last_filename,
                    selected_model,
                    caption=caption,
                    progress_callback=update_status,
                    on_model_switch=on_model_switch
                )
                st.session_state.recipe_json = recipe
                st.session_state.used_model = used_model
                st.session_state.best_frame_timestamp = best_timestamp
            
            # Besten Frame als Bild extrahieren (statt Thumbnail)
            if best_timestamp > 0:
                update_status(f"🖼️ Extrahiere Rezeptbild bei {best_timestamp}s...")
                frame_data = extract_frame_from_video(
                    st.session_state.file_bytes, 
                    best_timestamp
                )
                if frame_data:
                    st.session_state.best_frame_data = frame_data
                    st.info(f"📷 KI hat Frame bei {best_timestamp}s als Rezeptbild ausgewählt")
            
            status_placeholder.empty()
            
    except (GeminiError, PDFError) as e:
        st.session_state.processing_error = str(e)
        st.error(f"❌ {e}")


def render_recipe_preview(recipe):
    """Rendert die Rezept-Vorschau."""
    st.success(f"✅ Rezept erkannt: **{recipe.get('name', 'Unbekannt')}**")
    
    # Modellwechsel-Hinweise anzeigen
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
    
    # Details in Spalten
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🥕 Zutaten")
        ingredients = recipe.get('recipeIngredient', [])
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
    
    with col2:
        st.subheader("👨‍🍳 Zubereitung")
        instructions = recipe.get('recipeInstructions', [])
        for i, step in enumerate(instructions, 1):
            text = step.get('text', step) if isinstance(step, dict) else step
            st.write(f"**{i}.** {text}")
    
    # JSON Vorschau
    with st.expander("🔧 JSON Vorschau (für Mealie)", expanded=False):
        st.json(recipe)


def render_action_buttons(recipe):
    """Rendert die Aktions-Buttons."""
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
                
                # KI-ausgewählten Frame bevorzugen, sonst Thumbnail
                if st.session_state.best_frame_data:
                    thumbnail_data = st.session_state.best_frame_data
                else:
                    thumbnail_data = video_info.thumbnail_data
                    
            elif st.session_state.file_type == "video":
                # Video-Upload ohne URL
                if st.session_state.best_frame_data:
                    thumbnail_data = st.session_state.best_frame_data
                    
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
                reset_session_state()
            else:
                st.error(f"❌ {message}")
    
    with col_btn2:
        if st.button("🔄 Neu analysieren", use_container_width=True):
            st.session_state.recipe_json = None
            st.session_state.processing_error = None
            st.rerun()


def render_footer(config, selected_model):
    """Rendert den Footer."""
    st.divider()
    col_footer1, col_footer2 = st.columns([2, 1])
    
    with col_footer1:
        st.caption(f"🔗 Mealie: `{config.mealie.url}` | 🤖 Modell: `{selected_model}`")
    
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


def main():
    """Hauptfunktion der Streamlit App."""
    # Konfiguration laden
    config = get_config()
    
    # Seite konfigurieren
    st.set_page_config(
        page_title="Mealie Importer",
        page_icon="🍳",
        layout="centered"
    )
    
    # Session State initialisieren
    init_session_state()
    
    # Header
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
    
    # File Upload
    render_file_upload(config)
    
    # Datei verarbeiten
    process_file(selected_model)
    
    # Rezept anzeigen
    if st.session_state.recipe_json:
        render_recipe_preview(st.session_state.recipe_json)
        render_action_buttons(st.session_state.recipe_json)
    elif not st.session_state.file_bytes:
        st.info("👆 Wähle oben einen Tab und lade eine PDF oder ein Video hoch.")
    
    # Footer
    render_footer(config, selected_model)


if __name__ == "__main__":
    main()
