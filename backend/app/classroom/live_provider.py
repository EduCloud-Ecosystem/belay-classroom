# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit live profile: existing accounting, strict responses, no content in evidence."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import signal
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import select

from ..agent.llm import OpenAICompatProvider, parse_json
from ..config import settings
from ..controls.contracts import ControlError, Scope
from ..controls.ledger import attempts
from ..controls.runtime import attempt_reference, current, model_call, reservation_guard


def allowed_operation(scope, request_id):
    return hashlib.sha256((scope.keys()[-1] + ":" + request_id).encode()).hexdigest()


def write_evidence(path: Path, value, *, new=False):
    """Atomic durable replacement; interruption never turns unknown into success."""
    temporary = path.with_name(path.name + ".pending")
    target = path if new else temporary
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        json.dump(value, handle, sort_keys=True, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    if not new:
        os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


@contextmanager
def wall_deadline(seconds):
    """The dedicated one-turn worker runs on the main POSIX thread, never a server thread."""
    if threading.current_thread() is not threading.main_thread() or not hasattr(
        signal, "setitimer"
    ):
        raise ControlError("live_wall_supervisor_unavailable", 503)
    started = time.monotonic()
    previous = signal.getsignal(signal.SIGALRM)
    old_timer = signal.getitimer(signal.ITIMER_REAL)

    def expired(*_):
        raise ControlError("live_wall_deadline", 503)

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, min(seconds, old_timer[0]) if old_timer[0] else seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if old_timer[0]:
            signal.setitimer(
                signal.ITIMER_REAL,
                max(0.000001, old_timer[0] - (time.monotonic() - started)),
                old_timer[1],
            )


def safe_request_id(value):
    return (
        value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) else None
    )


class LiveRun:
    def __init__(self, profile, grant, directory, grant_path):
        self.profile, self.grant = profile, grant
        self.directory, self.grant_path = directory, grant_path
        self.scope = Scope(grant["deployment_id"], "synthetic-inst", "synthetic-class", "edu:2")
        self.operation = allowed_operation(self.scope, grant["request_id"])

    def assert_unblocked(self):
        if (self.directory / "run-blocked.json").exists():
            raise ControlError("live_run_blocked", 503)

    def block(self, code):
        try:
            write_evidence(
                self.directory / "run-blocked.json",
                {"operation": self.operation, "code": code, "at": time.time()},
                new=True,
            )
        except FileExistsError:
            pass

    def authority(self, remaining=0):
        try:
            if json.loads(self.grant_path.read_text()) != self.grant:
                raise ValueError("grant changed")
            if json.loads((self.directory / "live-grant.json").read_text()) != self.grant:
                raise ValueError("installed grant changed")
            now = time.time()
            if not self.grant["not_before"] <= now < self.grant["expires_at"] - remaining:
                raise ValueError("absolute window expired")
        except (ValueError, OSError, TypeError):
            raise ControlError("live_authority_unavailable", 503) from None

    def context(self, remaining=0):
        self.assert_unblocked()
        self.authority(remaining)
        context = current()  # Rechecks the original membership, job lease and checkpoint.
        if context is None or context.scope != self.scope or context.operation != self.operation:
            raise ControlError("live_turn_not_granted", 403)
        return context

    def reserve(self, conn, kind):
        # Called under the existing SQLite IMMEDIATE/Postgres coordinator lock,
        # in the same transaction as reserve_in. No nested coordinator transaction.
        self.authority()
        self.assert_unblocked()
        rows = list(conn.execute(select(attempts)).mappings())
        relevant = [r for r in rows if r["kind"] in {"model", "runner"}]
        if any(
            r["operation"] != self.operation or r["state"] in {"reserved", "unknown", "overrun"}
            for r in relevant
        ):
            raise ControlError("live_unresolved_or_foreign_attempt", 503)
        limit = self.profile["max_attempts"] if kind == "model" else self.profile["runner_calls"]
        if kind not in {"model", "runner"} or sum(r["kind"] == kind for r in relevant) >= limit:
            raise ControlError("live_attempt_limit", 429)
        # Absolute run ceilings include all periods and persist over restart.
        tokens = sum(
            (r["actual"] if r["actual"] is not None else r["reserved"])["tokens"] for r in relevant
        )
        runs = sum(r["kind"] == "runner" for r in relevant)
        if tokens > self.profile["aggregate_tokens"] or runs > self.profile["runner_calls"]:
            raise ControlError("live_absolute_budget_exceeded", 429)


