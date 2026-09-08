#!/usr/bin/env python3
"""Interactive-CLI generation arm for bakeoff 9 (T-012).

`drive2.mjs` generates on SDK `query()`. This module is its counterpart on the
*interactive* CLI -- the surface the clause is actually deployed to -- under the
same declared configuration, emitting the same `capture-spine/1` spine T-002
defined. `pty_drive.py` remains as the preserved T-001 capture driver; this
module supersedes it for generation and replaces its deny-list environment
hygiene with an allowlist -- see `ENV_ALLOWLIST` for what that measurement
found.

The declared configuration is hardcoded, for the reason `drive2.mjs:63-68`
gives: a probe that can drift from the freeze cannot validate it.

    --setting-sources project
    --settings {"autoMemoryEnabled":false}
    --tools Bash,Read,Edit,Write,Grep,Glob

Three tiers, unchanged from `scripts/capture_spine.py`:

  raw    transient, outside the repository. Request bodies the loopback probe
         or OTEL wrote, and the pty transcript -- which carries the prompt and
         every byte the model printed. `raw_tier_path` refuses a path inside
         the repository so neither can be written into `sources/` by mistake.
  record durable. Trial entries and the spec, written through
         `capture_spine.write_record`, so the retention scan runs before any
         byte lands.
  text   durable, opt-in, system prompt only. Unchanged.

The admission gate stays a gate. `probes/` refuses a malformed prompt *before* a
request is issued, and this module adds three refusals a pty-driven TUI needs
and an SDK client does not:

  * a prompt carrying a newline submits early and generates a truncated request;
  * a prompt opening `!`, `/` or `#` is consumed by the TUI's bash, slash-command
    and memory prefixes and never becomes an ordinary turn;
  * a prompt carrying credential-shaped text must not reach a transcript.

`run_trial` refuses a non-loopback endpoint outright unless it is handed an
explicit authorization string *and* a preflight receipt that admitted the
declared surface. Loopback is the default and needs neither.

Usage:
    python3 probes/cli_drive.py preflight --binary BIN --cwd DIR --config-dir DIR \\
        --baseline sources/2026-08-24-t001-surface-cli-declared.json --out receipt.json
    python3 probes/cli_drive.py trial --binary BIN --cwd DIR --config-dir DIR \\
        --fixture-id b1e-... --stratum b1-easy --prompt-file P --out trial.json
    python3 probes/cli_drive.py spec trial-*.json --out spec.json --baseline cli=BASE.json
    python3 scripts/capture_spine.py ingest spec.json --out manifest.json
"""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import capture_spine as cs  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]

# -- the declared configuration, as freeze constants ------------------------

SETTING_SOURCES = ("project",)
DECLARED_SETTINGS = {"autoMemoryEnabled": False}
TOOL_SURFACE = ("Bash", "Read", "Edit", "Write", "Grep", "Glob")
TOOL_SURFACE_OPTION = "--tools"

# pty factors. Carried from `pty_drive.py`, recorded in every manifest, and
# measured against the request surfaces rather than assumed neutral -- see
# `sources/2026-08-25-t012-cli-arm-instrument.md`.
PTY_ROWS = 40
PTY_COLS = 120
PTY_TERM = "xterm-256color"
MOUNT_WAIT = 8.0
SETTLE_WAIT = 3.0
DEADLINE = 120.0

GENERATOR = "cli-interactive-pty"

# The child environment is an allowlist, not a deny-list.
#
# `pty_drive.py` and `drive2.mjs` copy the parent environment and delete named
# auth keys. Measured 2026-08-25 inside a Claude Code session, that parent
# carries eleven `CLAUDE*`/`ANTHROPIC*` variables, and that deny-list names three
# of them; eight survive it. Two of the eight are why this is an allowlist:
# `CLAUDE_CODE_MESSAGING_TOKEN` is a credential, and `CLAUDE_CODE_CHILD_SESSION`
# makes the child print "Transcript saving is off" and write **no session
# JSONL** -- which is half the T-002 spine. A deny-list is only as good as the
# last time someone read the parent's environment.
ENV_ALLOWLIST = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "LC_ALL",
                 "LC_CTYPE", "TZ", "TMPDIR")

