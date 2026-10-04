"""GEE gateway: qayta urinish, 429/timeout'da zaxira loyihaga o'tish, xotira chegarasi, jurnal."""

import json
import time
from typing import Any

import pytest

from backend.app.core import config
from backend.app.core.errors import GEEError, GEEMemoryLimitError, GEETimeoutError
from backend.app.core.run_settings import RunSettings
from backend.app.gee.auth import PRIMARY, SECONDARY
from backend.app.gee.gateway import CallContext, GEEGateway, classify_error


class Env:
    """Soxta ee holati: qaysi loyiha initsializatsiya qilingan."""

    def __init__(self, secondary: bool = True) -> None:
        self.inits: list[str] = []
        self.secondary = secondary

    def init(self, role: str, _timeout: int) -> None:
        self.inits.append(role)

    def configured(self, role: str) -> bool:
        return role == PRIMARY or (role == SECONDARY and self.secondary)


async def _no_sleep(_s: float) -> None:
    return None


def make_gw(env: Env, timeout_s: int = 5, retries: int = 2) -> GEEGateway:
    gw = GEEGateway(initializer=env.init, role_configured=env.configured, sleep=_no_sleep)
    gw.configure(RunSettings(gee_request_timeout_s=timeout_s, gee_max_retries=retries))
    return gw


def records() -> list[dict[str, Any]]:
    out = []
    for f in config.API_CALLS_LOG_DIR.glob("*.jsonl"):
        out += [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line]
    return out


def test_classify_errors():
    assert classify_error(Exception("HTTP 429 Too Many Requests")) == "transient"
    assert classify_error(Exception("Too many concurrent aggregations.")) == "transient"
    assert classify_error(Exception("Quota exceeded for project")) == "quota"
    assert classify_error(Exception("Caller does not have required permission")) == "auth"
    assert classify_error(Exception("User memory limit exceeded.")) == "memory"
    assert classify_error(TimeoutError()) == "timeout"
    assert classify_error(Exception("Image.select: band not found")) == "fatal"


async def test_failover_after_429_retries_exhausted():
    env = Env()
    gw = make_gw(env, retries=2)
    events: list[str] = []

    async def on_event(kind: str, _d: dict[str, Any]) -> None:
        events.append(kind)

    def fn() -> int:
        if gw.role == PRIMARY:
            raise Exception("429 Too Many Requests")
        return 42

    res = await gw.call(fn, ctx=CallContext(run_id=7, on_event=on_event), operation="op", purpose="p", dataset="d")
    assert res == 42
    assert gw.role == SECONDARY and gw.failover_happened
    assert events == ["failover"]
    recs = records()
    primary = [r for r in recs if r["service"] == "gee_primary"]
    assert [r["retries"] for r in primary] == [0, 1, 2]  # 1 + 2 qayta urinish
    ok = [r for r in recs if r["status"] == "success"]
    assert ok[-1]["service"] == "gee_secondary" and ok[-1]["failover"] is True


async def test_failover_on_timeout():
    env = Env()
    gw = make_gw(env, timeout_s=5)
    gw.timeout_s = 0.2  # testni tezlashtirish

    def fn() -> str:
        if gw.role == PRIMARY:
            time.sleep(0.5)
        return "ok"

    assert await gw.call(fn, ctx=CallContext(run_id=1), operation="op", purpose="p", dataset="d") == "ok"
    assert gw.role == SECONDARY
    assert any(r["status"] == "timeout" for r in records())


async def test_timeout_without_secondary_raises_after_retries():
    gw = make_gw(Env(secondary=False), retries=1)
    gw.timeout_s = 0.1

    def fn() -> None:
        time.sleep(0.3)

    with pytest.raises(GEETimeoutError):
        await gw.call(fn, ctx=CallContext(), operation="op", purpose="p", dataset="d")
    assert gw.role == PRIMARY


async def test_quota_triggers_immediate_failover():
    env = Env()
    gw = make_gw(env, retries=3)
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if gw.role == PRIMARY:
            raise Exception("Earth Engine quota exceeded")
        return "ok"

    assert await gw.call(fn, ctx=CallContext(), operation="op", purpose="p", dataset="d") == "ok"
    assert calls["n"] == 2  # qayta urinishsiz darhol o'tdi
    assert env.inits == [PRIMARY, SECONDARY]


async def test_memory_limit_does_not_failover():
    gw = make_gw(Env())

    def fn() -> None:
        raise Exception("User memory limit exceeded.")

    with pytest.raises(GEEMemoryLimitError):
        await gw.call(fn, ctx=CallContext(), operation="op", purpose="p", dataset="d")
    assert gw.role == PRIMARY and not gw.failover_happened


async def test_fatal_error_not_retried():
    gw = make_gw(Env())
    calls = {"n": 0}

    def fn() -> None:
        calls["n"] += 1
        raise Exception("Image.select: Band 'X' not found")

    with pytest.raises(GEEError):
        await gw.call(fn, ctx=CallContext(), operation="op", purpose="p", dataset="d")
    assert calls["n"] == 1


async def test_configure_resets_to_primary():
    env = Env()
    gw = make_gw(env)
    gw.role = SECONDARY
    gw.configure(RunSettings())
    assert gw.role == PRIMARY and not gw.failover_happened
