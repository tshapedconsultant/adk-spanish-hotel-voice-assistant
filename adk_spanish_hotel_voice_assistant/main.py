"""CLI entry point.

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import argparse
from .config import GOOGLE_API_KEY, HOST, PORT, WEBHOOK_BASE
from .runtime import AssistantApp, normalize_cli_mode
from .server import run_production_server
from .state import app as flask_app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ADK Spanish Hotel Reservation Voice Assistant"
    )
    parser.add_argument(
        "--mode",
        choices=["text", "chat", "voice", "code"],
        default="text",
        help="Modo inicial: text/chat (CLI), voice (voz). 'code' está obsoleto (alias de text).",
    )
    parser.add_argument(
        "--serve-webhook",
        action="store_true",
        help="Inicia el servidor de webhooks en este proceso",
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Usa waitress para un servidor listo para producción",
    )
    args = parser.parse_args()

    if not GOOGLE_API_KEY:
        print(
            "Error: configure la variable GOOGLE_API_KEY con una clave válida de Google Gemini.\n"
            "Ejemplo (Linux/macOS): export GOOGLE_API_KEY='SU_CLAVE'\n"
            "Ejemplo (Windows PowerShell): $env:GOOGLE_API_KEY='SU_CLAVE'"
        )
        return

    if args.serve_webhook:
        if args.production:
            run_production_server()
        else:
            print(f"Webhook server running on {WEBHOOK_BASE}")
            print("Press Ctrl+C to stop.")
            flask_app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
        return

    app_instance = AssistantApp()
    if args.mode == "code":
        print("Aviso: --mode code está obsoleto; use --mode text.")
    app_instance.set_mode(normalize_cli_mode(args.mode))
    app_instance.start()