# Anything auth-shaped must be absent from the child by construction; this is
# the assertion, checked by `env_problems`, not the mechanism.
AUTH_SHAPED = re.compile(
    r"(TOKEN|SECRET|CREDENTIAL|PASSWORD|SESSION_ID|OAUTH|API_KEY|APIKEY)", re.I)

MODEL_ROLE_VARS = (
    "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL",
)

DUMMY_KEY = "sk-ant-dummy-capture-not-a-real-key"

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]")

MAX_PROMPT_CHARS = 1024
TUI_PREFIXES = ("!", "/", "#")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
REMINDER_BLOCK = re.compile(r"<system-reminder>.*?</system-reminder>\s*", re.S | re.I)


class PromptRefused(ValueError):
    """The admission gate refused a prompt. No request was issued."""


class NotAuthorized(RuntimeError):
    """A non-loopback endpoint was requested without authorization."""


# -- admission gate --------------------------------------------------------


def prompt_problems(prompt: str) -> list[str]:
    """Why this prompt cannot be typed into the TUI. Empty means admissible."""
    problems = []
    if not prompt or not prompt.strip():
        problems.append("prompt is empty")
    if "\n" in prompt or "\r" in prompt:
        problems.append("prompt contains a newline: the TUI submits on Enter, so the "
                        "request would carry only the first line")
    stray = sorted({c for c in CONTROL_CHARS.findall(prompt) if c not in "\n\r"})
    if stray:
        problems.append("prompt contains control characters: "
                        + ", ".join(hex(ord(c)) for c in stray))
    if prompt[:1] in TUI_PREFIXES:
        problems.append(f"prompt opens with {prompt[:1]!r}, a TUI prefix "
                        "(! bash, / slash command, # memory); it does not become a model turn")
    if len(prompt) > MAX_PROMPT_CHARS:
        problems.append(f"prompt is {len(prompt)} characters, over the {MAX_PROMPT_CHARS} "
                        "the driver admits")
    if cs.redact(prompt) != prompt:
        problems.append("prompt contains credential-shaped text and must not reach a transcript")
    return problems


def admit_prompt(prompt: str) -> str:
    """Return the prompt, or raise before anything is spent."""
    problems = prompt_problems(prompt)
    if problems:
        raise PromptRefused("; ".join(problems))
    return prompt


# -- endpoint guard --------------------------------------------------------


def is_loopback(base_url: str) -> bool:
    match = re.match(r"^https?://([^/:]+|\[[^\]]+\])(:\d+)?/?$", base_url or "")
    return bool(match) and match.group(1) in LOOPBACK_HOSTS


def check_endpoint(base_url: str, *, authorization: str | None, receipt: dict | None) -> None:
    if is_loopback(base_url):
        return
    if not authorization:
        raise NotAuthorized(
            f"{base_url} is not loopback and no authorization was supplied. "
            "Paid generation needs an explicit per-run authorization.")
    if not receipt or not receipt.get("admitted"):
        raise NotAuthorized(
            "paid generation needs a preflight receipt whose surfaces matched the arm baseline")
    if receipt.get("declared_configuration") != declared_configuration():
        raise NotAuthorized(
            "the preflight receipt was taken under a different declared configuration")


# -- raw tier --------------------------------------------------------------


def raw_tier_path(path) -> Path:
    """A transient path, refused if it is inside the repository.

    The pty transcript carries the prompt and every byte the model printed, and
    the captured bodies carry the reminder payload and a dummy `x-api-key`.
    Neither is a durable record. `capture_spine.purge_raw` applies the same rule
    to the raw directory; this applies it before anything is written.
    """
    resolved = Path(path).resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise ValueError(f"raw-tier path is inside the repository: {resolved}")
    return resolved