def make_client(profile):
    import httpx2 as httpx
    from openai import DefaultHttpxClient, OpenAI

    if not issubclass(DefaultHttpxClient, httpx.Client):
        raise ControlError("live_sdk_transport_incompatible", 503)
    timeout = float(profile["http_wall_seconds"])

    class LimitedStream(httpx.SyncByteStream):
        def __init__(self, stream):
            self.stream = stream

        def __iter__(self):
            size = 0
            for chunk in self.stream:
                size += len(chunk)
                if size > profile["max_http_response_bytes"]:
                    raise ControlError("live_response_byte_limit", 503)
                yield chunk

        def close(self):
            self.stream.close()

    class BoundedTransport(httpx.BaseTransport):
        def __init__(self):
            self.inner = httpx.HTTPTransport(
                retries=0,
                trust_env=False,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            )

        def handle_request(self, request):
            if str(request.url) != profile["base_url"] + "/chat/completions":
                raise ControlError("live_endpoint_mismatch", 503)
            result = self.inner.handle_request(request)
            result.stream = LimitedStream(result.stream)
            return result

        def close(self):
            self.inner.close()

    return OpenAI(
        base_url=profile["base_url"],
        api_key=settings.openai_api_key,
        max_retries=0,
        timeout=timeout,
        http_client=DefaultHttpxClient(
            transport=BoundedTransport(),
            follow_redirects=False,
            trust_env=False,
            timeout=timeout,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        ),
    )


