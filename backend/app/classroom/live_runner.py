# SPDX-License-Identifier: AGPL-3.0-only
"""Live-profile-only container backend; never falls back to a host interpreter."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath

from ..controls.contracts import ControlError
from ..controls.runtime import attempt_reference
from ..core.runner import RunnerResult
from ..packs.datascience.nhanes_check import FAILURES as NHANES_FAILURES
from ..packs.datascience.nhanes_check import SUCCESS as NHANES_SUCCESS
from .assignments import NHANES
from .demo import EXERCISE
from .live_provider import write_evidence

ROOT = Path(__file__).parents[1]

_TIDY_SUCCESS = "All source cells, keys and missingness retained (row order ignored)."
_TIDY_FAILURES = frozenset(
    {
        "source_preserved: keep country_inflation unchanged.",
        "columns: provide country, year, annual_inflation in that order.",
        "row_count: retain one row for every source country/year cell, including missing cells.",
        "year_type: represent each year as an integer, not text or a float.",
        "keys: retain the source country names and four-digit years.",
        "duplicate_key: each country/year pair must occur once.",
        "keys: retain exactly the source country/year pairs.",
        "missingness: retain missing cells as missing; do not drop or fill them.",
        "numeric_value: retain finite numeric inflation values.",
        "source_value: at least one value differs from its source cell.",
        "method: use the assignment's melt() or pivot_table() requirement.",
    }
)


def checked_inputs(program, files, artifacts, profile, exercise=EXERCISE):
    """Only the reviewed grader/harness and current synthetic exercise are staged."""
    if artifacts or not isinstance(files, dict):
        raise ControlError("live_runner_inputs_invalid", 503)
    if exercise == EXERCISE:
        expected = {
            "spec.json": ROOT / "packs/datascience/specs" / (EXERCISE + ".json"),
            "tidy_check.py": ROOT / "packs/datascience/tidy_check.py",
            "data/info511-inflation-synthetic.csv": ROOT
            / "packs/datascience/specs/data/info511-inflation-synthetic.csv",
        }
    elif exercise == NHANES[0]:
        expected = {
            "spec.json": ROOT / "packs/datascience/specs" / (exercise + ".json"),
            "nhanes_check.py": ROOT / "packs/datascience/nhanes_check.py",
            **{
                name: ROOT / "packs/datascience/specs" / name
                for name in ("data/DEMO_L_selected.csv", "data/BPXO_L_selected.csv")
            },
        }
    else:
        raise ControlError("live_runner_inputs_invalid", 503)
    if (
        set(files) != {*expected, "student.py"}
        or program != (ROOT / "packs/datascience/_harness.py").read_text()
    ):
        raise ControlError("live_runner_inputs_invalid", 503)
    result = {"__program__.py": program.encode()}
    for name, value in files.items():
        rel = PurePosixPath(name)
        if (
            rel.is_absolute()
            or ".." in rel.parts
            or str(rel) != name
            or not isinstance(value, (str, bytes))
        ):
            raise ControlError("live_runner_path_invalid", 503)
        content = value.encode() if isinstance(value, str) else value
        if name in expected:
            trusted = expected[name].read_bytes()
            if name == "spec.json":
                if json.loads(content) != json.loads(trusted):
                    raise ControlError("live_runner_spec_mismatch", 503)
            elif content != trusted:
                raise ControlError("live_runner_input_mismatch", 503)
        result[name] = content
    if (
        len(result) > profile["input_files"]
        or sum(map(len, result.values())) > profile["input_bytes"]
    ):
        raise ControlError("live_runner_input_limit", 413)
    return result


def checked_verdict(stdout, exercise=EXERCISE):
    if exercise == EXERCISE:
        check_type, success, failures = "tidy_source_cells", _TIDY_SUCCESS, _TIDY_FAILURES
    elif exercise == NHANES[0]:
        check_type, success, failures = (
            "nhanes_participant_readings",
            NHANES_SUCCESS,
            NHANES_FAILURES,
        )
    else:
        raise ControlError("live_verifier_unavailable", 503)
    lines = stdout.splitlines()
    if len(lines) != 1 or not lines[0].startswith("__GRADE__"):
        raise ControlError("live_verifier_unavailable", 503)
    try:
        value = json.loads(lines[0][9:])
        if (
            not isinstance(value, dict)
            or type(value.get("ok")) is not bool
            or type(value.get("goalMet")) is not bool
            or not isinstance(value.get("checks"), list)
            or not isinstance(value.get("stdout"), str)
            or value.get("metric") is not None
        ):
            raise ValueError("malformed verdict")
        error = value.get("error")
        if error is not None and (
            not isinstance(error, str)
            or error.startswith(("ImportError:", "ModuleNotFoundError:", "MemoryError:"))
        ):
            raise ValueError("unavailable verifier")
        if value["ok"]:
            checks = value["checks"]
            if (
                error is not None
                or len(checks) != 1
                or checks[0].get("type") != check_type
                or type(checks[0].get("ok")) is not bool
                or not isinstance(checks[0].get("detail"), str)
                or value["goalMet"] != checks[0]["ok"]
            ):
                raise ValueError("invalid check")
            check = checks[0]
            if (check["ok"] and check["detail"] != success) or (
                not check["ok"] and check["detail"] not in failures
            ):
                raise ValueError("unknown or untruthful checker detail")
        elif not error or value["goalMet"] or value["checks"]:
            raise ValueError("invalid error verdict")
        return {
            "ok": value["ok"],
            "goal_met": value["goalMet"],
            "check_count": len(value["checks"]),
        }
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ControlError("live_verifier_unavailable", 503) from None


def bounded_process(command, seconds, byte_cap):
    """Drain both streams without unbounded communicate(); never log their contents."""
    proc = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        start_new_session=True,
    )
    selector = selectors.DefaultSelector()
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    assert proc.stdout is not None and proc.stderr is not None
    selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
    selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
    deadline = time.monotonic() + max(0.001, seconds)
    reason = None
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                reason = "timeout"
                break
            for key, _ in selector.select(min(0.1, remaining)):
                chunk = os.read(key.fd, 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                target = buffers[key.data]
                if len(target) + len(chunk) > byte_cap:
                    reason = "stdio_limit"
                    break
                target.extend(chunk)
            if reason:
                break
        if reason:
            proc.kill()
        try:
            code = proc.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
            reason, code = "timeout", None
        return code, bytes(buffers["stdout"]), bytes(buffers["stderr"]), reason
    finally:
        selector.close()
        proc.stdout.close()
        proc.stderr.close()
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=2)


class ContainerRunner:
    def __init__(self, run):
        self.run = run
        self.profile = run.profile["runner"]
        self.docker = self.profile["docker_binary"]

    def cli(self, *args, seconds=5):
        return bounded_process([self.docker, *args], seconds, self.profile["stdio_bytes_each"])

    def inspect(self, target, image=False):
        code, out, _, reason = self.cli("image" if image else "container", "inspect", target)
        if code != 0 or reason:
            raise ControlError("live_runner_inspection_unavailable", 503)
        try:
            values = json.loads(out)
            if len(values) != 1:
                raise ValueError("ambiguous inspection")
            return values[0]
        except (ValueError, TypeError, KeyError):
            raise ControlError("live_runner_inspection_unavailable", 503) from None

    def preflight(self):
        if self.inspect(self.profile["image_id"], image=True)["Id"] != self.profile["image_id"]:
            raise ControlError("live_runner_image_mismatch", 503)

    def owned(self, name, attempt):
        state = self.inspect(name)
        labels = state["Config"]["Labels"]
        if (
            labels.get("belay.live.attempt") != attempt
            or labels.get("belay.live.operation") != self.run.operation
        ):
            raise ControlError("live_runner_ownership_unavailable", 503)
        return state

    def confinement(self, info):
        h, c = info["HostConfig"], info["Config"]
        p = self.profile
        mounts = info["Mounts"]
        if (
            info["Image"] != p["image_id"]
            or c["User"] != "65534:65534"
            or not h["ReadonlyRootfs"]
            or h["NetworkMode"] != "none"
            or h["Memory"] != p["memory_mb"] * 1048576
            or h["MemorySwap"] != h["Memory"]
            or h["NanoCpus"] != 1000000000
            or h["PidsLimit"] != p["pids"]
            or h["Privileged"]
            or h.get("PidMode") not in {"", "private"}
            or h.get("IpcMode") != "private"
            or h["CapDrop"] != ["ALL"]
            or "no-new-privileges" not in h["SecurityOpt"]
            or any("unconfined" in opt for opt in h["SecurityOpt"])
            or set(h["Tmpfs"]) != {"/tmp"}
            or len(mounts) != 2
            or {m["Destination"] for m in mounts} != {"/input", "/runner/_child.py"}
            or any(m["RW"] or m["Type"] != "bind" for m in mounts)
        ):
            raise ControlError("live_runner_confinement_mismatch", 503)
        expected_tmpfs = {"rw", "noexec", "nosuid", "nodev", "size=67108864", "mode=1777"}
        if set(h["Tmpfs"]["/tmp"].split(",")) != expected_tmpfs:
            raise ControlError("live_runner_confinement_mismatch", 503)

    def __call__(
        self,
        program,
        *,
        files=None,
        artifacts=None,
        cpu_seconds=10,
        memory_mb=None,
        wall_seconds=20,
    ):
        p, run = self.profile, self.run
        run.context(p["wall_seconds"] + 5)
        if (
            cpu_seconds != p["cpu_seconds"]
            or wall_seconds != p["wall_seconds"]
            or memory_mb not in {None, p["memory_mb"]}
        ):
            raise ControlError("live_runner_limits_mismatch", 503)
        inputs = checked_inputs(program, files, artifacts, p, run.profile["exercise_id"])
        attempt = attempt_reference()  # Existing outer runner_call reservation.
        name = "belay-live-" + attempt
        work = Path(tempfile.mkdtemp(prefix="belay-live-runner-"))
        stage = work / "input"
        stage.mkdir()
        for rel, content in inputs.items():
            dest = stage / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
            dest.chmod(0o444)
        bootstrap = work / "_child.py"
        bootstrap.write_bytes((ROOT / "core/runner/_child.py").read_bytes())
        bootstrap.chmod(0o444)
        for folder in [
            *sorted((v for v in stage.rglob("*") if v.is_dir()), reverse=True),
            stage,
            work,
        ]:
            folder.chmod(0o555)
        evidence = {
            "kind": "runner",
            "attempt_id": attempt,
            "operation": run.operation,
            "container_name": name,
            "container_id": None,
            "image_id": p["image_id"],
            "staging_directory": str(work),
            "input_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in inputs.items()},
            "bootstrap_sha256": hashlib.sha256(bootstrap.read_bytes()).hexdigest(),
            "profile_sha256": run.grant["profile_sha256"],
            "source_sha256": run.grant["source_sha256"],
            "limits": p,
            "started_at": time.time(),
            "outcome": "create_pending_or_unknown",
            "stopped_confirmed": False,
            "removed_confirmed": False,
            "cpu_peak_memory_measurement": "not_available_from_container_inspect",
        }
        path = run.directory / "attempt-evidence" / ("runner-" + attempt + ".json")
        write_evidence(path, evidence, new=True)
        start = time.monotonic()
        created, teardown = False, False
        stdout = stderr = b""
        reason = None
        exit_code = None
        try:
            self.preflight()
            command = [
                "create",
                "--pull=never",
                "--name",
                name,
                "--label",
                "belay.live.attempt=" + attempt,
                "--label",
                "belay.live.operation=" + run.operation,
                "--network=none",
                "--read-only",
                "--user=65534:65534",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges",
                "--memory=512m",
                "--memory-swap=512m",
                "--cpus=1",
                "--pids-limit=32",
                "--ulimit",
                "cpu=10:11",
                "--ulimit",
                "nofile=64:64",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,nodev,size=67108864,mode=1777",
                "--workdir=/input",
                "--mount",
                "type=bind,src=" + str(stage) + ",dst=/input,readonly",
                "--mount",
                "type=bind,src=" + str(bootstrap) + ",dst=/runner/_child.py,readonly",
            ]
            for key, value in {
                "HOME": "/tmp",
                "TMPDIR": "/tmp",
                "LANG": "C.UTF-8",
                "PTF_CPU_SECONDS": "10",
                "PTF_MEMORY_MB": "512",
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            }.items():
                command += ["--env", key + "=" + value]
            command += [p["image_id"], "python", "-I", "/runner/_child.py", "/input/__program__.py"]
            # Name/labels are durable BEFORE create. A lost create reply requires operator inspection.
            created = True
            code, out, _, reason = self.cli(*command)
            if code != 0 or reason or not re.fullmatch(rb"[0-9a-f]{64}\n?", out):
                raise ControlError("live_runner_create_unavailable", 503)
            evidence["container_id"] = out.decode().strip()
            info = self.owned(name, attempt)
            self.confinement(info)
            if {m["Destination"]: m["Source"] for m in info["Mounts"]} != {
                "/input": str(stage),
                "/runner/_child.py": str(bootstrap),
            }:
                raise ControlError("live_runner_mount_mismatch", 503)
            write_evidence(path, evidence)
            _, stdout, stderr, reason = self.cli(
                "start",
                "--attach",
                name,
                seconds=max(0.001, wall_seconds - (time.monotonic() - start)),
            )
            info = self.owned(name, attempt)
            if info["State"]["Running"]:
                code, _, _, kill_reason = self.cli("kill", name)
                if code != 0 or kill_reason:
                    raise ControlError("live_runner_stop_unknown", 503)
                info = self.owned(name, attempt)
            if info["State"]["Running"]:
                raise ControlError("live_runner_stop_unknown", 503)
            evidence.update(
                stopped_confirmed=True,
                oom_killed=info["State"]["OOMKilled"],
                exit_code=info["State"]["ExitCode"],
                captured_stdout_bytes=len(stdout),
                captured_stderr_bytes=len(stderr),
                timed_out=reason == "timeout",
                stdio_overflow=reason == "stdio_limit",
            )
            exit_code = info["State"]["ExitCode"]
            if reason or info["State"]["OOMKilled"] or exit_code != 0:
                raise ControlError("live_verifier_unavailable", 503)
            verdict = checked_verdict(stdout.decode("utf-8", "strict"), run.profile["exercise_id"])
            evidence.update(verdict=verdict, outcome="verified_execution_finished")
        finally:
            try:
                if created:
                    info = self.owned(name, attempt)
                    if info["State"]["Running"]:
                        code, _, _, why = self.cli("kill", name)
                        if code != 0 or why:
                            raise ControlError("live_runner_stop_unknown", 503)
                        info = self.owned(name, attempt)
                    if info["State"]["Running"]:
                        raise ControlError("live_runner_stop_unknown", 503)
                    evidence["stopped_confirmed"] = True
                    code, _, _, why = self.cli("rm", name)
                    if code != 0 or why:
                        raise ControlError("live_runner_teardown_unknown", 503)
                    evidence["removed_confirmed"] = True
                teardown = True
            finally:
                evidence["wall_ms"] = round((time.monotonic() - start) * 1000, 1)
                write_evidence(path, evidence)
                if teardown:
                    for folder in [work, stage, *[v for v in stage.rglob("*") if v.is_dir()]]:
                        folder.chmod(0o700)
                    shutil.rmtree(work)
                # Unknown teardown leaves staging and runner liability/slot intact.
        run.context()
        return RunnerResult(
            True,
            exit_code,
            stdout.decode(),
            stderr.decode("utf-8", "replace"),
            False,
            evidence["wall_ms"],
            None,
        )