# -- configuration ---------------------------------------------------------


def settings_argument() -> str:
    return json.dumps(DECLARED_SETTINGS, separators=(",", ":"))


def declared_argv(binary: str, model: str, extra=()) -> list[str]:
    """The interactive CLI invocation. No `--print`: `--print` reports
    `cc_entrypoint=sdk-cli`, which is a different host, not this arm."""
    return [
        str(binary),
        "--model", model,
        "--setting-sources", ",".join(SETTING_SOURCES),
        "--settings", settings_argument(),
        TOOL_SURFACE_OPTION, ",".join(TOOL_SURFACE),
        *extra,
    ]


def declared_configuration() -> dict:
    return {
        "generator": GENERATOR,
        "setting_sources": list(SETTING_SOURCES),
        "declared_settings": dict(DECLARED_SETTINGS),
        "tool_surface_option": TOOL_SURFACE_OPTION,
        "tool_surface": list(TOOL_SURFACE),
    }


def child_env(parent: dict, *, base_url: str, config_dir: str, api_key: str = DUMMY_KEY,
              raw_bodies_dir: str | None = None, rows: int = PTY_ROWS,
              cols: int = PTY_COLS, term: str = PTY_TERM,
              model_roles: dict | None = None) -> dict:
    """The child environment, built from `ENV_ALLOWLIST` rather than inherited.

    `DISABLE_TELEMETRY=1` is set and is never removed: measured n=2 per
    condition, dropping it moves `tools_sha256` 5dbd88f2 -> 0e26c506 and takes
    330 characters out of system block 2
    (`sources/2026-08-24-t002-capture-spine.md`). The OTEL export variables are
    request-neutral only on top of it.

    `ANTHROPIC_API_KEY` is the loopback dummy by default. A subscription-auth
    run passes `api_key=None`, which leaves the variable unset rather than
    empty -- an empty value is still a value to the CLI.
    """
    env = {k: parent[k] for k in ENV_ALLOWLIST if parent.get(k) is not None}
    env["ANTHROPIC_BASE_URL"] = base_url
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    env["DISABLE_TELEMETRY"] = "1"
    env["DISABLE_ERROR_REPORTING"] = "1"
    env["DISABLE_AUTOUPDATER"] = "1"
    env["DISABLE_NON_ESSENTIAL_MODEL_CALLS"] = "1"
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    env["TERM"] = term
    env["COLUMNS"] = str(cols)
    env["LINES"] = str(rows)
    if raw_bodies_dir:
        env["CLAUDE_CODE_ENABLE_TELEMETRY"] = "1"
        env["OTEL_LOGS_EXPORTER"] = "console"
        env["OTEL_METRICS_EXPORTER"] = ""
        env["OTEL_LOG_RAW_API_BODIES"] = f"file:{raw_bodies_dir}"
    for name, value in (model_roles or {}).items():
        if name not in MODEL_ROLE_VARS:
            raise ValueError(f"not a model-role variable: {name}")
        env[name] = value
    problems = env_problems(env)
    if problems:
        raise ValueError("child environment is not clean: " + "; ".join(problems))
    return env


def env_problems(env: dict) -> list[str]:
    """Auth-shaped names that reached the child. Empty means clean.

    `ANTHROPIC_API_KEY` is exempt only when it holds this module's dummy: the
    loopback probe needs a key present, and no other value may be handed to a
    child this driver starts.
    """
    problems = []
    for name, value in env.items():
        if name == "ANTHROPIC_API_KEY":
            if value != DUMMY_KEY:
                problems.append("ANTHROPIC_API_KEY is set to something other than the "
                                "loopback dummy")
            continue
        if AUTH_SHAPED.search(name):
            problems.append(f"auth-shaped variable reached the child: {name}")
    return problems


