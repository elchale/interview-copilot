"""Tests for the cloud backend: crypto, DB/pairing, device auth, publisher, settings."""

from __future__ import annotations

import asyncio

import pytest

from cloud import auth, db
from cloud.crypto import decrypt, encrypt
from cloud.publisher import BrowserPublisher, CloudSettings, Hub, HubRegistry
from cloud.remote_publisher import RemotePublisher


@pytest.fixture()
def session(tmp_path):
    db.init_engine(f"sqlite:///{tmp_path / 'test.db'}")
    s = db.get_session()
    yield s
    s.close()


class TestCrypto:
    def test_round_trip(self) -> None:
        sk = "secret"
        token = encrypt(sk, "sk-ant-123")
        assert token and token != "sk-ant-123"
        assert decrypt(sk, token) == "sk-ant-123"

    def test_empty_and_tampered(self) -> None:
        assert encrypt("k", "") == ""
        assert decrypt("k", "") == ""
        assert decrypt("k", "not-a-valid-token") == ""

    def test_wrong_key_fails_closed(self) -> None:
        token = encrypt("right", "value")
        assert decrypt("wrong", token) == ""


class TestPairingAndDevices:
    def test_upsert_is_idempotent(self, session) -> None:
        info = {"sub": "g-1", "email": "a@b.com", "name": "A"}
        u1 = auth.upsert_user(session, info)
        u2 = auth.upsert_user(session, info)
        assert u1.id == u2.id
        assert u1.email == "a@b.com"

    def test_claim_then_authenticate_device(self, session) -> None:
        user = auth.upsert_user(session, {"sub": "g-2", "email": "x@y.com"})
        pc = db.PairCode(device_code="dc-123", status="pending")
        session.add(pc)
        session.commit()

        token = auth.claim_pair_code(session, "dc-123", user.id)
        assert token
        # code is now consumed
        assert session.query(db.PairCode).filter_by(device_code="dc-123").one().status == "claimed"
        # token authenticates the agent back to the right user
        device = auth.device_for_token(session, token)
        assert device is not None and device.user_id == user.id

    def test_claim_invalid_code_raises(self, session) -> None:
        user = auth.upsert_user(session, {"sub": "g-3"})
        with pytest.raises(ValueError):
            auth.claim_pair_code(session, "missing", user.id)

    def test_bad_token_returns_none(self, session) -> None:
        assert auth.device_for_token(session, "") is None
        assert auth.device_for_token(session, "nope") is None


class TestCloudSettings:
    def test_keys_served_without_env_or_dpapi(self) -> None:
        s = CloudSettings(deepgram_key="dg", anthropic_key="an", answer_mode="CODING")
        assert s.deepgram_key == "dg"
        assert s.anthropic_key == "an"
        assert s.llm_api_key() == "an"
        assert s.llm_provider == "anthropic"
        assert s.answer_mode == "CODING"


class TestBrowserPublisher:
    def test_fanout_and_snapshot(self) -> None:
        pub = BrowserPublisher()
        q = pub.subscribe()
        pub.add_transcript("Two sum?", source="system")
        pub.start_answer("a1")
        pub.stream_answer_delta("a1", "Use a hashmap.")
        pub.finish_answer("a1", latency_ms=900)

        events = []
        while not q.empty():
            events.append(q.get_nowait())
        types = [e["type"] for e in events]
        assert "transcript" in types and "answer.start" in types and "answer.done" in types

        snap = pub.snapshot()
        assert snap["transcript"][0]["text"] == "Two sum?"
        assert snap["answers"][0]["text"] == "Use a hashmap."
        assert snap["answers"][0]["status"] == "DONE"

    def test_unsubscribe_stops_delivery(self) -> None:
        pub = BrowserPublisher()
        q = pub.subscribe()
        pub.unsubscribe(q)
        pub.add_transcript("hi")
        assert q.empty()


class TestRemotePublisher:
    def test_buffers_events_in_ingest_shape(self) -> None:
        rp = RemotePublisher("https://x/api/ingest", "tok")
        rp.add_transcript("Two sum?", source="system")
        rp.start_answer("a1")
        rp.stream_answer_delta("a1", "Use a map.")
        rp.finish_answer("a1", latency_ms=800)
        rp.update_status(call_active=True)

        kinds = [e["kind"] for e in rp._buf]
        assert kinds == ["transcript", "answer.start", "answer.delta", "answer.done", "status"]
        assert rp._buf[0]["payload"] == {"text": "Two sum?", "source": "system"}
        assert rp._buf[3]["payload"] == {"answerId": "a1", "latencyMs": 800}
        assert rp._buf[4]["payload"] == {"call_active": True}


class TestHubRegistry:
    def test_get_or_create_is_stable(self) -> None:
        reg = HubRegistry()
        loop = asyncio.new_event_loop()
        try:
            settings = CloudSettings(deepgram_key="", anthropic_key="")
            hub1 = reg.get_or_create(1, settings, loop)
            hub2 = reg.get_or_create(1, settings, loop)
            assert hub1 is hub2
            assert isinstance(hub1, Hub)
            reg.drop(1)
            assert reg.get(1) is None
        finally:
            loop.close()

    def test_refresh_updates_live_keys(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            hub = Hub(CloudSettings(deepgram_key="", anthropic_key=""), loop)
            hub.refresh(deepgram_key="DG", anthropic_key="AN", answer_mode="MATH",
                        persona="p", enable_web_search=False)
            s = hub.live._settings
            assert s.deepgram_key == "DG" and s.anthropic_key == "AN"
            assert s.answer_mode == "MATH" and s.enable_web_search is False
        finally:
            loop.close()
