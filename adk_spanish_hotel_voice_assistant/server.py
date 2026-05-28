"""HTTP server entry helpers.

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import threading

from .config import HOST, PORT
from .state import app


def run_production_server() -> None:
    try:
        from waitress import serve

        print(f"Starting production server on {HOST}:{PORT}")
        serve(app, host=HOST, port=PORT, threads=8)
    except ImportError:
        print("Waitress no disponible, iniciando servidor Flask de desarrollo.")
        app.run(host=HOST, port=PORT, debug=False)


def run_flask_in_thread() -> threading.Thread:
    def _run():
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread
