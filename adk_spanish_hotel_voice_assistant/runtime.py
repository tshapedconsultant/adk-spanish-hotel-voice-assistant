"""CLI and voice interaction loops.

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

from .config import GEMINI_MODEL
from . import state
from .voice import try_init_voice_io

_VALID_MODES = frozenset({"text", "voice", "code", "chat"})


def normalize_cli_mode(mode: str) -> str:
    """Map legacy CLI aliases to the canonical mode names."""
    if mode in ("code", "chat"):
        return "text"
    return mode


class AssistantApp:
    """Runtime that can switch between CLI (text) and voice modes."""

    def __init__(self):
        self.mode = "text"
        self.running = False
        self.agent = state.agent
        self.voice = None
        self.session_manager = state.session_manager
        self.current_session_id = None

    def _ensure_voice(self):
        if self.voice is None:
            self.voice = try_init_voice_io()
        return self.voice

    def set_mode(self, mode: str) -> None:
        if mode not in _VALID_MODES:
            raise ValueError("Mode must be 'text', 'chat', 'voice', or legacy 'code'")
        self.mode = normalize_cli_mode(mode)
        if self.mode == "voice":
            voice = self._ensure_voice()
            if voice:
                session = self.session_manager.create_session()
                self.current_session_id = session.session_id
                print(f"Sesión de voz iniciada: {self.current_session_id}")

    def start(self) -> None:
        if not self.agent:
            print("Error: no se pudo inicializar el agente Gemini.")
            return
        self.running = True
        print(f"Iniciando AssistantApp en modo {self.mode} con modelo {GEMINI_MODEL}")
        if self.mode == "voice" and not self._ensure_voice():
            print("Dependencias de voz no disponibles, cambiando a modo texto.")
            self.mode = "text"
        if self.mode == "voice":
            self._run_voice_loop()
        else:
            self._run_text_loop()

    def _run_text_loop(self) -> None:
        session = self.session_manager.create_session()
        self.current_session_id = session.session_id
        print("Sesión de texto iniciada. Escriba 'salir' para terminar.")
        while self.running:
            try:
                user_input = input("Usuario > ").strip()
            except KeyboardInterrupt:
                print("\nSaliendo...")
                break
            if not user_input:
                continue
            if user_input.lower() in {"quit", "exit", "salir"}:
                self.running = False
                break
            if user_input.lower() == "cambiar" and self._ensure_voice():
                self.set_mode("voice")
                self._run_voice_loop()
                return
            reply, self.current_session_id = self.agent.generate(
                user_input, self.current_session_id
            )
            print(f"Asistente > {reply}\n")

    def _run_voice_loop(self) -> None:
        if not self.voice:
            print("VoiceIO no disponible.")
            return
        greeting = "Hola, soy su asistente virtual de reservas de hotel. ¿En qué puedo ayudarle?"
        print(f"Asistente > {greeting}")
        self.voice.say(greeting)
        while self.running:
            self.voice.interrupt()
            print("Escuchando... (di 'salir' para terminar)")
            user_text = self.voice.listen()
            if not user_text:
                prompt = "No le he entendido, ¿podría repetirlo?"
                print(f"Asistente > {prompt}")
                self.voice.say(prompt)
                continue
            normalized = user_text.lower()
            if normalized in {"salir", "adiós", "terminar"}:
                goodbye = "Hasta luego, gracias por usar nuestro servicio."
                print(f"Asistente > {goodbye}")
                self.voice.say(goodbye)
                self.running = False
                break
            reply, self.current_session_id = self.agent.generate(
                user_text, self.current_session_id
            )
            print(f"Asistente (voz) > {reply}")
            self.voice.say(reply)