class LiveClassroomProvider(OpenAICompatProvider):
    """Preserves the full tutor loop; only this explicit launcher selects the adapter."""

    def __init__(self, run):
        self.run = run
        p = run.profile
        if (
            settings.controls_mode != "enforced"
            or settings.llm_billing_mode != "metered"
            or settings.openai_base_url != p["base_url"]
            or set(settings.model_tiers.values()) != {p["model"]}
            or not settings.injection_guard_enabled
            or not settings.distress_routing_enabled
        ):
            raise ControlError("live_profile_mismatch", 503)
        try:
            self._client = make_client(p)
        except Exception:
            raise ControlError("live_provider_unavailable", 503) from None

    @staticmethod
    def _usage(result):
        usage = getattr(result, "usage", None)
        prompt = getattr(usage, "prompt_tokens", None)
        completion = getattr(usage, "completion_tokens", None)
        total = getattr(usage, "total_tokens", None)
        if (
            type(prompt) is not int
            or type(completion) is not int
            or type(total) is not int
            or prompt < 0
            or completion < 0
            or total != prompt + completion
        ):
            raise ControlError("live_usage_unknown", 503)
        return prompt, completion

    def _attempt(self, role: str, kwargs: dict):
        p, run = self.run.profile, self.run
        context = run.context(p["http_wall_seconds"])
        cap = p["stages"].get(role)
        messages = json.dumps(kwargs["messages"], ensure_ascii=False)
        input_bytes = len(messages.encode())
        output = kwargs["max_tokens"]
        if (
            cap is None
            or kwargs["model"] != p["model"]
            or type(output) is not int
            or output != cap["output_tokens"]
            or input_bytes > p["max_messages_bytes"]
        ):
            raise ControlError("live_attempt_bounds_exceeded", 413)
        record = {}
        path = None

        def send():
            nonlocal path, record
            run.context(p["http_wall_seconds"])
            attempt_id = attempt_reference()
            directory = run.directory / "attempt-evidence"
            records = [json.loads(f.read_text()) for f in directory.glob("model-*.json")]
            role_records = [r for r in records if r["role"] == role]
            if len(role_records) >= cap["http_attempts"]:
                raise ControlError("live_stage_attempt_limit", 429)
            record = {
                "kind": "model",
                "attempt_id": attempt_id,
                "operation": context.operation,
                "scope_hashes": list(context.scope.keys()),
                "model": p["model"],
                "service_tier": "default",
                "role": role,
                "stage_attempt_index": len(role_records) + 1,
                "format_attempt_index": kwargs["format_attempt_index"],
                "reasoning_effort": kwargs["reasoning_effort"],
                "messages_bytes": input_bytes,
                "output_limit": output,
                "client_request_id": attempt_id,
                "provider_request_id": None,
                "profile_sha256": run.grant["profile_sha256"],
                "source_sha256": run.grant["source_sha256"],
                "policy_version": p["profile_id"],
                "price_version": p["price_version"],
                "started_at": time.time(),
                "outcome": "dispatch_pending_or_unknown",
            }
            path = directory / ("model-" + attempt_id + ".json")
            write_evidence(path, record, new=True)
            wire = {
                k: v for k, v in kwargs.items() if k not in {"max_tokens", "format_attempt_index"}
            }
            wire.update(
                max_completion_tokens=output,
                store=False,
                stream=False,
                n=1,
                service_tier="default",
                extra_headers={"X-Client-Request-Id": attempt_id},
            )
            try:
                with wall_deadline(p["http_wall_seconds"]):
                    result = self._client.chat.completions.create(**wire)
            except BaseException as exc:
                status = getattr(exc, "status_code", None)
                record.update(
                    provider_request_id=safe_request_id(getattr(exc, "request_id", None)),
                    http_status=status if type(status) is int else None,
                )
                write_evidence(path, record)
                error = ControlError("live_transport_unknown", 503)
                if type(status) is int:
                    error.status_code = status  # type: ignore[attr-defined]
                raise error from None  # Never allow inherited format fallback on unknown usage.
            record.update(provider_request_id=safe_request_id(getattr(result, "_request_id", None)))
            write_evidence(path, record)
            return result

        try:
            with reservation_guard(run.reserve):
                result = model_call(send, messages, output, self._usage)
            prompt, completion = self._usage(result)
            returned_model = getattr(result, "model", None)
            returned_tier = getattr(result, "service_tier", None)
            record.update(
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=prompt + completion,
                estimated_microunits=prompt + completion,
                finished_at=time.time(),
                returned_model=safe_request_id(returned_model),
                returned_tier=safe_request_id(returned_tier),
            )
            if (
                returned_model != p["model"]
                or returned_tier != "default"
                or not record["provider_request_id"]
                or prompt > input_bytes + 1024
                or completion > output
            ):
                record["outcome"] = "response_contract_failed"
                if path is not None:
                    write_evidence(path, record)
                raise ControlError("live_response_contract_failed", 503)
            run.context()  # Expiry/revocation fences response release too.
            record["outcome"] = "usage_settled_response_received"
            if path is not None:
                write_evidence(path, record)
            return result
        except ControlError:
            raise
        except Exception:
            raise ControlError("live_attempt_unavailable", 503) from None

    def json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        try:
            return self._json(
                role=role,
                tier=tier,
                system=system,
                user=user,
                max_tokens=max_tokens,
                reasoning_effort=reasoning_effort,
            )
        except ControlError as exc:
            self.run.block(exc.code)
            raise
        except Exception:
            self.run.block("live_response_invalid")
            raise ControlError("live_response_invalid", 503) from None

    def _json(self, *, role, tier, system, user, max_tokens=800, reasoning_effort=None):
        p = self.run.profile
        if role not in p["stages"] or tier != ("strong" if role == "reasoner" else "fast"):
            raise ControlError("live_stage_not_granted", 403)
        effort = reasoning_effort or ("medium" if role == "reasoner" else "none")
        if effort not in ({"medium", "high"} if role == "reasoner" else {"none"}):
            raise ControlError("live_reasoning_mismatch", 503)
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for index in range(2):
            result = self._attempt(
                role,
                {
                    "model": p["model"],
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                    "reasoning_effort": effort,
                    "format_attempt_index": index + 1,
                },
            )
            text = self._extract_text(result)
            parsed = parse_json(text)
            if isinstance(parsed, dict):
                if role == "classifier":
                    confidence = parsed.get("confidence")
                    if (
                        type(parsed.get("flagged")) is not bool
                        or isinstance(confidence, bool)
                        or not isinstance(confidence, (int, float))
                    ):
                        raise ControlError("live_classifier_invalid", 503)
                    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                        raise ControlError("live_classifier_invalid", 503)
                return parsed
            if role == "classifier":
                raise ControlError("live_classifier_invalid", 503)
            messages = [
                *messages,
                {"role": "assistant", "content": text},
                {
                    "role": "user",
                    "content": "Return ONLY the JSON object. No prose, no markdown fences.",
                },
            ]
        raise ControlError("live_json_invalid", 503)


def install(run):
    from ..agent import injection_guard, llm

    class BoundProvider(LiveClassroomProvider):
        def __init__(self):
            super().__init__(run)

    llm._PROVIDERS["openai_compatible"] = BoundProvider

    class StrictGuard(injection_guard.InjectionGuard):
        def check(self, text):
            try:
                verdict = super().check(text)
            except ControlError:
                raise
            except Exception:
                raise ControlError("live_classifier_unavailable", 503) from None
            if verdict.error or verdict.model_used != run.profile["model"]:
                raise ControlError("live_classifier_unavailable", 503)
            return verdict

    injection_guard._guard_instance = StrictGuard()
