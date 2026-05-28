"""Microphone input and TTS when optional dependencies are installed.

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import queue
import re
import threading
from typing import Optional

from . import callbacks as _callbacks_mod
from .config import HAS_SR, HAS_TTS, logger

if HAS_SR:
    import speech_recognition as sr
if HAS_TTS:
    import pyttsx3

# Queue sentinels (never use "" — that used to break the TTS worker thread).
_SHUTDOWN = object()


class VoiceIO:
    """Handles microphone input and TTS output when dependencies are available."""

    def __init__(self):
        if not HAS_SR or not HAS_TTS:
            raise RuntimeError("SpeechRecognition and pyttsx3 are required for voice mode")
        self.recognizer = sr.Recognizer() if HAS_SR else None
        self.tts_engine = pyttsx3.init() if HAS_TTS else None
        self._tts_queue: "queue.Queue[object]" = queue.Queue()
        self._tts_lock = threading.Lock()
        self._tts_thread = threading.Thread(target=self._tts_loop, daemon=True)
        self._tts_thread.start()
        if self.tts_engine:
            self._configure_tts()

    def _configure_tts(self) -> None:
        try:
            voices = self.tts_engine.getProperty("voices")
            for voice in voices:
                ident = (voice.id + voice.name).lower()
                if any(tag in ident for tag in ("es", "spanish", "espa")):
                    self.tts_engine.setProperty("voice", voice.id)
                    break
            self.tts_engine.setProperty("rate", 160)
            self.tts_engine.setProperty("volume", 0.85)
        except Exception as exc:  # pragma: no cover - hardware specific
            cb = _callbacks_mod.callbacks
            if cb.on_error:
                cb.on_error(exc)

    def listen(self, timeout: int = 8, phrase_time_limit: int = 15) -> str:
        if not HAS_SR:
            raise RuntimeError("SpeechRecognition not installed")

        self.interrupt()

        with sr.Microphone() as mic:
            self.recognizer.adjust_for_ambient_noise(mic, duration=2)
            audio = self.recognizer.listen(
                mic, timeout=timeout, phrase_time_limit=phrase_time_limit
            )
        try:
            return self.recognizer.recognize_google(audio, language="es-ES")
        except sr.UnknownValueError:
            return ""

    def say(self, text: str) -> None:
        if not HAS_TTS:
            print(f"[TTS disabled] {text}")
            return

        self._tts_queue.put(text)

    def interrupt(self) -> None:
        """Stop the current utterance and discard pending phrases (barge-in)."""
        if not HAS_TTS:
            return

        with self._tts_lock:
            if self.tts_engine:
                try:
                    self.tts_engine.stop()
                except Exception as exc:  # pragma: no cover - platform specific
                    logger.debug("TTS stop: %s", exc)

            preserved_shutdown = False
            while True:
                try:
                    item = self._tts_queue.get_nowait()
                except queue.Empty:
                    break
                if item is _SHUTDOWN:
                    preserved_shutdown = True

            if preserved_shutdown:
                self._tts_queue.put(_SHUTDOWN)

    def stop(self) -> None:
        """Shut down the background TTS worker (alias: shutdown)."""
        self.shutdown()

    def shutdown(self) -> None:
        """Stop the TTS worker thread cleanly."""
        self.interrupt()
        self._tts_queue.put(_SHUTDOWN)

    @staticmethod
    def _clean_text_for_tts(text: str) -> str:
        normalized = re.sub(r"[¡¿]", "", text)
        normalized = re.sub(r"[!?]{2,}", "!", normalized)
        normalized = normalized.replace("?", ".").replace("!", ".")
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = normalized.strip()
        if not normalized.endswith("."):
            normalized += "."
        return normalized

    def _tts_loop(self) -> None:  # pragma: no cover - hardware specific
        while True:
            try:
                item = self._tts_queue.get()
                if item is _SHUTDOWN:
                    break
                if not isinstance(item, str) or not item.strip():
                    continue

                clean_text = self._clean_text_for_tts(item)
                with self._tts_lock:
                    if self.tts_engine:
                        self.tts_engine.say(clean_text)
                        self.tts_engine.runAndWait()
            except Exception as exc:
                cb = _callbacks_mod.callbacks
                if cb.on_error:
                    cb.on_error(exc)


def try_init_voice_io() -> Optional[VoiceIO]:
    if not HAS_SR or not HAS_TTS:
        return None
    try:
        return VoiceIO()
    except Exception as exc:  # pragma: no cover - hardware specific
        logger.exception("VoiceIO unavailable: %s", exc)
        return None
