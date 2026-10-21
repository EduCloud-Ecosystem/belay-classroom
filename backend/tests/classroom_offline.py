# SPDX-License-Identifier: AGPL-3.0-only
"""Fail loudly if this narrowly scoped test window tries external work."""

import pytest


@pytest.fixture(autouse=True)
def deny_external(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("classroom hermetic window forbids sockets, processes and runner")

    monkeypatch.setattr("socket.create_connection", denied)
    monkeypatch.setattr("socket.socket.connect", denied)
    monkeypatch.setattr("socket.socket.connect_ex", denied)
    monkeypatch.setattr("subprocess.Popen", denied)
    monkeypatch.setattr("app.core.runner.run_python", denied)
