"""
URL Processor für TikTok, Instagram und YouTube Videos.
Nutzt yt-dlp zum Herunterladen von Videos und Extrahieren von Metadaten.
"""

import subprocess
import json
import tempfile
import os
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class URLError(Exception):
    """Fehler beim Verarbeiten einer URL."""
    message: str
    
    def __str__(self):
        return f"URL Fehler: {self.message}"


@dataclass
class VideoInfo:
    """Informationen über ein heruntergeladenes Video."""
    video_data: bytes
    caption: str
    title: str
    uploader: str
    platform: str
    original_url: str
    duration: Optional[int] = None  # in Sekunden
    thumbnail_data: Optional[bytes] = None  # Thumbnail als Bytes


def detect_platform(url: str) -> str:
    """Erkennt die Plattform anhand der URL."""
    url_lower = url.lower()
    
    if "tiktok.com" in url_lower:
        return "TikTok"
    elif "instagram.com" in url_lower:
        return "Instagram"
    elif "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "YouTube"
    elif "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "Facebook"
    elif "twitter.com" in url_lower or "x.com" in url_lower:
        return "Twitter/X"
    else:
        return "Unbekannt"


def is_supported_url(url: str) -> bool:
    """Prüft ob die URL von einer unterstützten Plattform ist."""
    supported = [
        "tiktok.com",
        "instagram.com",
        "youtube.com",
        "youtu.be",
        "facebook.com",
        "fb.watch",
        "twitter.com",
        "x.com"
    ]
    url_lower = url.lower()
    return any(platform in url_lower for platform in supported)


