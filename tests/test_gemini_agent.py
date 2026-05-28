# Copyright (c) 2026 Andres Lage. MIT License — see LICENSE.

from types import SimpleNamespace

import adk_spanish_hotel_voice_assistant as assistant
import adk_spanish_hotel_voice_assistant.callbacks as callbacks_pkg


class StubChatSession:
    def __init__(self, responses_iter):
        self._responses = responses_iter

    def send_message(self, *_args, **_kwargs):
        return SimpleNamespace(text=next(self._responses))


class StubModel:
    def __init__(self, responses_iter):
        self._responses = responses_iter

    def start_chat(self, history):
        assert isinstance(history, list)
        return StubChatSession(self._responses)


def test_gemini_agent_generates_response_and_keeps_context():
    responses = iter(
        [
            "¡Hola! ¿En qué fechas desea hospedarse?",
            "Perfecto, procederé con la reserva.",
        ]
    )

    def model_factory():
        return StubModel(responses)

    original_callbacks = callbacks_pkg.callbacks
    callbacks_pkg.callbacks = assistant.Callbacks()
    try:
        agent = assistant.GeminiAgent(
            system_prompt="prompt",
            api_key="fake-key",
            model_factory=model_factory,
            structured_routing_enabled=False,
            function_call_routing_enabled=False,
        )

        captured = {}
        booking_calls = []

        def fake_booking_callback(payload):
            booking_calls.append(payload)
            return {"status": "ok"}

        def on_intent(payload):
            captured.update(payload)

        callbacks_pkg.callbacks.on_booking_request = fake_booking_callback
        callbacks_pkg.callbacks.on_intent = on_intent

        reply_1, sid1 = agent.generate("Hola", None)
        reply_2, sid2 = agent.generate("Quiero reservar una habitación", sid1)

        assert "Hola" in reply_1
        assert "Perfecto" in reply_2
        assert sid1 == sid2
        assert captured["detected_intent"] == "booking_request"
        assert len(booking_calls) == 0

        session = agent.session_manager.get_session(sid2)
        session.current_reservation = {
            "guest_name": "Ana Test",
            "check_in": "2026-06-01",
            "check_out": "2026-06-03",
            "ciudad": "Madrid",
        }
        agent.session_manager.put_session(session)

        responses = iter(["Reserva confirmada."])
        agent._model_factory = lambda: StubModel(responses)
        agent._model_instance = None

        agent.generate("Confirmo la reserva", sid2)
        assert len(booking_calls) == 1
    finally:
        callbacks_pkg.callbacks = original_callbacks


def test_gemini_agent_clamps_oversized_user_input(monkeypatch):
    import importlib

    agent_module = importlib.import_module("adk_spanish_hotel_voice_assistant.agent")
    monkeypatch.setattr(agent_module, "MAX_TEXT_CHARS", 10)

    seen = {}

    class StubChatSession:
        def send_message(self, user_input, **_kwargs):
            seen["text"] = user_input
            return SimpleNamespace(text="ok")

    class StubModel:
        def start_chat(self, history):
            return StubChatSession()

    agent = assistant.GeminiAgent(
        system_prompt="prompt",
        api_key="fake-key",
        model_factory=lambda: StubModel(),
        structured_routing_enabled=False,
        function_call_routing_enabled=False,
    )
    reply, _ = agent.generate("x" * 20)
    assert reply == "ok"
    assert seen["text"] == "x" * 10


def test_llm_intent_classifier_enhances_detection():
    """Phrase chosen so keyword tier stays unknown and the LLM tier supplies intent."""
    responses = iter(["Respuesta genérica."])

    def model_factory():
        return StubModel(responses)

    class IntentModel:
        def generate_content(self, *_args, **_kwargs):
            return SimpleNamespace(text='{"intent": "price_inquiry"}')

    original_callbacks = callbacks_pkg.callbacks
    callbacks_pkg.callbacks = assistant.Callbacks()
    captured = {}

    def intent_callback(payload):
        captured.update(payload)

    callbacks_pkg.callbacks.on_intent = intent_callback
    try:
        agent = assistant.GeminiAgent(
            system_prompt="prompt",
            api_key="fake-key",
            model_factory=model_factory,
            intent_classifier_enabled=True,
            intent_model_factory=lambda: IntentModel(),
            structured_routing_enabled=False,
            function_call_routing_enabled=False,
        )

        reply, _ = agent.generate(
            "¿Dispone la suite premium de minibar y vista panorámica?", None
        )
        assert reply

        assert captured["detected_intent"] == "price_inquiry"
    finally:
        callbacks_pkg.callbacks = original_callbacks
