"""Audio transcription via Gemini multimodal (demo microphone).

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import List, Optional

from .config import GEMINI_25_FLASH, GEMINI_25_FLASH_LITE, GEMINI_MODEL, HAS_GEMINI, genai, logger

_ALLOWED_MIME = frozenset(
    {
        "audio/webm",
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/ogg",
        "audio/mp4",
        "audio/x-m4a",
    }
)

_SUFFIX_BY_MIME = {
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
}

_TRANSCRIBE_PROMPT = """Transcribe el audio a texto en español.
Devuelve únicamente la transcripción literal de lo dicho, sin comillas ni comentarios.
Si no hay voz inteligible, devuelve una cadena vacía."""


def normalize_audio_mime(mime_type: Optional[str]) -> str:
    raw = (mime_type or "audio/webm").split(";")[0].strip().lower()
    if raw in _ALLOWED_MIME:
        return raw
    if raw.startswith("audio/"):
        return raw
    return "audio/webm"


def transcribe_model_candidates(preferred: Optional[str] = None) -> List[str]:
    """Models to try, most compatible first for short browser recordings."""
    ordered = [
        os.getenv("TRANSCRIBE_MODEL", "").strip() or None,
        GEMINI_25_FLASH_LITE,
        GEMINI_25_FLASH,
        preferred,
        GEMINI_MODEL,
    ]
    seen: set[str] = set()
    out: List[str] = []
    for name in ordered:
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _response_text(response: object) -> str:
    try:
        text = getattr(response, "text", None)
        if text:
            return str(text).strip()
    except ValueError:
        pass

    candidates = getattr(response, "candidates", None) or []
    if candidates:
        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) if content else None
        if parts:
            chunks = []
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    chunks.append(str(part_text))
            if chunks:
                return "".join(chunks).strip()

    feedback = getattr(response, "prompt_feedback", None)
    if feedback is not None:
        block = getattr(feedback, "block_reason", None)
        if block:
            raise RuntimeError(f"Respuesta bloqueada por el modelo ({block})")

    raise RuntimeError("El modelo no devolvió texto de transcripción")


def _wait_file_active(uploaded: object, *, timeout_sec: float = 45.0) -> object:
    name = getattr(uploaded, "name", None)
    if not name:
        return uploaded

    deadline = time.time() + timeout_sec
    file_obj = uploaded
    while time.time() < deadline:
        state = getattr(getattr(file_obj, "state", None), "name", None)
        if state == "ACTIVE":
            return file_obj
        if state == "FAILED":
            raise RuntimeError("No se pudo procesar el audio en Gemini Files API")
        time.sleep(0.5)
        file_obj = genai.get_file(name)
    raise TimeoutError("Tiempo de espera agotado al subir el audio")


def _transcribe_with_upload(
    *,
    api_key: str,
    model_name: str,
    audio_bytes: bytes,
    mime: str,
) -> str:
    suffix = _SUFFIX_BY_MIME.get(mime, ".webm")
    tmp_path: Optional[str] = None
    uploaded = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            tmp_path = tmp.name

        uploaded = genai.upload_file(tmp_path, mime_type=mime)
        uploaded = _wait_file_active(uploaded)

        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            [_TRANSCRIBE_PROMPT, uploaded],
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )
        return _response_text(response)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        if uploaded is not None:
            file_name = getattr(uploaded, "name", None)
            if file_name:
                try:
                    genai.delete_file(file_name)
                except Exception:
                    logger.debug("Could not delete uploaded file %s", file_name)


def _transcribe_inline(
    *,
    api_key: str,
    model_name: str,
    audio_bytes: bytes,
    mime: str,
) -> str:
    model = genai.GenerativeModel(model_name)
    part = {"mime_type": mime, "data": audio_bytes}
    response = model.generate_content(
        [_TRANSCRIBE_PROMPT, part],
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=1024,
        ),
    )
    return _response_text(response)


def transcribe_audio(
    *,
    api_key: str,
    model_name: str,
    audio_bytes: bytes,
    mime_type: str,
) -> str:
    """Return Spanish transcript for short microphone recordings."""
    if not api_key:
        raise ValueError("GOOGLE_API_KEY required for transcription")
    if not audio_bytes:
        raise ValueError("Empty audio payload")
    if not HAS_GEMINI or genai is None:
        raise RuntimeError("google-generativeai is not installed")

    mime = normalize_audio_mime(mime_type)
    genai.configure(api_key=api_key)

    models = transcribe_model_candidates(model_name)
    last_error: Optional[Exception] = None

    for candidate in models:
        try:
            if len(audio_bytes) > 18 * 1024 * 1024:
                text = _transcribe_with_upload(
                    api_key=api_key,
                    model_name=candidate,
                    audio_bytes=audio_bytes,
                    mime=mime,
                )
            else:
                try:
                    text = _transcribe_with_upload(
                        api_key=api_key,
                        model_name=candidate,
                        audio_bytes=audio_bytes,
                        mime=mime,
                    )
                except Exception as upload_exc:
                    logger.warning(
                        "Upload transcription failed (%s), trying inline: %s",
                        candidate,
                        upload_exc,
                    )
                    text = _transcribe_inline(
                        api_key=api_key,
                        model_name=candidate,
                        audio_bytes=audio_bytes,
                        mime=mime,
                    )
            logger.info(
                "Transcribed %s bytes (%s) with %s -> %d chars",
                len(audio_bytes),
                mime,
                candidate,
                len(text),
            )
            return text
        except Exception as exc:
            last_error = exc
            logger.warning("Transcription failed with model %s: %s", candidate, exc)

    if last_error is not None:
        raise last_error
    raise RuntimeError("No transcription model available")