def download_video_from_url(url: str, max_duration_minutes: int = 10) -> VideoInfo:
    """
    Lädt ein Video von einer URL herunter und extrahiert Metadaten.
    
    Args:
        url: Die Video-URL (TikTok, Instagram, YouTube, etc.)
        max_duration_minutes: Maximale Videolänge in Minuten
        
    Returns:
        VideoInfo mit Video-Daten und Metadaten
        
    Raises:
        URLError: Bei Fehlern beim Download oder wenn Video zu lang
    """
    platform = detect_platform(url)
    logger.info(f"Lade Video von {platform}: {url}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Fester Output-Name um lange Titel zu vermeiden
        output_path = os.path.join(tmpdir, "video.mp4")
        
        # yt-dlp Kommando - einfach und robust
        cmd = [
            "yt-dlp",
            "--no-warnings",
            "--no-playlist",  # Keine Playlists
            "-o", output_path,
            "--write-info-json",
            "--write-thumbnail",  # Thumbnail herunterladen
            "--format", "best[ext=mp4]/mp4/best",  # Bevorzuge MP4
            url
        ]
        
        logger.info(f"Führe aus: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                timeout=300  # 5 Minuten Timeout
            )
        except subprocess.TimeoutExpired:
            raise URLError("Download-Timeout überschritten (5 Minuten)")
        except FileNotFoundError:
            raise URLError("yt-dlp ist nicht installiert. Bitte installieren Sie es mit: pip install yt-dlp")
        
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unbekannter Fehler"
            logger.error(f"yt-dlp Fehler: {error_msg}")
            
            # Bekannte Fehler übersetzen
            if "Video unavailable" in error_msg:
                raise URLError("Video nicht verfügbar oder privat")
            elif "Sign in" in error_msg or "login" in error_msg.lower():
                raise URLError("Video erfordert Anmeldung - nicht öffentlich zugänglich")
            elif "not found" in error_msg.lower() or "404" in error_msg:
                raise URLError("Video nicht gefunden - Link möglicherweise ungültig")
            else:
                raise URLError(f"Download fehlgeschlagen: {error_msg[:200]}")
        
        # Debug: Zeige alle Dateien im Verzeichnis
        all_files = list(Path(tmpdir).iterdir())
        logger.info(f"Dateien im Download-Ordner: {[f.name for f in all_files]}")
        
        # Info-JSON finden und lesen
        info_files = list(Path(tmpdir).glob("*.info.json"))
        if not info_files:
            raise URLError(f"Keine Metadaten gefunden. Dateien: {[f.name for f in all_files]}")
        
        with open(info_files[0], "r", encoding="utf-8") as f:
            info = json.load(f)
        
        # Videolänge prüfen
        duration = info.get("duration", 0)
        if duration and duration > max_duration_minutes * 60:
            raise URLError(
                f"Video ist zu lang ({duration // 60} Min). "
                f"Maximum: {max_duration_minutes} Minuten"
            )
        
        # Video-Datei finden (NICHT die .json Dateien!)
        video_extensions = ['.mp4', '.webm', '.mkv', '.mov', '.avi']
        video_files = [
            f for f in Path(tmpdir).iterdir() 
            if f.suffix.lower() in video_extensions
            and '.info' not in f.name  # Keine info.json Dateien
        ]
        
        if not video_files:
            # Fallback: Suche nach video.mp4 explizit
            video_mp4 = Path(tmpdir) / "video.mp4"
            if video_mp4.exists():
                video_files = [video_mp4]
            else:
                raise URLError(f"Keine Videodatei gefunden. Dateien: {[f.name for f in all_files]}")
        
        video_path = video_files[0]
        file_size_mb = video_path.stat().st_size / 1024 / 1024
        logger.info(f"Video gefunden: {video_path.name} ({file_size_mb:.1f} MB)")
        
        if file_size_mb < 0.01:
            raise URLError(f"Video-Datei ist leer oder zu klein: {video_path.name}")
        
        # Video-Bytes lesen
        with open(video_path, "rb") as f:
            video_data = f.read()
        
        # Thumbnail suchen - auch Dateien ohne Extension wie "video.image"
        thumbnail_data = None
        thumbnail_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.image']
        thumbnail_files = [
            f for f in Path(tmpdir).iterdir()
            if f.suffix.lower() in thumbnail_extensions
            or 'image' in f.name.lower()
            or 'thumb' in f.name.lower()
        ]
        # Filtere Video-Dateien raus
        thumbnail_files = [f for f in thumbnail_files if f.suffix.lower() not in ['.mp4', '.webm', '.mkv', '.json']]
        
        if thumbnail_files:
            thumbnail_path = thumbnail_files[0]
            logger.info(f"Thumbnail gefunden: {thumbnail_path.name} ({thumbnail_path.stat().st_size / 1024:.1f} KB)")
            with open(thumbnail_path, "rb") as f:
                thumbnail_data = f.read()
        else:
            logger.warning(f"Kein Thumbnail gefunden in: {[f.name for f in all_files]}")
        
        # Caption zusammenstellen
        caption = info.get("description", "") or ""
        
        # Bei TikTok ist der Titel oft die Caption
        title = info.get("title", "") or ""
        if not caption and title:
            caption = title
        
        # Hashtags extrahieren falls vorhanden
        tags = info.get("tags", [])
        if tags and isinstance(tags, list):
            hashtags = " ".join(f"#{tag}" for tag in tags[:10])
            if hashtags and hashtags not in caption:
                caption = f"{caption}\n\nHashtags: {hashtags}"
        
        return VideoInfo(
            video_data=video_data,
            caption=caption.strip(),
            title=title,
            uploader=info.get("uploader", "") or info.get("channel", "") or "",
            platform=platform,
            original_url=url,
            duration=duration,
            thumbnail_data=thumbnail_data
        )


def format_video_info_for_display(info: VideoInfo) -> str:
    """Formatiert VideoInfo für die Anzeige in der UI."""
    lines = [f"**Plattform:** {info.platform}"]
    
    if info.uploader:
        lines.append(f"**Ersteller:** {info.uploader}")
    
    if info.title:
        lines.append(f"**Titel:** {info.title}")
    
    if info.duration:
        minutes = info.duration // 60
        seconds = info.duration % 60
        lines.append(f"**Länge:** {minutes}:{seconds:02d}")
    
    return "\n\n".join(lines)


def extract_frame_from_video(video_data: bytes, timestamp_seconds: int) -> Optional[bytes]:
    """
    Extrahiert einen Frame aus einem Video bei einem bestimmten Zeitpunkt.
    
    Args:
        video_data: Video als Bytes
        timestamp_seconds: Zeitpunkt in Sekunden
        
    Returns:
        JPEG-Bild als Bytes oder None bei Fehler
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Video temporär speichern
        video_path = os.path.join(tmpdir, "video.mp4")
        output_path = os.path.join(tmpdir, "frame.jpg")
        
        with open(video_path, "wb") as f:
            f.write(video_data)
        
        # ffmpeg Kommando zum Frame-Extrahieren
        cmd = [
            "ffmpeg",
            "-y",  # Überschreiben ohne Nachfrage
            "-ss", str(timestamp_seconds),  # Zeitstempel
            "-i", video_path,
            "-frames:v", "1",  # Nur 1 Frame
            "-q:v", "2",  # Hohe Qualität
            output_path
        ]
        
        logger.info(f"Extrahiere Frame bei {timestamp_seconds}s...")
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                logger.warning(f"ffmpeg Fehler: {result.stderr}")
                return None
            
            # Frame lesen
            if os.path.exists(output_path):
                with open(output_path, "rb") as f:
                    frame_data = f.read()
                logger.info(f"Frame extrahiert: {len(frame_data)/1024:.1f} KB")
                return frame_data
            
        except subprocess.TimeoutExpired:
            logger.warning("Frame-Extraktion Timeout")
        except FileNotFoundError:
            logger.warning("ffmpeg nicht gefunden")
        except Exception as e:
            logger.warning(f"Frame-Extraktion fehlgeschlagen: {e}")
        
        return None
