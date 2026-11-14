# SPDX-License-Identifier: AGPL-3.0-only
"""Real classroom provider + SDK + Portage HTTP/ledger; synthetic upstream only."""

import asyncio
import importlib.util
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from openai import APIStatusError
from starlette.requests import Request

from app.agent.llm import PortageProvider, provider_class
from app.auth import authorize, execution_grant, recheck_grant
from app.config import settings
from app.controls.contracts import ControlError, Limits, Scope
from app.controls.runtime import operation
from conftest import controls_policy
from tests.http_auth import configure, token

CONTROL_SCOPE = Scope("test", "i", "c", "learner01")

PORTAGE_REVISION = "709f5aba85dd2e56f87e9f5c32a2ac7438268ee5"
ROSTER_ID = "47a8ed4608e14957bf74ac18f93655c1"


def roster_authorization(monkeypatch, tmp_path):
    authorization = {
        "exercise_versions": {"echo-1": "v1"},
        "subjects": {
            "verified-subject": [
                {
                    "institution_id": "i",
                    "class_id": "c",
                    "learner_id": ROSTER_ID,
                    "learner_id_kind": "cairn_roster_v1",
                    "grant_generation": "a45abc18d8ca4ae6a7b32def7048d2ac",
                    "assignments": {"echo-1": "v1"},
                }
            ],
        },
    }
    path = configure(monkeypatch, tmp_path, authorization)
    request = Request({"type": "http", "method": "POST", "path": "/api/sol/turn", "headers": []})
    request._body = json.dumps({"participant_id": ROSTER_ID, "exercise_id": "echo-1"}).encode()
    identity = asyncio.run(
        authorize(
            request,
            HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=token("verified-subject"),
            ),
        )
    )
    return identity, path, authorization


def test_verified_roster_label_reaches_actual_gateway(connected, ledger, monkeypatch, tmp_path):
    provider, portage, state = connected
    identity, _, _ = roster_authorization(monkeypatch, tmp_path)
    portage.member("course01", identity.learner_id, 100000)
    grant = execution_grant(identity)
    scope = Scope("test", identity.institution_id, identity.class_id, identity.learner_id)
    with operation(ledger, scope, "roster-success", guard=lambda: recheck_grant(grant)):
        assert invoke(provider) == {"hint": "check missingness"}
    assert state["gateway_calls"] == state["calls"] == 1
    assert state["authority_paths"]
    assert set(state["authority_paths"]) == {"/internal/member/" + ROSTER_ID}
    assert portage.usage("course01", ROSTER_ID)["committed"] == 15
    assert portage.usage("course01", "learner01")["committed"] == 0


@pytest.mark.parametrize(
    "change", ["revoked", "stale_assignment", "substituted_principal", "renewed"]
)
def test_roster_execution_grant_rechecked_before_dispatch(
    configured, ledger, monkeypatch, tmp_path, change
):
    identity, path, authorization = roster_authorization(monkeypatch, tmp_path)
    grant = execution_grant(identity)
    if change == "revoked":
        authorization["subjects"].clear()
    elif change == "stale_assignment":
        authorization["exercise_versions"]["echo-1"] = "v2"
    elif change == "renewed":
        authorization["subjects"]["verified-subject"][0]["grant_generation"] = (
            "3d7e9b1e9d3e452ab2f405b85b56685c"
        )
    else:
        authorization["subjects"]["other-subject"] = authorization["subjects"].pop(
            "verified-subject"
        )
    path.write_text(json.dumps(authorization))
    provider = PortageProvider()
    try:
        scope = Scope("test", identity.institution_id, identity.class_id, identity.learner_id)
        with operation(ledger, scope, "roster-revoked", guard=lambda: recheck_grant(grant)):
            with pytest.raises(HTTPException) as error:
                invoke(provider)
        assert error.value.status_code == 404
        assert ledger.summary()["attempts"] == 0
    finally:
        provider._client.close()


