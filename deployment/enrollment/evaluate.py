#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded synthetic evaluator; caller supplies pinned local component checkouts."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--cairn', type=Path, required=True)
parser.add_argument('--portage', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
out = args.output.resolve()
out.mkdir(mode=0o700, parents=True, exist_ok=False)
pins = json.loads((root / 'deployment/enrollment/sources.json').read_text())
for name, path in [('cairn', args.cairn), ('portage', args.portage)]:
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=path, text=True)
    if head != pins[name] or dirty:
        raise SystemExit(name + ': exact clean dependency pin required')
commands = [
    (["go", "test", "./internal/enrollment", "-run", "^TestWriteConsumerFixture$", "-count=1"], args.cairn),
    ([sys.executable, "-m", "pytest", "backend/tests/test_enrollment_authority.py", "backend/tests/test_enrollment_portage.py", "-q", "--junitxml=" + str(out / "acceptance.xml")], root),
]
env = {**os.environ, "ENROLLMENT_FIXTURE_DIR": str(out / "fixtures"), "CAIRN_ENROLLMENT_FIXTURES": str(out / "fixtures"), "PORTAGE_CHECKOUT": str(args.portage.resolve())}
record = {"sources": {}, "commands": []}
for name, path in [('cairn', args.cairn), ('belay-classroom', root), ('portage', args.portage)]:
    record['sources'][name] = {"path": str(path.resolve()), "head": subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=path, text=True).strip(), "dirty": subprocess.check_output(['git', 'status', '--porcelain'], cwd=path, text=True)}
for index, (command, cwd) in enumerate(commands):
    with (out / (str(index) + '.log')).open('w') as log:
        try:
            code = subprocess.run(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180).returncode
        except subprocess.TimeoutExpired:
            code = 124
    record['commands'].append({"command": command, "cwd": str(cwd), "exit_code": code})
    (out / 'commands.json').write_text(json.dumps(record, indent=2) + '\n')
    if code:
        raise SystemExit(code)
# A missing native fixture or silently skipped transport cannot pass this gate.
import xml.etree.ElementTree as ET
suite = next(ET.parse(out / 'acceptance.xml').getroot().iter('testsuite'))
if any(int(suite.attrib[k]) for k in ('failures', 'errors', 'skipped')) or int(suite.attrib['tests']) < 22:
    raise SystemExit('acceptance incomplete')
print(json.dumps(suite.attrib))
