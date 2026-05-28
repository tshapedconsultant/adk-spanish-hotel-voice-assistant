"""Gemini-backed agent with shared session store, routing, and entity extraction.

Author: Andres Lage. Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import callbacks as _callbacks_mod
from .amadeus_client import amadeus_configured
from .config import (
    DEFAULT_HOTEL_CITY,
    ENABLE_LLM_INTENT,
    GEMINI_MODEL,
    HAS_GEMINI,
    INTENT_CLASSIFIER_MODEL,
    LLM_INTENT_OVERRIDE,
    ROUTING_MODEL,
    USE_AMADEUS_HOTEL_TOOLS,
    USE_INTENT_FUNCTION_CALLING,
    USE_STRUCTURED_ROUTING,
    genai,
    logger,
)
from .hotel_search import buscar_disponibilidad_hotel, infer_ciudad_from_text
from .hotel_tools import format_amadeus_context_for_prompt, run_chat_with_hotel_tools
from .gemini_errors import (
    chat_model_fallbacks,
    extract_response_text,
    is_quota_error,
    user_facing_gemini_error,
)
from .routing import RoutingService
from .sessions import RedisSessionStore, SessionManager, UserSession

_BOOKING_RES = (
    re.compile(r"\breserv", re.IGNORECASE),
    re.compile(r"\bhabitaci", re.IGNORECASE),
    re.compile(r"\bhotel\b", re.IGNORECASE),
    re.compile(r"\bhosped", re.IGNORECASE),
)
_GREETING_RES = (
    re.compile(r"\bhola\b", re.IGNORECASE),
    re.compile(r"\bbuen[oa]s\b", re.IGNORECASE),
    re.compile(r"\bsaludos\b", re.IGNORECASE),
)
_GRATITUDE_RES = (
    re.compile(r"\bgracias\b", re.IGNORECASE),
    re.compile(r"\bagradezco\b", re.IGNORECASE),
)
_PRICE_RES = (
    re.compile(r"\bprecio", re.IGNORECASE),
    re.compile(r"\btarifa", re.IGNORECASE),
    re.compile(r"\bcoste\b", re.IGNORECASE),
    re.compile(r"\bcu[aá]nto", re.IGNORECASE),
)
_CANCELLATION_RES = (
    re.compile(r"\bcancel", re.IGNORECASE),
    re.compile(r"\banular\b", re.IGNORECASE),
    re.compile(r"\beliminar\b", re.IGNORECASE),
)

_INTENT_JSON_RE = re.compile(
    r'"intent"\s*:\s*"([a-z_]+)"', re.IGNORECASE | re.DOTALL
)


class GeminiAgent:
    """Wrapper around Gemini with session memory, routing, and intent callbacks."""

    def __init__(
        self,
        system_prompt: str,
        api_key: str,
        model_name: str = GEMINI_MODEL,
        model_factory: Optional[Callable[..., Any]] = None,
        intent_classifier_enabled: Optional[bool] = None,
        intent_model_factory: Optional[Callable[..., Any]] = None,
        session_manager: Optional[SessionManager | RedisSessionStore] = None,
        structured_routing_enabled: Optional[bool] = None,
        function_call_routing_enabled: Optional[bool] = None,
    ):
        if not api_key:
            raise ValueError("GOOGLE_API_KEY environment variable required")

        self.model_name = model_name
        self._system_prompt = system_prompt
        self._api_key = api_key
        self.session_manager = session_manager or SessionManager()
        self._live_api = model_factory is None
        self._model_factory = model_factory
        self._model_instance = None
        self.intent_classifier_enabled = (
            ENABLE_LLM_INTENT
            if intent_classifier_enabled is None
            else intent_classifier_enabled
        )
        self.intent_classifier_override = LLM_INTENT_OVERRIDE
        self.intent_model_name = INTENT_CLASSIFIER_MODEL
        self._intent_model_factory = intent_model_factory

        use_struct = (
            USE_STRUCTURED_ROUTING
            if structured_routing_enabled is None
            else structured_routing_enabled
        )
        use_fc = (
            USE_INTENT_FUNCTION_CALLING
            if function_call_routing_enabled is None
            else function_call_routing_enabled
        )
        self._routing: Optional[RoutingService] = None
        if model_factory is None and HAS_GEMINI and (use_struct or use_fc):
            try:
                route_model = ROUTING_MODEL
                self._routing = RoutingService(
                    api_key,
                    route_model,
                    use_function_call=bool(use_fc),
                )
                logger.info(
                    "Intent routing: %s via model %s",
                    "function_call" if use_fc else "structured_json",
                    route_model,
                )
            except Exception as exc:
                logger.warning("Routing service disabled: %s", exc)
                self._routing = None

        if model_factory is None:
            if not HAS_GEMINI:
                raise RuntimeError(
                    "google-generativeai package not installed. "
                    "Install with `pip install google-generativeai`."
                )

            genai.configure(api_key=api_key)
            self._generation_config = genai.types.GenerationConfig(
                temperature=0.7,
                top_p=0.8,
                top_k=40,
                max_output_tokens=1024,
            )
        else:
            self._generation_config = None

        if self.intent_classifier_enabled and self._intent_model_factory is None:
            if not HAS_GEMINI:
                raise RuntimeError(
                    "Intent classifier requires google-generativeai package. "
                    "Install with `pip install google-generativeai`."
                )
            self._intent_model_factory = lambda: genai.GenerativeModel(
                model_name=self.intent_model_name,
                system_instruction=(
                    "Eres un clasificador de intenciones en español. "
                    "Devuelve exclusivamente JSON con la forma {\"intent\": \"<label>\"}. "
                    "El conjunto permitido es: booking_request, greeting, gratitude, "
                    "price_inquiry, cancellation_request, smalltalk, unknown."
                ),
            )

        self._allowed_intents = {
            "booking_request",
            "greeting",
            "gratitude",
            "price_inquiry",
            "cancellation_request",
            "smalltalk",
            "unknown",
        }

    def _enrich_with_amadeus_data(
        self,
        user_input: str,
        intent: str,
        entities: Dict[str, Any],
        session: UserSession,
    ) -> str:
        """Prefetch Amadeus when we already have dates (tool mode off or extra context)."""
        if not amadeus_configured():
            return user_input
        if intent not in ("price_inquiry", "booking_request"):
            return user_input

        base = dict(session.current_reservation or {})
        ciudad = (entities.get("ciudad") or base.get("ciudad") or DEFAULT_HOTEL_CITY).strip()
        check_in = (entities.get("check_in") or base.get("check_in") or "").strip()
        check_out = (entities.get("check_out") or base.get("check_out") or "").strip()
        guests = entities.get("guests") or base.get("guests") or 1
        if not check_in or not check_out:
            return user_input

        result = buscar_disponibilidad_hotel(
            ciudad=ciudad,
            check_in=check_in,
            check_out=check_out,
            huespedes=int(guests) if guests else 1,
        )
        return user_input + format_amadeus_context_for_prompt(result)

    def _run_chat_turn(
        self, model_name: str, history: List[Dict[str, Any]], user_input: str
    ) -> str:
        if self._live_api:
            if not HAS_GEMINI:
                raise RuntimeError("google-generativeai is not installed")
            if amadeus_configured() and USE_AMADEUS_HOTEL_TOOLS:
                return run_chat_with_hotel_tools(
                    model_name=model_name,
                    system_prompt=self._system_prompt,
                    history=history,
                    user_input=user_input,
                    generation_config=self._generation_config,
                )
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=self._system_prompt,
            )
            chat_session = model.start_chat(history=history)
            kwargs: Dict[str, Any] = {}
            if self._generation_config is not None:
                kwargs["generation_config"] = self._generation_config
            response = chat_session.send_message(user_input, **kwargs)
            return extract_response_text(response)

        if self._model_instance is None:
            if self._model_factory is None:
                raise RuntimeError("Model factory not configured")
            self._model_instance = self._model_factory()
        chat_session = self._model_instance.start_chat(history=history)
        kwargs = {}
        if self._generation_config is not None:
            kwargs["generation_config"] = self._generation_config
        response = chat_session.send_message(user_input, **kwargs)
        return extract_response_text(response)

    def generate(
        self, user_input: str, session_id: Optional[str] = None
    ) -> Tuple[str, str]:
        """Return (assistant_reply, session_id) for the conversation turn."""
        session = self._ensure_session(session_id)
        active_session_id = session.session_id
        session.add_message("user", user_input)
        self._persist(session)

        intent, entities = self._resolve_intent(user_input)
        if not (entities.get("ciudad") or "").strip():
            guessed = infer_ciudad_from_text(user_input)
            if guessed:
                entities = {**entities, "ciudad": guessed}
        self._merge_reservation(session, entities)
        self._persist(session)

        history = self._format_history(session.conversation_history[:-1])
        chat_input = user_input
        if amadeus_configured() and not USE_AMADEUS_HOTEL_TOOLS:
            chat_input = self._enrich_with_amadeus_data(
                user_input, intent, entities, session
            )

        models_to_try = (
            chat_model_fallbacks(self.model_name)
            if self._live_api
            else [self.model_name]
        )
        last_exc: Optional[Exception] = None

        for candidate in models_to_try:
            try:
                assistant_response = self._run_chat_turn(
                    candidate, history, chat_input
                )
                if candidate != self.model_name:
                    logger.info("Chat succeeded with fallback model %s", candidate)
                session.add_message("model", assistant_response)
                self._persist(session)
                self._trigger_intent_callbacks(
                    user_input,
                    assistant_response,
                    session,
                    intent,
                    entities,
                )
                return assistant_response, active_session_id
            except Exception as exc:
                last_exc = exc
                self._handle_error(exc)
                if self._live_api and is_quota_error(exc):
                    logger.warning(
                        "Chat quota/error on %s, trying next model: %s",
                        candidate,
                        exc,
                    )
                    self._model_instance = None
                    continue
                break

        self._persist(session)
        return user_facing_gemini_error(last_exc), active_session_id

    def _persist(self, session: UserSession) -> None:
        self.session_manager.put_session(session)

    def _ensure_session(self, session_id: Optional[str]) -> UserSession:
        if session_id:
            session = self.session_manager.get_session(session_id)
            if session:
                return session
            logger.warning("Session %s not found; creating a new session.", session_id)
        return self.session_manager.create_session()

    @staticmethod
    def _format_history(history: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        formatted = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            formatted.append({"role": role, "parts": [msg["content"]]})
        return formatted

    def _resolve_intent(self, user_input: str) -> Tuple[str, Dict[str, Any]]:
        entities: Dict[str, Any] = {}
        intent = "unknown"
        if self._routing is not None:
            intent, entities = self._routing.route(user_input)
        if intent == "unknown":
            intent = self._keyword_intent(user_input)
        if self.intent_classifier_enabled and (
            intent == "unknown" or self.intent_classifier_override
        ):
            llm_intent = self._classify_intent_llm(user_input)
            if llm_intent:
                intent = llm_intent
        return intent, entities

    @staticmethod
    def _merge_reservation(session: UserSession, entities: Dict[str, Any]) -> None:
        if not entities:
            return
        base = dict(session.current_reservation or {})
        gn = (entities.get("guest_name") or "").strip()
        if gn:
            base["guest_name"] = gn
        for key in ("check_in", "check_out", "room_type", "ciudad"):
            v = (entities.get(key) or "").strip()
            if v:
                base[key] = v
        g = entities.get("guests")
        if isinstance(g, int) and g > 0:
            base["guests"] = g
        session.current_reservation = base if base else None

    def _keyword_intent(self, user_text: str) -> str:
        if any(r.search(user_text) for r in _BOOKING_RES):
            return "booking_request"
        if any(r.search(user_text) for r in _GREETING_RES):
            return "greeting"
        if any(r.search(user_text) for r in _GRATITUDE_RES):
            return "gratitude"
        if any(r.search(user_text) for r in _PRICE_RES):
            return "price_inquiry"
        if any(r.search(user_text) for r in _CANCELLATION_RES):
            return "cancellation_request"
        return "unknown"

    def _trigger_intent_callbacks(
        self,
        user_input: str,
        response: str,
        session: UserSession,
        intent: str,
        entities: Dict[str, Any],
    ) -> None:
        session_id = session.session_id
        payload = {
            "session_id": session_id,
            "user_input": user_input,
            "assistant_response": response,
            "detected_intent": intent,
            "extracted_entities": dict(entities),
            "current_reservation": dict(session.current_reservation or {}),
            "timestamp": time.time(),
        }

        if amadeus_configured() and intent in ("price_inquiry", "booking_request"):
            base = dict(session.current_reservation or {})
            ciudad = (entities.get("ciudad") or base.get("ciudad") or DEFAULT_HOTEL_CITY)
            cin = (entities.get("check_in") or base.get("check_in") or "")
            cout = (entities.get("check_out") or base.get("check_out") or "")
            if cin and cout:
                payload["amadeus_search"] = buscar_disponibilidad_hotel(
                    ciudad=str(ciudad),
                    check_in=str(cin),
                    check_out=str(cout),
                    huespedes=int(entities.get("guests") or base.get("guests") or 1),
                )

        cb = _callbacks_mod.callbacks
        if intent == "booking_request" and cb.on_booking_request:
            try:
                booking_result = cb.on_booking_request(payload)
                if isinstance(booking_result, dict):
                    payload["booking_result"] = booking_result
            except Exception as exc:  # pragma: no cover - hook failures
                self._handle_error(exc)

        if cb.on_intent:
            try:
                cb.on_intent(payload)
            except Exception as exc:  # pragma: no cover - hook failures
                self._handle_error(exc)

    @staticmethod
    def _handle_error(exc: Exception) -> None:
        cb = _callbacks_mod.callbacks
        if cb.on_error:
            cb.on_error(exc)

    def _classify_intent_llm(self, user_input: str) -> Optional[str]:
        if not self.intent_classifier_enabled or not self._intent_model_factory:
            return None
        prompt = (
            "Clasifica la intención del usuario. Responde únicamente con JSON de la forma "
            '{"intent": "<label>"} sin explicaciones. Las etiquetas válidas son: '
            "booking_request, greeting, gratitude, price_inquiry, cancellation_request, "
            "smalltalk, unknown.\n"
            f"Usuario: {user_input}\n"
        )
        try:
            model = self._intent_model_factory()
            response = model.generate_content([prompt])
            intent = self._parse_intent_response(response.text)
            if intent in self._allowed_intents:
                logger.debug("LLM intent classifier result: %s", intent)
                return intent
        except Exception as exc:
            logger.debug("LLM intent classifier fallback: %s", exc)
            self._handle_error(exc)
        return None

    @staticmethod
    def _parse_intent_response(text: str) -> Optional[str]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z0-9_]*\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)

        for candidate in (
            cleaned,
            cleaned[cleaned.find("{") :] if "{" in cleaned else cleaned,
        ):
            try:
                if not candidate.strip().startswith("{"):
                    continue
                data = json.loads(candidate)
                intent = data.get("intent")
                if isinstance(intent, str):
                    stripped = intent.strip().lower()
                    if stripped:
                        return stripped
            except json.JSONDecodeError:
                continue

        match = _INTENT_JSON_RE.search(cleaned)
        if match:
            return match.group(1).strip().lower()
        return None