@pytest.fixture
def configured(monkeypatch):
    for key, value in {
        "controls_mode": "enforced",
        "provider": "portage",
        "portage_deployment": "test",
        "portage_institution": "i",
        "portage_classroom": "c",
        "openai_base_url": "http://127.0.0.1:1/v1",
        "openai_api_key": "synthetic-only-key",
        "openai_response_format": "json_object",
    }.items():
        monkeypatch.setattr(settings, key, value)


def test_selection_and_aliases(configured):
    assert provider_class("portage") is PortageProvider
    assert settings.model_tiers == {"fast": "code_small", "strong": "code_large"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("controls_mode", "development_bypass"),
        ("portage_classroom", ""),
        ("openai_api_key", "EMPTY"),
        ("openai_base_url", "http://untrusted.invalid/v1"),
        ("openai_base_url", "https://host.invalid/v1?redirect=elsewhere"),
    ],
)
def test_invalid_configuration_refuses(configured, monkeypatch, field, value):
    monkeypatch.setattr(settings, field, value)
    with pytest.raises(ControlError, match="portage_configuration_required"):
        PortageProvider()


def invoke(provider):
    return provider.json(
        role="planner", tier="fast", system="synthetic", user="hint", max_tokens=10
    )


def test_missing_or_cross_class_context_never_dispatches(configured, ledger):
    provider = PortageProvider()
    try:
        with pytest.raises(ControlError, match="verified_execution_required"):
            invoke(provider)
        with operation(ledger, Scope("test", "i", "other", "learner01"), "cross-class"):
            with pytest.raises(ControlError, match="portage_scope_mismatch"):
                invoke(provider)
        assert ledger.summary()["attempts"] == 0
    finally:
        provider._client.close()


@pytest.fixture
def connected(configured, ledger, tmp_path, monkeypatch, request):
    root = os.environ.get("PORTAGE_CHECKOUT")
    if not root:
        pytest.skip("PORTAGE_CHECKOUT required for actual component integration")
    root_path = Path(root).resolve()
    assert (
        subprocess.check_output(
            ["git", "-C", str(root_path), "rev-parse", "HEAD"], text=True
        ).strip()
        == PORTAGE_REVISION
    )
    assert not subprocess.check_output(
        ["git", "-C", str(root_path), "status", "--porcelain", "--untracked-files=no"], text=True
    ).strip()
    spec = importlib.util.spec_from_file_location(
        "classroom_portage_gateway", root_path / "integrations/ai_pilot/gateway.py"
    )
    assert spec is not None and spec.loader is not None
    gateway = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gateway)
    state = {
        "calls": 0,
        "gateway_calls": 0,
        "authority_paths": [],
        "active": True,
        "usage": True,
        "repair": False,
        "fail": False,
    }

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            state["authority_paths"].append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                json.dumps({"active": state["active"], "project": "course01"}).encode()
            )

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["calls"] += 1
            assert self.headers.get("X-Portage-Request-Id")
            assert body["model"] == "code_small"
            if state["fail"]:
                self.send_response(503)
                self.end_headers()
                return
            text = (
                "not json"
                if state["repair"] and state["calls"] == 1
                else '{"hint":"check missingness"}'
            )
            result = {
                "id": "synthetic",
                "object": "chat.completion",
                "created": 0,
                "model": "code_small",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": "stop",
                    }
                ],
            }
            if state["usage"]:
                result["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    origin = f"http://127.0.0.1:{upstream.server_port}"
    portage = gateway.Ledger(tmp_path / "portage.sqlite")
    portage.project("course01", 100000, 2)
    portage.member("course01", "learner01", 100000)
    token = portage.issue("course01", kind="application")
    models = {
        name: {
            "endpoint": origin,
            "max_output_tokens": 100,
            "max_request_tokens": 10000,
            "operation": "chat/completions",
            "synthetic": True,
        }
        for name in ["code_small", "code_large"]
    }
    service = gateway.Gateway(
        ("127.0.0.1", 0),
        portage,
        {"mode": "synthetic", "models": models},
        "control",
        "inference",
        origin,
        "authority",
        shadow_decider=gateway.ShadowDecider() if getattr(request, "param", False) else None,
    )

    class CountedHandler(gateway.Handler):
        def do_POST(self):
            state["gateway_calls"] += 1
            return super().do_POST()

    service.RequestHandlerClass = CountedHandler
    monkeypatch.setattr(settings, "openai_base_url", f"http://127.0.0.1:{service.server_port}/v1")
    monkeypatch.setattr(settings, "openai_api_key", token)
    ledger.update_policy(controls_policy(version="portage-v1", deployment=Limits(tokens=100000)))
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (upstream, service)]
    for thread in threads:
        thread.start()
    provider = PortageProvider()
    try:
        state["models"] = models
        yield provider, portage, state
    finally:
        provider._client.close()
        for server in (service, upstream):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=2)
            assert not thread.is_alive()