def ensure_config(config_dir, cwd, *, approve_dummy_key: bool = False) -> Path:
    """Write the minimal config stub that lets the TUI reach a model turn.

    Measured 2026-08-25: with an empty `CLAUDE_CONFIG_DIR` the interactive CLI
    stops on the *trust this folder* dialog and issues no request at all. Every
    trial gets its own fixture directory, so that dialog fires on every trial
    unless the directory is pre-trusted -- this is a hard requirement of the arm,
    not a convenience.

    `approve_dummy_key` pre-answers the *custom API key detected* dialog, which
    only appears because loopback capture sets `ANTHROPIC_API_KEY`. It records
    the suffix of this module's dummy key and cannot be made to record any
    other value; a subscription-auth run leaves it off.
    """
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / ".claude.json"
    config = json.loads(path.read_text()) if path.is_file() else {}
    config.update({
        "hasCompletedOnboarding": True,
        "installMethod": "native",
        "autoUpdates": False,
        "numStartups": max(5, config.get("numStartups", 0)),
    })
    projects = config.setdefault("projects", {})
    projects[str(Path(cwd).resolve())] = {
        "allowedTools": [],
        "hasTrustDialogAccepted": True,
        "hasCompletedProjectOnboarding": True,
        "projectOnboardingSeenCount": 5,
        "mcpServers": {},
        "enabledMcpjsonServers": [],
        "disabledMcpjsonServers": [],
    }
    if approve_dummy_key:
        config["customApiKeyResponses"] = {"approved": [DUMMY_KEY[-20:]], "rejected": []}
    path.write_text(json.dumps(config, indent=2))
    return path


# -- loopback probe --------------------------------------------------------


