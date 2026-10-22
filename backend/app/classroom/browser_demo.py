# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit one-turn browser host; no inference in an HTTP or background worker thread."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import threading
import time
from http.server import ThreadingHTTPServer

from .assignments import EXERCISE, POLICY, VERSION
from .demo import bind_learner, check_binding
from .live_demo import BACKEND, budget, live_adapter, mark_started, read_turn


def browser_source_manifest():
    frontend = BACKEND.parent / "frontend"
    paths = sorted(
        p
        for folder in (frontend, frontend / "vendor")
        for p in folder.glob("*")
        if p.is_file() and p.suffix in {".html", ".js", ".css"}
    )
    hashes = {
        str(p.relative_to(frontend)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    }
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(), hashes


def reviewed_turn(grant, turn_path):
    turn = read_turn(turn_path)
    if (
        grant.get("browser_source_sha256") != browser_source_manifest()[0]
        or not turn_path
        or grant.get("browser_turn_sha256") != hashlib.sha256(turn_path.read_bytes()).hexdigest()
    ):
        raise ValueError("exact browser assets and synthetic turn review required")
    return turn


def metadata(run, turn):
    # Public synthetic inputs only. No grant, provider credential or identity token.
    return {
        "mode": "live",
        "learner": "bob",
        "exercise_id": EXERCISE,
        "exercise_version": VERSION,
        "request_id": run.grant["request_id"],
        "expires_at": run.grant["expires_at"],
        "message": turn["message"],
        "source": turn["source"],
    }


class BrowserBoundary:
    """Allow only classroom actions, approved unsaved Ask and same-job recovery.

    All allowed routes still use the ordinary application's authentication,
    membership, PII checks, teaching policy and coordinator. This boundary never
    executes inference or substitutes a result, and does not trust UI constants.
    """

    def __init__(self, app, run, turn, origin):
        self.app, self.run, self.turn, self.origin = app, run, turn, origin

    def allowed(self, method, path):
        private = f"/api/classroom/{EXERCISE}/{VERSION}"
        jobs = "/api/sol/jobs"
        reads = {
            "/healthz",
            "/api/curriculum",
            "/api/conversations/config",
            jobs + "/config",
            private,
            jobs + "/" + self.run.operation,
            jobs + "/by-request/" + self.run.grant["request_id"],
        }
        writes = {
            private,
            jobs,
            "/api/participant",
            "/api/overlay",
            jobs + "/by-request/" + self.run.grant["request_id"] + "/reconcile",
        }
        # Existing atomic reconciliation looks up the original job or fences an
        # absent request with a retained tombstone. It never dispatches work.
        return (method == "GET" and path in reads) or (method == "POST" and path in writes)

    def approved_payload(self, body):
        expected = {
            "request_id": self.run.grant["request_id"],
            "participant_id": "edu:2",
            "exercise_id": EXERCISE,
            "exercise_version": VERSION,
            "event": "chat",
            "source": self.turn["source"],
            "recent": [{"who": "student", "text": self.turn["message"]}],
        }
        return (
            isinstance(body, dict)
            and all(body.get(k) == v for k, v in expected.items())
            and body.get("mode") in ("study", "teach")
            and body.get("stance") in ("peer", "oracle", "control")
            and not (set(body) - set(expected) - {"mode", "stance", "result"})
            and body.get("result") is None
        )

    async def __call__(self, scope, receive, send):
        from ..controls.contracts import ControlError

        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            return await send({"type": "websocket.close", "code": 1008})
        method, path = scope["method"], scope["path"]
        headers = dict(scope.get("headers", []))
        try:
            self.run.authority()
            if method == "OPTIONS":
                if not any(self.allowed(m, path) for m in ("GET", "POST")):
                    raise ControlError("live_route_unavailable", 403)
            elif not self.allowed(method, path):
                raise ControlError("live_route_unavailable", 403)
            if method == "POST" and path == "/api/sol/jobs":
                chunks, size = [], 0
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    size += len(chunk)
                    if size > 16384:
                        raise ControlError("payload_too_large", 413)
                    chunks.append(chunk)
                    if not message.get("more_body", False):
                        break
                raw = b"".join(chunks)
                self.run.authority()  # Body delivery cannot extend a revoked/expired grant.
                try:
                    body = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    raise ControlError("request_invalid", 422) from None
                if not self.approved_payload(body):
                    raise ControlError("live_turn_not_granted", 403)

                original_receive = receive
                delivered = False

                async def replay():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {"type": "http.request", "body": raw, "more_body": False}
                    return await original_receive()

                receive = replay
            self.run.authority()
        except ControlError as exc:
            response = json.dumps({"detail": {"code": exc.code}}).encode()
            out = [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]
            if headers.get(b"origin") == self.origin.encode():
                out.append((b"access-control-allow-origin", self.origin.encode()))
                out.append((b"vary", b"Origin"))
            await send({"type": "http.response.start", "status": exc.status, "headers": out})
            return await send({"type": "http.response.body", "body": response})
        return await self.app(scope, receive, send)


def confirm_stopped(run, threads, receipt, stop):
    if any(thread.is_alive() for thread in threads):
        run.block("live_listener_shutdown_unknown")
        raise RuntimeError("listener shutdown unconfirmed")
    receipt.unlink(missing_ok=True)
    stop.unlink(missing_ok=True)


def start(runtime, directory, profile, grant, grant_path, turn_path):
    import uvicorn
    from sqlalchemy import select

    from ..controls.admission import jobs
    from ..controls.contracts import Policy
    from ..controls.jobs_http import execution_store
    from ..controls.worker import run_one
    from .live_provider import LiveRun, install, wall_deadline, write_evidence
    from .live_runner import ContainerRunner

    run = LiveRun(profile, grant, directory, grant_path)
    run.authority()
    run.assert_unblocked()
    turn = reviewed_turn(grant, turn_path)
    check_binding(directory, EXERCISE, VERSION, POLICY)
    store = execution_store()
    with store.ledger.transaction() as conn:
        if (
            store.ledger.policy(conn) != Policy(**budget(profile))
            or conn.execute(select(jobs.c.id)).first()
        ):
            raise ValueError(
                "fresh exact-policy installation required; never replay a previous session"
            )
    manifest = runtime.load(directory)
    for port in (manifest["api_port"], manifest["frontend_port"]):
        runtime.check_loopback_port(port)
    runner = ContainerRunner(run)
    runner.preflight()
    install(run)
    bind_learner(runtime, "bob")
    from ..main import app

    host = runtime.runtime_host(directory, manifest)
    original_bootstrap = host.bootstrap
    public = json.dumps(metadata(run, turn), ensure_ascii=True).encode()
    host.bootstrap = (
        lambda: original_bootstrap() + b"\nwindow.BELAY_CLASSROOM_DEMO = " + public + b";\n"
    )
    boundary = BrowserBoundary(app, run, turn, manifest["frontend_origin"])
    server = uvicorn.Server(uvicorn.Config(boundary, access_log=False, log_level="critical"))
    adapter = live_adapter(run, store, runner)
    api_socket = socket.socket()
    frontend = None
    threads = []
    receipt = directory / "running.json"
    stop = directory / "stop.request"
    worked = False
    try:
        api_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        api_socket.bind(("127.0.0.1", manifest["api_port"]))
        api_socket.listen(32)
        frontend = ThreadingHTTPServer(
            ("127.0.0.1", manifest["frontend_port"]), host.handler(runtime.ROOT / "frontend")
        )
        host.origin = manifest["frontend_origin"]
        # A partial startup, crash or process restart never creates fresh authority.
        mark_started(run)
        runtime.private_write(
            receipt,
            json.dumps(
                {"pid": os.getpid(), "nonce": manifest["nonce"], "lane": "live_browser"}
            ).encode(),
        )
        threads = [
            threading.Thread(target=server.run, kwargs={"sockets": [api_socket]}, daemon=True),
            threading.Thread(target=frontend.serve_forever, daemon=True),
        ]
        for thread in threads:
            thread.start()
        ready = False
        while time.time() < grant["expires_at"] and not stop.exists():
            if not all(thread.is_alive() for thread in threads):
                raise RuntimeError("browser service stopped")
            if server.started and not ready:
                print(
                    json.dumps(
                        {
                            "ready": True,
                            "frontend": host.origin + "/dev-client.html",
                            "lane": "live_browser",
                            "expires_at": grant["expires_at"],
                        }
                    ),
                    flush=True,
                )
                ready = True
            adapter.cleanup()
            if not worked and ready:
                # Only main-thread dispatch; HTTP handlers can only admit/recover.
                with wall_deadline(max(0.001, grant["expires_at"] - time.time())):
                    worked = run_one(store.admission, adapter)
                if worked:
                    write_evidence(
                        directory / "browser-job-finished.json",
                        {
                            "operation": run.operation,
                            "ledger": store.ledger.summary(),
                            "invoice_reconciled": False,
                        },
                        new=True,
                    )
            time.sleep(0.1)
    finally:
        server.should_exit = True
        if frontend is not None:
            if len(threads) == 2 and threads[1].is_alive():
                frontend.shutdown()
            frontend.server_close()
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=10)
        api_socket.close()
        # Preserve the ownership receipt whenever shutdown is uncertain.
        confirm_stopped(run, threads, receipt, stop)
        # A body queued just as the window closed was never executed. Cancel
        # only that known queued operation after HTTP threads have stopped;
        # never settle running/unknown work or erase its retained accounting.
        with store.ledger.transaction() as conn:
            queued = (
                conn.execute(
                    select(jobs.c.state).where(jobs.c.id == run.operation)
                ).scalar_one_or_none()
                == "queued"
            )
        if queued:
            store.admission.cancel(run.scope, run.operation)
        adapter.cleanup()
    return {"stopped": True, "worker_dispatched": worked, "lane": "live_browser"}