def test_actual_gateway_success(connected, ledger):
    provider, portage, state = connected
    with operation(ledger, CONTROL_SCOPE, "success"):
        assert invoke(provider) == {"hint": "check missingness"}
    assert state["gateway_calls"] == 1
    assert state["calls"] == 1
    assert portage.usage("course01", "learner01")["committed"] == 15
    assert ledger.summary()["consumed"]["tokens"] == 15


@pytest.mark.parametrize("refusal", ["revoked", "exhausted"])
def test_actual_gateway_refusal_no_upstream(connected, ledger, refusal):
    provider, portage, state = connected
    if refusal == "revoked":
        state["active"] = False
    else:
        portage.member("course01", "learner01", 1)
    with (
        operation(ledger, CONTROL_SCOPE, refusal),
        pytest.raises(ControlError if refusal == "revoked" else APIStatusError),
    ):
        invoke(provider)
    assert state["gateway_calls"] == 1
    assert state["calls"] == 0
    assert portage.usage("course01", "learner01")["committed"] == 0
    # Without authenticated no-dispatch receipts Belay retains a conservative hold.
    assert ledger.summary()["states"]["unknown"] == 1


def test_actual_gateway_explicit_repair_accounted(connected, ledger):
    provider, portage, state = connected
    state["repair"] = True
    with operation(ledger, CONTROL_SCOPE, "repair"):
        assert invoke(provider) == {"hint": "check missingness"}
    assert state["gateway_calls"] == 2
    assert state["calls"] == 2
    assert portage.usage("course01", "learner01")["committed"] == 30
    assert ledger.summary()["consumed"]["tokens"] == 30


@pytest.mark.parametrize("mode", ["missing_usage", "upstream_error"])
def test_actual_gateway_unknown_no_hidden_retry(connected, ledger, mode):
    provider, portage, state = connected
    state["usage"] = False
    state["fail"] = mode == "upstream_error"
    with operation(ledger, CONTROL_SCOPE, mode):
        if state["fail"]:
            with pytest.raises(APIStatusError):
                invoke(provider)
        else:
            assert invoke(provider) == {"hint": "check missingness"}
    assert state["gateway_calls"] == 1
    assert state["calls"] == 1
    assert ledger.summary()["states"]["unknown"] == 1
    assert portage.usage("course01", "learner01")["committed"] > 15


def test_controlled_startup_accepts_portage_without_contact(configured):
    from app.controlled_runtime import validate_provider
    from app.preflight import check_provider

    validate_provider()
    ok, message = check_provider()
    assert ok and "NOT PROBED" in message


def test_unbound_legacy_learner_is_not_silently_renamed(configured, ledger):
    provider = PortageProvider()
    try:
        with operation(ledger, Scope("test", "i", "c", "edu:2"), "legacy"):
            with pytest.raises(ControlError, match="portage_subject_binding_required"):
                invoke(provider)
        assert ledger.summary()["attempts"] == 0
    finally:
        provider._client.close()


def test_portage_request_rejection_is_not_format_fallback(connected, ledger):
    provider, portage, state = connected
    state["models"]["code_small"]["max_output_tokens"] = 5
    with operation(ledger, CONTROL_SCOPE, "invalid-output-limit"):
        with pytest.raises(ControlError, match="portage_request_refused"):
            invoke(provider)
    assert state["gateway_calls"] == 1
    assert state["calls"] == 0
    assert portage.usage("course01", "learner01")["committed"] == 0
