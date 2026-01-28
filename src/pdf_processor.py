"""
PDF Verarbeitung für den Recipe Importer.
"""

import logging
from typing import Optional
import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PDFError(Exception):
    """Fehler bei der PDF-Verarbeitung."""
    pass


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extrahiert Text aus einem PDF-Bytestream.
    
    Args:
        file_bytes: PDF als Bytes
        
    Returns:
        Extrahierter Text
        
    Raises:
        PDFError: Bei Verarbeitungsfehlern
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text_parts = []
        
        for page_num, page in enumerate(doc):
            page_text = page.get_text()
            if page_text.strip():
                text_parts.append(page_text)
            logger.debug(f"Seite {page_num + 1}: {len(page_text)} Zeichen")
        
        doc.close()
        
        full_text = "\n".join(text_parts)
        
        if not full_text.strip():
            raise PDFError("PDF enthält keinen extrahierbaren Text")
            
        logger.info(f"PDF Text extrahiert: {len(full_text)} Zeichen")
        return full_text
        
    except fitz.FileDataError as e:
        raise PDFError(f"Ungültiges PDF-Format: {e}")
    except Exception as e:
        if isinstance(e, PDFError):
            raise
        raise PDFError(f"Fehler beim Lesen des PDFs: {e}")
