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

        def fake_booking_callback(payload):
            captured.update(payload)
            return {"status": "ok"}

        callbacks_pkg.callbacks.on_booking_request = fake_booking_callback

        reply_1, sid1 = agent.generate("Hola", None)
        reply_2, sid2 = agent.generate("Quiero reservar una habitación", sid1)

        assert "Hola" in reply_1
        assert "Perfecto" in reply_2
        assert sid1 == sid2
        assert captured["detected_intent"] == "booking_request"
    finally:
        callbacks_pkg.callbacks = original_callbacks


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
