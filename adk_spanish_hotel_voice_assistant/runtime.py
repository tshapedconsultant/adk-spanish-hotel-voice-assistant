"""CLI and voice interaction loops.

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

from .config import GEMINI_MODEL
from . import state


class AssistantApp:
    """Runtime that can switch between CLI (code) and voice modes."""

    def __init__(self):
        self.mode = "code"
        self.running = False
        self.agent = state.agent
        self.voice = state.voice_io
        self.session_manager = state.session_manager
        self.current_session_id = None

    def set_mode(self, mode: str) -> None:
        if mode not in {"code", "voice"}:
            raise ValueError("Mode must be 'code' or 'voice'")
        self.mode = mode
        if mode == "voice" and self.voice:
            session = self.session_manager.create_session()
            self.current_session_id = session.session_id
            print(f"Sesión de voz iniciada: {self.current_session_id}")

    def start(self) -> None:
        if not self.agent:
            print("Error: no se pudo inicializar el agente Gemini.")
            return
        self.running = True
        print(f"Iniciando AssistantApp en modo {self.mode} con modelo {GEMINI_MODEL}")
        if self.mode == "voice" and not self.voice:
            print("Dependencias de voz no disponibles, cambiando a modo texto.")
            self.mode = "code"
        if self.mode == "voice":
            self._run_voice_loop()
        else:
            self._run_code_loop()

    def _run_code_loop(self) -> None:
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
            if user_input.lower() == "cambiar" and self.voice:
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