class LoopbackProbe:
    """`probes/server.py` as a context manager, recording every request.

    server.py captures the first `POST /v1/messages` and stops. A generation
    driver needs every turn's body, so this writes `req-<n>.json` per request
    into a raw-tier directory in the same wrapper shape
    (`capture_spine.request_body` reads it), and answers the same synthetic 401.
    """

    def __init__(self, raw_dir):
        self.raw_dir = raw_tier_path(raw_dir)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.count = 0
        self._lock = threading.Lock()
        probe = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            timeout = 5

            def log_message(self, *args):
                pass

            def _hello(self):
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_HEAD = _hello
            do_GET = _hello

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                if "/v1/messages" in self.path:
                    probe._record(self.path, dict(self.headers.items()), body)
                payload = json.dumps({"type": "error", "error": {
                    "type": "authentication_error",
                    "message": "synthetic capture stop"}}).encode()
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_port
        self.base_url = f"http://127.0.0.1:{self.port}"

    def _record(self, path, headers, body):
        try:
            parsed = json.loads(body.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            return
        with self._lock:
            self.count += 1
            index = self.count
        (self.raw_dir / f"req-{index:03d}.json").write_text(json.dumps(
            {"path": path, "headers": headers, "body": parsed}, indent=2))

    def __enter__(self):
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._server.shutdown()
        self._server.server_close()
        return False


# -- pty driver ------------------------------------------------------------


def drive(*, argv, env, cwd, prompt, tty_log, rows=PTY_ROWS, cols=PTY_COLS,
          mount_wait=MOUNT_WAIT, settle_wait=SETTLE_WAIT, deadline=DEADLINE,
          done=None):
    """Type one admitted prompt into the interactive CLI and wait.

    `done()` decides when the turn is finished. On loopback that is "a body
    landed"; under a real endpoint the caller supplies a completion predicate.
    Returns a status dict and never the transcript.
    """
    admit_prompt(prompt)
    log_path = raw_tier_path(tty_log)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - the child never returns
        try:
            os.chdir(cwd)
            os.execve(argv[0], argv, env)
        finally:
            os._exit(127)

    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    log = open(log_path, "wb")
    start = time.time()
    sent = False
    status = "unknown"
    try:
        while True:
            if time.time() - start > deadline:
                status = "deadline"
                break
            readable, _, _ = select.select([fd], [], [], 0.25)
            if readable:
                try:
                    data = os.read(fd, 65536)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        status = "child-exited"
                        break
                    raise
                if not data:
                    status = "child-eof"
                    break
                log.write(data)
                log.flush()
            if not sent and time.time() - start > mount_wait:
                os.write(fd, prompt.encode())
                time.sleep(0.6)
                os.write(fd, b"\r")
                sent = True
            if sent and done is not None and done() and time.time() - start > mount_wait + 4:
                time.sleep(settle_wait)
                status = "complete"
                break
    finally:
        log.close()
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(pid, sig)
            except OSError:
                pass
            time.sleep(0.5)
        try:
            os.waitpid(pid, os.WNOHANG)
        except OSError:
            pass
        os.close(fd)

    return {
        "status": status,
        "prompt_sent": sent,
        "elapsed_s": round(time.time() - start, 1),
        "tty_log_bytes": log_path.stat().st_size if log_path.exists() else 0,
        "pty": {"rows": rows, "cols": cols, "term": env.get("TERM"),
                "mount_wait_s": mount_wait},
    }


# -- prompt fidelity -------------------------------------------------------


AUXILIARY_DIR = "auxiliary"


def is_auxiliary(raw: dict) -> bool:
    """A request the CLI makes beside the model turn, not the turn itself.

    Measured 2026-08-25, n=8 at a 219-character prompt, n=2 at an 88-character
    one, and n=0 at a 4-character one: the interactive CLI issues a **session-title** request
    alongside the turn -- same model, `max_tokens: 64000`,
    `output_config.effort: high`, `thinking: {type: disabled}`, a
    `json_schema` output format, **no tools**, no `<system-reminder>`, and the
    whole user prompt inside a `<session>` block. `DISABLE_TELEMETRY=1` and
    `DISABLE_NON_ESSENTIAL_MODEL_CALLS=1` do not suppress it.

    It matters twice. On a paid endpoint it is a second billed Opus 5 call per
    trial. In the spine it is a second `surface_key` group, so
    `capture_spine.observed_surfaces` reports `distinct_surfaces: 2`, the trial
    grades `mismatch`, and `validate_manifest` rejects the manifest -- a healthy
    trial failing on a request that is not the trial's.

    The arm always carries the six declared tools and always carries the
    reminder, so "no tools and no reminder" separates the two without needing to
    recognise the title prompt itself.
    """
    body = cs.request_body(raw)
    if body.get("tools"):
        return False
    for message in body.get("messages") or []:
        content = message.get("content")
        texts = [content] if isinstance(content, str) else [
            b.get("text", "") for b in content or [] if isinstance(b, dict)]
        if any(cs.REMINDER_TAG.search(t or "") for t in texts):
            return False
    return True


def partition_auxiliary(raw_dir) -> int:
    """Move auxiliary bodies into `<raw_dir>/auxiliary/`. Returns how many.

    `capture_spine.raw_body_paths` lists files, not directories, so the spine
    then sees the trial's own turns and nothing else. Nothing is deleted: the
    auxiliary bodies stay in the raw tier, where a reader can still count them.
    """
    raw_dir = Path(raw_dir)
    if not raw_dir.is_dir():
        return 0
    moved = 0
    destination = raw_dir / AUXILIARY_DIR
    for path in cs.raw_body_paths(raw_dir):
        try:
            raw = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(raw, dict) and is_auxiliary(raw):
            destination.mkdir(exist_ok=True)
            path.rename(destination / path.name)
            moved += 1
    return moved


def prompt_echo(raw: dict) -> str | None:
    """The first user message's text with reminder blocks removed.

    Typed input is the one part of a pty arm an SDK arm does not have, and a
    dropped or reordered character produces a request that looks healthy on all
    four surfaces. This is what makes the difference checkable.
    """
    body = cs.request_body(raw)
    for message in body.get("messages") or []:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            texts = [content]
        elif isinstance(content, list):
            texts = [b.get("text", "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text"]
        else:
            continue
        return REMINDER_BLOCK.sub("", "".join(texts)).strip()
    return None


def prompt_fidelity(raw_dir, prompt: str) -> dict:
    """Whether the typed prompt arrived intact. Records verdict and hash only."""
    paths = cs.raw_body_paths(Path(raw_dir))
    if not paths:
        return {"verdict": "unrecorded", "bodies": 0}
    echo = prompt_echo(json.loads(paths[0].read_text()))
    if echo is None:
        return {"verdict": "unrecorded", "bodies": len(paths)}
    return {
        "verdict": "exact" if echo == prompt else "mismatch",
        "bodies": len(paths),
        "expected_chars": len(prompt),
        "observed_chars": len(echo),
        "expected_sha256": cs.sha256_text(prompt),
        "observed_sha256": cs.sha256_text(echo),
    }


# -- session spine ---------------------------------------------------------


def session_slug(cwd) -> str:
    """Claude Code's project-directory slug: the absolute path, punctuation to `-`."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(cwd).resolve()))


def session_files(config_dir, cwd) -> list[Path]:
    """Session JSONL for one working directory, newest last."""
    project = Path(config_dir) / "projects" / session_slug(cwd)
    if not project.is_dir():
        return []
    return sorted((p for p in project.glob("*.jsonl")), key=lambda p: p.stat().st_mtime)


# -- trial and spec --------------------------------------------------------


def trial_entry(*, trial_id, arm, fixture_id, stratum, cwd, raw_dir, session=None,
                driver=None, fidelity=None) -> dict:
    """One entry in a `capture_spine` ingest spec, plus this arm's own fields.

    `capture_spine.build_manifest` reads `trial_id`, `arm`, `fixture_id`,
    `stratum`, `cwd`, `raw_dir` and `session` and ignores the rest, so the pty
    factors ride along into the manifest without extending the schema.
    """
    entry = {
        "trial_id": trial_id,
        "arm": arm,
        "fixture_id": fixture_id,
        "stratum": stratum,
        "cwd": str(cwd),
        "raw_dir": str(raw_dir),
    }
    if session:
        entry["session"] = str(session)
    if driver:
        entry["driver"] = driver
    if fidelity:
        entry["prompt_fidelity"] = fidelity
    return entry


def environment_block(*, binary, binary_version=None, binary_sha256=None, model,
                      pty_factors, inference_purchased, model_roles=None,
                      raw_body_capture=None) -> dict:
    """`capture-spine/1`'s free-form `environment` pins for this arm.

    Additive: the schema version is not touched and no second manifest shape is
    defined. `pty` is recorded because it is a harness parameter that has to be
    reproducible, and because it is a candidate treatment.
    """
    block = dict(declared_configuration())
    block.update({
        "binary": str(binary),
        "binary_version": binary_version,
        "binary_sha256": binary_sha256,
        "model": model,
        "pty": dict(pty_factors),
        "inference_purchased": bool(inference_purchased),
    })
    if model_roles:
        block["model_roles"] = dict(model_roles)
    if raw_body_capture:
        block["raw_body_capture"] = raw_body_capture
    return block


def build_spec(entries, *, campaign, run_id, baselines, environment) -> dict:
    return {
        "campaign": campaign,
        "run_id": run_id,
        "baselines": dict(baselines),
        "environment": dict(environment),
        "trials": list(entries),
    }


# -- runs ------------------------------------------------------------------


def run_trial(*, binary, model, cwd, config_dir, prompt, raw_dir, tty_log,
              trial_id="trial-1", arm="cli", fixture_id=None, stratum=None,
              base_url=None, authorization=None, receipt=None,
              rows=PTY_ROWS, cols=PTY_COLS, term=PTY_TERM,
              mount_wait=MOUNT_WAIT, extra_args=(), model_roles=None,
              raw_bodies_dir=None, parent_env=None, deadline=DEADLINE,
              bootstrap_config=True) -> dict:
    """One interactive-CLI trial. Loopback unless explicitly authorized."""
    admit_prompt(prompt)
    check_endpoint(base_url or "http://127.0.0.1:0",
                   authorization=authorization, receipt=receipt)
    raw_dir = raw_tier_path(raw_dir)
    if bootstrap_config:
        ensure_config(config_dir, cwd, approve_dummy_key=base_url is None)

    if base_url is None:
        probe = LoopbackProbe(raw_dir)
        with probe:
            env = child_env(parent_env if parent_env is not None else os.environ,
                            base_url=probe.base_url, config_dir=config_dir,
                            raw_bodies_dir=raw_bodies_dir, rows=rows, cols=cols,
                            term=term, model_roles=model_roles)
            driver = drive(argv=declared_argv(binary, model, extra_args), env=env,
                           cwd=cwd, prompt=prompt, tty_log=tty_log, rows=rows,
                           cols=cols, mount_wait=mount_wait, deadline=deadline,
                           done=lambda: probe.count > 0)
        driver["requests_captured"] = probe.count
        purchased = False
    else:  # pragma: no cover - never exercised: no paid call is authorized
        env = child_env(parent_env if parent_env is not None else os.environ,
                        base_url=base_url, config_dir=config_dir,
                        api_key=None,
                        raw_bodies_dir=raw_bodies_dir or str(raw_dir), rows=rows,
                        cols=cols, term=term, model_roles=model_roles)
        driver = drive(argv=declared_argv(binary, model, extra_args), env=env,
                       cwd=cwd, prompt=prompt, tty_log=tty_log, rows=rows,
                       cols=cols, mount_wait=mount_wait, deadline=deadline,
                       done=None)
        purchased = True

    driver["auxiliary_requests"] = partition_auxiliary(raw_dir)
    driver["turn_requests"] = len(cs.raw_body_paths(raw_dir))
    driver["inference_purchased"] = purchased
    sessions = session_files(config_dir, cwd)
    return trial_entry(
        trial_id=trial_id, arm=arm, fixture_id=fixture_id, stratum=stratum,
        cwd=cwd, raw_dir=raw_dir, session=sessions[-1] if sessions else None,
        driver=driver, fidelity=prompt_fidelity(raw_dir, prompt))


def grade_preflight(entry: dict, baseline: dict | None, *, label=None) -> dict:
    """Grade a captured trial against an arm baseline. Pure; no process runs."""
    surfaces = cs.observed_surfaces(Path(entry["raw_dir"]), baseline)
    if not surfaces:
        verdict, differing = "unrecorded", None
    elif baseline is None:
        verdict, differing = "unchecked", None
    else:
        differing = sorted({s for group in surfaces
                            for s in group.get("differing_surfaces") or []})
        verdict = "match" if not differing else "mismatch"
    return {
        "label": label or entry.get("trial_id"),
        "declared_configuration": declared_configuration(),
        "pty": (entry.get("driver") or {}).get("pty"),
        "prompt_fidelity": entry.get("prompt_fidelity"),
        "surface_verdict": verdict,
        "differing_surfaces": differing,
        "distinct_surfaces": len(surfaces),
        "request_surfaces": surfaces,
        "admitted": verdict == "match",
    }


# -- command line ----------------------------------------------------------


def _common(p):
    p.add_argument("--binary", required=True)
    p.add_argument("--model", default="claude-opus-5")
    p.add_argument("--cwd", required=True)
    p.add_argument("--config-dir", required=True)
    p.add_argument("--raw-dir", required=True, help="transient, outside the repository")
    p.add_argument("--tty-log", required=True, help="transient, outside the repository")
    p.add_argument("--rows", type=int, default=PTY_ROWS)
    p.add_argument("--cols", type=int, default=PTY_COLS)
    p.add_argument("--term", default=PTY_TERM)
    p.add_argument("--mount-wait", type=float, default=MOUNT_WAIT)
    p.add_argument("--deadline", type=float, default=DEADLINE)
    p.add_argument("--extra-arg", action="append", default=[])
    p.add_argument("--out", type=Path)


def _cmd_preflight(args) -> int:
    baseline = json.loads(Path(args.baseline).read_text()) if args.baseline else None
    entry = run_trial(binary=args.binary, model=args.model, cwd=args.cwd,
                      config_dir=args.config_dir, prompt=args.prompt,
                      raw_dir=args.raw_dir, tty_log=args.tty_log,
                      trial_id=args.label or "preflight", rows=args.rows,
                      cols=args.cols, term=args.term, mount_wait=args.mount_wait,
                      extra_args=args.extra_arg, deadline=args.deadline)
    receipt = grade_preflight(entry, baseline, label=args.label)
    receipt["driver"] = entry.get("driver")
    if args.out:
        cs.write_record(args.out, receipt)
        print(f"wrote {args.out}: {receipt['surface_verdict']}")
    else:
        print(json.dumps(receipt, indent=2))
    return 0 if receipt["surface_verdict"] in ("match", "unchecked") else 1


def _cmd_trial(args) -> int:
    prompt = args.prompt if args.prompt is not None else Path(args.prompt_file).read_text().strip()
    entry = run_trial(binary=args.binary, model=args.model, cwd=args.cwd,
                      config_dir=args.config_dir, prompt=prompt,
                      raw_dir=args.raw_dir, tty_log=args.tty_log,
                      trial_id=args.trial_id, fixture_id=args.fixture_id,
                      stratum=args.stratum, rows=args.rows, cols=args.cols,
                      term=args.term, mount_wait=args.mount_wait,
                      extra_args=args.extra_arg, deadline=args.deadline)
    if args.out:
        cs.write_record(args.out, entry)
        print(f"wrote {args.out}")
    else:
        print(json.dumps(entry, indent=2))
    return 0 if (entry.get("prompt_fidelity") or {}).get("verdict") == "exact" else 1


def _cmd_spec(args) -> int:
    entries = [json.loads(Path(p).read_text()) for p in args.trials]
    baselines = dict(pair.split("=", 1) for pair in args.baseline)
    environment = environment_block(
        binary=args.binary, binary_version=args.binary_version,
        binary_sha256=args.binary_sha256, model=args.model,
        pty_factors={"rows": args.rows, "cols": args.cols, "term": args.term,
                     "mount_wait_s": args.mount_wait},
        inference_purchased=any((e.get("driver") or {}).get("inference_purchased")
                                for e in entries))
    spec = build_spec(entries, campaign=args.campaign, run_id=args.run_id,
                      baselines=baselines, environment=environment)
    cs.write_record(args.out, spec)
    print(f"wrote {args.out}: {len(entries)} trials")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight", help="capture the declared configuration and grade it")
    _common(p)
    p.add_argument("--baseline", help="arm baseline surface summary")
    p.add_argument("--prompt", default="ping")
    p.add_argument("--label")
    p.set_defaults(func=_cmd_preflight)

    p = sub.add_parser("trial", help="run one trial and emit its spine entry")
    _common(p)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--prompt")
    group.add_argument("--prompt-file")
    p.add_argument("--trial-id", default="trial-1")
    p.add_argument("--fixture-id")
    p.add_argument("--stratum")
    p.set_defaults(func=_cmd_trial)

    p = sub.add_parser("spec", help="trial entries -> a capture_spine ingest spec")
    p.add_argument("trials", nargs="+")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--baseline", action="append", default=[], metavar="ARM=PATH")
    p.add_argument("--campaign", default="clause-bakeoff-9-2026-08-22")
    p.add_argument("--run-id", required=True)
    p.add_argument("--binary", required=True)
    p.add_argument("--binary-version")
    p.add_argument("--binary-sha256")
    p.add_argument("--model", default="claude-opus-5")
    p.add_argument("--rows", type=int, default=PTY_ROWS)
    p.add_argument("--cols", type=int, default=PTY_COLS)
    p.add_argument("--term", default=PTY_TERM)
    p.add_argument("--mount-wait", type=float, default=MOUNT_WAIT)
    p.set_defaults(func=_cmd_spec)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
