#!/usr/bin/env python3
"""Capture spine for bakeoff 9: sanitizer, canonical hashing, per-turn records.

Built for `wayfinder/tickets/T-002-capture-spine.md`. The method note is
`sources/2026-08-24-t002-capture-spine.md`; it is the normative statement of the
schema this module implements. `MANIFEST_SCHEMA_VERSION` below is the version
string downstream tickets (T-005, T-006, T-012) pin against.

Three tiers, and the boundary between them is the whole point of this module:

  raw    transient. Full request bodies as the probe or OTEL wrote them: system
         prompt, messages, tool schemas, `metadata.user_id` (device id), and on
         the probe path the `x-api-key` header. Lives outside the repository,
         is never committed, and `--purge-raw` deletes it after ingest.
  record durable. Hashes, sizes, counts, enumerations and token numbers only.
         No message text, no tool-argument values, no reminder payload. Every
         emitted record is scanned by `retention_problems` before it is written
         and the writer refuses a record that fails.
  text   durable, opt-in, system prompt only. The `.text.json` sidecar shape
         `compare_surfaces.py` already reads. Messages, tool arguments and tool
         results never enter it.

Canonicalization -- these two rules reproduce every hash published in
`sources/2026-08-24-t001-declared-capture-configuration.md` and in the
2026-08-22 control, so records stay comparable with the existing captures:

  structural  sha256(json.dumps(value, sort_keys=True).encode("utf-8"))
              used for a message object, the tools array, one tool schema, and
              the sorted tool-name list.
  text        sha256(text.encode("utf-8"))
              used for a system block's text, the mid-turn `role: "system"`
              content, and messages[0]'s concatenated text.

Two surfaces are not byte-stable and each gets normalized companion hashes:

  `messages[0]` carries the current date (preregistration `:266`) and the user
  prompt beside the reminder, so every reminder summary carries
  `date_normalized_sha256` and, from 2026-08-26, `payload_sha256` over the
  tagged spans alone.
  The system prompt names the working directory, and its billing block carries a
  `cc_version` build suffix that tracks the prompt, so every summary carries
  `system_joined_normalized_sha256` (cwd and dates) and, from 2026-08-26,
  `system_joined_stable_sha256` (those plus the suffix). Without them a
  per-fixture working directory or a per-fixture prompt gives each trial its own
  system hash and no trial matches its arm baseline (T-016).

Byte equality stays the right check inside one run at one cwd and one prompt;
the raw hashes are retained for it.

Usage:
    python3 scripts/capture_spine.py summarize RAW.json --out SUMMARY.json
    python3 scripts/capture_spine.py admit RAW.json --baseline BASELINE.json
    python3 scripts/capture_spine.py ingest SPEC.json --out manifest.json
    python3 scripts/capture_spine.py check manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_SCHEMA_VERSION = "capture-spine/1"
RETENTION_POLICY = "capture-spine/1"
TEXT_RETENTION_POLICY = "capture-spine-text/1"
TEXT_SIDECAR_NOTE = (
    "System prompt and mid-turn system text only. messages[0] is never included."
)

WITHHELD = "<withheld>"
REDACTED_MARK = "<redacted>"

#: Longest string any durable record may carry. Hashes are 64 characters and
#: paths and model ids are far shorter, so anything past this is free text that
#: escaped the boundary.
MAX_RECORD_STRING = 512

#: Request headers that may be summarized. Everything else is dropped, which is
#: what keeps `x-api-key`, `authorization` and `x-claude-code-session-id` out.
HEADER_ALLOWLIST = ("user-agent", "anthropic-version", "anthropic-beta", "x-app")

#: Request-body keys that are dropped wholesale. `metadata.user_id` carries the
#: device id and account uuid.
BODY_DROP = ("metadata",)

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
REMINDER_TAG = re.compile(r"<system-reminder>", re.I)
REMINDER_SPAN = re.compile(r"<system-reminder>.*?</system-reminder>", re.I | re.S)

#: The billing block's `cc_version` carries a fourth component that tracks the
#: user prompt rather than the binary. Measured 2026-08-26 over five captures
#: (`sources/2026-08-26-t016-prompt-stable-surfaces.md`): at prompts of 4, 88 and
#: 219 characters the three system blocks are byte-identical and the normalized
#: system text differs in this suffix and nothing else. The pinned version
#: itself stays compared, so 2.1.239 -> 2.1.240 is still a mismatch.
CC_VERSION_BUILD = re.compile(r"(cc_version=\d+\.\d+\.\d+)\.[A-Za-z0-9]+")

#: The system prompt names the working directory, so its hash moves with every
#: fixture directory exactly as `messages[0]` moves with the date. Measured
#: 2026-08-25: two runs differing only in cwd differ in system block 2 by the
#: length of the path and nothing else.
CWD_LINE = re.compile(r"(?m)^(\s*-\s*Primary working directory:[ \t]*)(\S+)[ \t]*$")

#: Credential-shaped text. Applied to any free text before it is hashed, and
#: used to scan finished records. Deliberately excludes the long-hex rule that
#: `compare_surfaces.redact` carries for diff lines, because a sha256 is 64 hex
#: characters and every record is full of them.
CREDENTIAL_PATTERNS = (
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]+"), "<redacted:api-key>"),
    (re.compile(r"\b(?:Bearer|Basic)\s+[A-Za-z0-9._\-/+=]+", re.I), "<redacted:authorization>"),
    (re.compile(
        r"(?i)(?<!\S)(--?(?:[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*[_-](?:token|key|secret|password)|"
        r"api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|secret|password|passwd|"
        r"authorization|x-api-key|client[_-]?secret))(\s+)\S+"),
     r"\1 <redacted>"),
    (re.compile(
        r"(?i)\b([a-z][a-z0-9]*(?:[_-][a-z0-9]+)*[_-](?:token|key|secret|password))\b"
        r"(\s*[:=]\s*)\S+"),
     r"\1=<redacted>"),
    (re.compile(
        r"(?i)\b(api[_-]?key|auth[_-]?token|access[_-]?token|refresh[_-]?token|secret|password|passwd|"
        r"authorization|x-api-key|client[_-]?secret)\b(\s*[:=]\s*)\S+"),
     r"\1=<redacted>"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}\b"), "<redacted:token>"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "<redacted:aws-key-id>"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "<redacted:private-key>"),
)

#: Argument, header and environment names that are authorization-shaped. A value
#: under such a name is withheld outright: it is never sized and never hashed,
#: because a hash of a short secret is an oracle for it.
AUTH_KEY = re.compile(
    r"(?i)(?:^|[_\-.])(?:api[_-]?key|apikey|auth|authorization|token|secret|password|passwd|"
    r"credential|credentials|bearer|private[_-]?key|session[_-]?token|access[_-]?key)(?:[_\-.]|$)"
)

CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


# -- primitives ------------------------------------------------------------


def canonical(value) -> str:
    """The structural canonical form. Python default separators, ensure_ascii on."""
    return json.dumps(value, sort_keys=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_structural(value) -> str:
    return sha256_text(canonical(value))


def text_digest(text: str) -> dict:
    return {"chars": len(text), "sha256": sha256_text(text)}


def structural_digest(value) -> dict:
    form = canonical(value)
    return {"chars": len(form), "sha256": sha256_text(form)}


def normalize_dates(text: str) -> str:
    """Replace ISO dates so a date-carrying surface can be compared across days."""
    return ISO_DATE.sub("<date>", text)


def normalize_system(text: str) -> str:
    """Replace the working directory and ISO dates in a system prompt.

    Without this, a per-fixture working directory gives every trial its own
    `system_joined_sha256` and no trial matches its arm baseline.
    """
    match = CWD_LINE.search(text)
    if match:
        cwd = match.group(2)
        text = text.replace(cwd, "<cwd>")
        for alias in (cwd.removeprefix("/private"), "/private" + cwd):
            if alias and alias != cwd:
                text = text.replace(alias, "<cwd>")
    return normalize_dates(text)


def normalize_prompt_derived(text: str) -> str:
    """`normalize_system`, plus the `cc_version` build suffix that tracks the prompt.

    Without it one arm baseline cannot grade trials at different fixtures: the
    system surface moves with the user prompt while the system prompt itself is
    unchanged.
    """
    return CC_VERSION_BUILD.sub(r"\1.<build>", normalize_system(text))


# -- sanitizer -------------------------------------------------------------


def redact(text: str) -> str:
    """Strip credential-shaped and authorization-shaped substrings."""
    for pattern, replacement in CREDENTIAL_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def is_auth_shaped_key(name: str) -> bool:
    """True for `api_key`, `x-api-key` and `authToken` alike.

    Tool arguments arrive in both snake and camel case, so the camel boundary is
    split before matching. The rule fails closed: `token_count` matches too.
    """
    return bool(AUTH_KEY.search(CAMEL_BOUNDARY.sub("_", str(name))))


def sanitized_digest(value) -> dict:
    """Size and hash of a value, taken after redaction.

    The hash covers the redacted form, so two calls that differ only inside a
    credential collapse to one hash. That is the intended trade: comparability
    of the non-secret remainder, and no hash of a secret.
    """
    form = value if isinstance(value, str) else canonical(value)
    clean = redact(form)
    digest = text_digest(clean)
    digest["redacted"] = clean != form
    return digest


def summarize_arguments(arguments: dict) -> list[dict]:
    """Tool-call arguments as names plus sanitized sizes. Never values."""
    out = []
    for key in sorted(arguments or {}):
        if is_auth_shaped_key(key):
            out.append({"key": str(key)[:MAX_RECORD_STRING], "withheld": True})
            continue
        entry = {"key": str(key)[:MAX_RECORD_STRING]}
        entry.update(sanitized_digest(arguments[key]))
        out.append(entry)
    return out


def retention_problems(record, path: str = "") -> list[str]:
    """Every way a finished record can violate the retention boundary.

    Returns problem descriptions; an empty list means the record may be written.
    """
    problems: list[str] = []
    if isinstance(record, dict):
        for key, value in record.items():
            where = f"{path}/{key}"
            if is_auth_shaped_key(key) and isinstance(value, str) and value != WITHHELD:
                problems.append(f"{where}: authorization-shaped key carries a value")
            problems.extend(retention_problems(value, where))
    elif isinstance(record, list):
        for index, value in enumerate(record):
            problems.extend(retention_problems(value, f"{path}[{index}]"))
    elif isinstance(record, str):
        if len(record) > MAX_RECORD_STRING:
            problems.append(f"{path}: string of {len(record)} chars exceeds the record limit")
        if REMINDER_TAG.search(record):
            problems.append(f"{path}: carries a <system-reminder> payload")
        if redact(record) != record:
            problems.append(f"{path}: credential-shaped text")
    return problems


def text_retention_problems(sidecar) -> list[str]:
    """Shape and credential problems in a system-prompt text sidecar."""
    if not isinstance(sidecar, dict):
        return ["text sidecar must be an object"]

    problems: list[str] = []
    expected = {"system_blocks", "mid_turn_system", "note"}
    for key in sorted(expected - set(sidecar)):
        problems.append(f"text sidecar is missing key: {key}")
    for key in sorted(set(sidecar) - expected):
        problems.append(f"text sidecar has unexpected key: {key}")

    blocks = sidecar.get("system_blocks")
    if not isinstance(blocks, list) or not all(isinstance(block, str) for block in blocks):
        problems.append("text sidecar system_blocks must be a list of strings")
        blocks = []
    mid_turn = sidecar.get("mid_turn_system")
    if mid_turn is not None and not isinstance(mid_turn, str):
        problems.append("text sidecar mid_turn_system must be a string or null")
        mid_turn = None
    note = sidecar.get("note")
    if not isinstance(note, str):
        problems.append("text sidecar note must be a string")
        note = ""
    elif note != TEXT_SIDECAR_NOTE:
        problems.append("text sidecar note does not match the policy declaration")

    texts = [(f"/system_blocks[{index}]", block) for index, block in enumerate(blocks)]
    texts.extend((("/mid_turn_system", mid_turn), ("/note", note)))
    for path, text in texts:
        if text is None:
            continue
        if REMINDER_TAG.search(text):
            problems.append(f"{path}: carries a <system-reminder> payload")
        if redact(text) != text:
            problems.append(f"{path}: credential-shaped text")
    return problems


def write_record(path: Path, record: dict) -> None:
    """Write a durable record, or refuse it."""
    problems = retention_problems(record)
    if problems:
        raise ValueError("retention boundary violated:\n  " + "\n  ".join(problems))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n")


def write_text_record(path: Path, sidecar: dict) -> None:
    """Write an opt-in system-prompt sidecar under its text retention policy."""
    problems = text_retention_problems(sidecar)
    if problems:
        raise ValueError(f"{TEXT_RETENTION_POLICY} boundary violated:\n  " + "\n  ".join(problems))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sidecar, indent=2) + "\n")


# -- request surfaces ------------------------------------------------------


def request_body(raw: dict) -> dict:
    """Accept either the probe capture wrapper or a bare OTEL request body."""
    if isinstance(raw.get("body"), dict):
        return raw["body"]
    return raw


def _block_texts(content) -> list[str]:
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return []


def _reminder_count(text: str) -> int:
    return len(REMINDER_TAG.findall(text))


def _reminder_payload(text: str) -> tuple[str, str]:
    """The reminder payload alone, date-normalized, and where it came from.

    `messages[0]` carries the user prompt beside the reminder, so digesting the
    whole message makes the surface move with the fixture. Only the tagged spans
    are behavior-bearing. If the tags do not pair, nothing can be isolated: the
    whole message is digested and `whole-message` is recorded, which fails closed
    -- two trials at different prompts then compare unequal rather than silently
    equal.
    """
    spans = REMINDER_SPAN.findall(text)
    if spans and len(spans) == _reminder_count(text):
        return normalize_dates("".join(spans)), "spans"
    return normalize_dates(text), "whole-message"


def summarize_request(raw: dict, *, label: str | None = None, host: str | None = None) -> tuple[dict, dict]:
    """Sanitized request-surface summary plus the system-prompt text sidecar.

    The summary is the shape `compare_surfaces.py` already reads and the shape
    `sources/2026-08-24-t001-surface-*.json` already carry, so a spine record
    compares directly against the T-001 captures and the 2026-08-22 control.
    """
    body = request_body(raw)
    headers = {k.lower(): v for k, v in (raw.get("headers") or {}).items()}

    blocks = body.get("system") or []
    block_texts = [b.get("text", "") if isinstance(b, dict) else str(b) for b in blocks]
    system_blocks = [
        {
            "index": i,
            "chars": len(t),
            "sha256": sha256_text(t),
            "cache_control": bool(isinstance(b, dict) and b.get("cache_control")),
        }
        for i, (b, t) in enumerate(zip(blocks, block_texts))
    ]

    tools = body.get("tools") or []
    tool_names = [t.get("name", "?") for t in tools if isinstance(t, dict)]

    messages = body.get("messages") or []
    message_summaries = []
    reminder = None
    mid_turn = None
    for index, message in enumerate(messages):
        texts = _block_texts(message.get("content"))
        joined = "".join(texts)
        summary = {"role": message.get("role")}
        summary.update(structural_digest(message))
        summary["system_reminder_count"] = _reminder_count(joined)
        message_summaries.append(summary)
        if reminder is None and summary["system_reminder_count"]:
            payload, payload_source = _reminder_payload(joined)
            reminder = {
                "message_index": index,
                "role": message.get("role"),
                "present": True,
                "count": summary["system_reminder_count"],
                "chars": len(joined),
                "sha256": sha256_text(joined),
                "date_normalized_sha256": sha256_text(normalize_dates(joined)),
                "payload_chars": len(payload),
                "payload_sha256": sha256_text(payload),
                "payload_source": payload_source,
            }
        if mid_turn is None and message.get("role") == "system":
            mid_turn = text_digest(joined)
    if reminder is None:
        reminder = {"present": False, "count": 0}

    entrypoint = None
    billing = block_texts[0] if block_texts else ""
    match = re.search(r"cc_entrypoint=([A-Za-z0-9_\-]+)", billing)
    if match:
        entrypoint = match.group(1)

    summary = {
        "label": label,
        "host": host,
        "cc_version_block": billing[:MAX_RECORD_STRING] if billing.startswith("x-anthropic-billing-header:") else None,
        "entrypoint": entrypoint,
        "system_blocks": system_blocks,
        "system_joined_sha256": sha256_text("".join(block_texts)),
        "system_joined_normalized_sha256": sha256_text(normalize_system("".join(block_texts))),
        "system_joined_stable_sha256": sha256_text(normalize_prompt_derived("".join(block_texts))),
        "tools": tool_names,
        "tools_sha256": sha256_structural(tools),
        "tools_names_sha256": sha256_structural(sorted(tool_names)),
        "tool_schemas": {
            t.get("name", "?"): structural_digest(t) for t in tools if isinstance(t, dict)
        },
        "messages": message_summaries,
        "system_reminder": reminder,
        "mid_turn_system": mid_turn,
        "model": body.get("model"),
        "max_tokens": body.get("max_tokens"),
        "thinking": body.get("thinking"),
        "output_config": body.get("output_config"),
        "output_format": body.get("output_format") or (body.get("output_config") or {}).get("format"),
        "context_management": body.get("context_management"),
        "betas": body.get("betas") or _split_betas(headers.get("anthropic-beta")),
        "headers": {k: str(v)[:MAX_RECORD_STRING] for k, v in headers.items() if k in HEADER_ALLOWLIST},
        "dropped_body_keys": [k for k in BODY_DROP if k in body],
        "retention": {
            "policy": RETENTION_POLICY,
            "note": "message text, tool-argument values and the messages[0] reminder payload "
                    "are not retained; presence, tag count, size and hash only",
        },
    }
    sidecar = {
        "system_blocks": block_texts,
        "mid_turn_system": "".join(_block_texts((messages[1] if len(messages) > 1 else {}).get("content")))
        if any(m.get("role") == "system" for m in messages) else None,
        "note": TEXT_SIDECAR_NOTE,
    }
    return summary, sidecar


def _split_betas(header: str | None) -> list[str] | None:
    if not header:
        return None
    return [item.strip() for item in header.split(",") if item.strip()]


SURFACE_KEYS = ("system_joined_stable_sha256", "tools_sha256")

#: Fields a manifest baseline must carry. A summary written before 2026-08-26 has
#: none of them, and grading a campaign against it would mismatch every trial
#: after the fixture the baseline was captured at.
BASELINE_REQUIRED = ("system_joined_stable_sha256",)


def _best_digest(summary: dict, baseline: dict, stable: tuple[str, ...], legacy: str):
    """The strongest digest both sides carry, as a comparable pair.

    A summary written before 2026-08-26 has only the legacy field. Falling back
    to it can over-report a difference -- that is the T-016 bug, and it is what
    `load_baselines` refuses -- but it can never report a changed surface as
    matching, so the fixed-prompt preflight keeps working against the archived
    baselines it was captured with.
    """
    a = tuple(summary.get(k) for k in stable)
    b = tuple(baseline.get(k) for k in stable)
    if None in a or None in b:
        return summary.get(legacy), baseline.get(legacy)
    return a, b


def surface_key(summary: dict) -> str:
    """Identity of the behavior-bearing prompt surface, stable across trials.

    Built from the digests that do not move with the date, the working directory
    or the user prompt, so one arm baseline covers every trial at every fixture.
    Byte equality remains the right check inside a single run at a single cwd and
    prompt, and `system_joined_sha256` is retained for it.
    """
    reminder = summary.get("system_reminder") or {}
    parts = [str(summary.get(k)) for k in SURFACE_KEYS]
    parts.append(str((summary.get("mid_turn_system") or {}).get("sha256")))
    parts.append(str(reminder.get("payload_sha256")))
    parts.append(str(reminder.get("payload_source")))
    return sha256_text("|".join(parts))


def surface_diff(summary: dict, baseline: dict) -> list[str]:
    """Which of the four behavior-bearing surfaces differ from a baseline.

    The reminder is compared by presence, tag count and payload -- the payload
    because that is where a leaked instruction would appear -- but not by the
    user prompt sitting beside it in the same message.
    """
    differing = []
    a, b = _best_digest(summary, baseline, ("system_joined_stable_sha256",),
                        "system_joined_normalized_sha256")
    if a != b:
        differing.append("system")
    if summary.get("tools_sha256") != baseline.get("tools_sha256"):
        differing.append("tools")
    a = (summary.get("mid_turn_system") or {}).get("sha256")
    b = (baseline.get("mid_turn_system") or {}).get("sha256")
    if a != b:
        differing.append("mid_turn_system")
    ra = summary.get("system_reminder") or {}
    rb = baseline.get("system_reminder") or {}
    if ra.get("present") != rb.get("present") or ra.get("count") != rb.get("count"):
        differing.append("system_reminder")
    elif ra.get("present"):
        pa, pb = _best_digest(ra, rb, ("payload_sha256", "payload_source"),
                              "date_normalized_sha256")
        if pa != pb:
            differing.append("system_reminder")
    return differing


def prompt_stable_baseline(
    baseline: dict, reference: dict, *, allowed_reference_differences: tuple[str, ...] = ()
) -> dict:
    """Add prompt-stable companions after a reference matches frozen legacy fields.

    Historical baselines predate T-016's stable digests. A zero-cost capture at
    their original prompt must match first, apart from explicitly named surfaces
    such as the arm-specific reminder; only then may its additive stable
    companions stand beside the unchanged frozen record.
    """
    differing = surface_diff(reference, baseline)
    unexpected = sorted(set(differing) - set(allowed_reference_differences))
    if unexpected:
        raise ValueError(
            "reference does not match frozen baseline: " + ", ".join(unexpected)
        )
    enriched = json.loads(json.dumps(baseline))
    enriched["system_joined_stable_sha256"] = reference.get(
        "system_joined_stable_sha256"
    )
    source_reminder = reference.get("system_reminder") or {}
    target_reminder = enriched.setdefault("system_reminder", {})
    for key in ("payload_chars", "payload_sha256", "payload_source"):
        target_reminder[key] = source_reminder.get(key)
    return enriched


# -- per-turn spine --------------------------------------------------------


def _usage(usage: dict) -> dict:
    details = usage.get("output_tokens_details") or {}
    creation = usage.get("cache_creation") or {}
    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "thinking_tokens": details.get("thinking_tokens"),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
        "cache_creation_5m_input_tokens": creation.get("ephemeral_5m_input_tokens"),
        "cache_creation_1h_input_tokens": creation.get("ephemeral_1h_input_tokens"),
        "service_tier": usage.get("service_tier"),
    }


def _content(blocks) -> dict:
    text_blocks = thinking_blocks = 0
    text_chars = thinking_chars = 0
    tool_uses = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            text_blocks += 1
            text_chars += len(block.get("text") or "")
        elif kind == "thinking":
            thinking_blocks += 1
            thinking_chars += len(block.get("thinking") or "")
        elif kind == "tool_use":
            tool_uses.append({
                "name": str(block.get("name"))[:MAX_RECORD_STRING],
                "id": str(block.get("id"))[:MAX_RECORD_STRING],
                "arguments": summarize_arguments(block.get("input") or {}),
            })
    return {
        "text_blocks": text_blocks,
        "text_chars": text_chars,
        "thinking_blocks": thinking_blocks,
        "thinking_chars": thinking_chars,
        "tool_uses": tool_uses,
    }


def turn_record(row: dict, turn_index: int) -> dict:
    """One assistant turn from a session JSONL row, sanitized.

    `sessionId` is replaced by a hash: the 2026-08-22 capture precedent omits
    session and device identifiers, and a hash still groups turns by session.
    """
    message = row.get("message") or {}
    session = row.get("sessionId")
    return {
        "turn_index": turn_index,
        "uuid": row.get("uuid"),
        "parent_uuid": row.get("parentUuid"),
        "request_id": row.get("requestId"),
        "message_id": message.get("id"),
        "timestamp": row.get("timestamp"),
        "version": row.get("version"),
        "entrypoint": row.get("entrypoint"),
        "effort": row.get("effort"),
        "model": message.get("model"),
        "cwd": row.get("cwd"),
        "git_branch": row.get("gitBranch"),
        "is_sidechain": row.get("isSidechain"),
        "session_sha256": sha256_text(session) if isinstance(session, str) else None,
        "stop_reason": message.get("stop_reason"),
        "stop_sequence": message.get("stop_sequence"),
        "api_error": bool(row.get("isApiErrorMessage")),
        "usage": _usage(message.get("usage") or {}),
        "content": _content(message.get("content")),
    }


def turn_records(lines) -> list[dict]:
    """Assistant turns, in file order, from session JSONL lines."""
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("type") != "assistant":
            continue
        if not isinstance(row.get("message"), dict):
            continue
        records.append(turn_record(row, len(records)))
    return records


def sdk_capture_record(messages) -> dict:
    """Reduce in-memory Agent SDK init/assistant messages to the turn schema.

    The SDK wire messages are transient. Text and argument values are reduced
    through the same ``_content``/``_usage`` boundary as session JSONL before
    this record can become durable.
    """
    init = None
    turns = []
    for row in messages:
        if not isinstance(row, dict):
            continue
        if row.get("type") == "system" and row.get("subtype") == "init":
            if init is not None:
                raise ValueError("SDK stream contains more than one system init")
            init = row
            continue
        if row.get("type") != "assistant" or not isinstance(row.get("message"), dict):
            continue
        if init is None:
            raise ValueError("SDK assistant message arrived before system init")
        message = row["message"]
        session = row.get("session_id")
        turns.append({
            "turn_index": len(turns),
            "uuid": row.get("uuid"),
            "parent_uuid": None,
            "request_id": row.get("request_id"),
            "message_id": message.get("id"),
            "timestamp": row.get("timestamp"),
            "version": init.get("claude_code_version"),
            "entrypoint": init.get("entrypoint"),
            "effort": row.get("effort"),
            "model": message.get("model") or init.get("model"),
            "cwd": init.get("cwd"),
            "git_branch": None,
            "is_sidechain": bool(row.get("parent_tool_use_id")),
            "session_sha256": sha256_text(session) if isinstance(session, str) else None,
            "stop_reason": message.get("stop_reason"),
            "stop_sequence": message.get("stop_sequence"),
            "api_error": bool(row.get("error")),
            "usage": _usage(message.get("usage") or {}),
            "content": _content(message.get("content")),
        })
    if init is None:
        raise ValueError("SDK stream has no system init")
    record = {
        "source": "sdk-stream",
        "init": {
            "cli_version": init.get("claude_code_version"),
            "cwd": init.get("cwd"),
            "model": init.get("model"),
            "account_source": init.get("apiKeySource"),
            "permission_mode": init.get("permissionMode"),
            "tools": [str(name)[:MAX_RECORD_STRING] for name in init.get("tools") or []],
        },
        "turns": turns,
        "usage_totals": usage_totals(turns),
        "cli_versions": cli_version_report([{"trial_id": "sdk-trial", "turns": turns}]),
    }
    problems = retention_problems(record)
    if problems:
        raise ValueError("SDK capture retention boundary violated:\n  " + "\n  ".join(problems))
    return record


def usage_totals(turns: list[dict]) -> dict:
    """Totals over model turns. Transport-error rows are counted, never summed.

    A loopback 401 leaves an `isApiErrorMessage` row in the session file with
    `model: "<synthetic>"`, no `requestId`, no `effort` and no thinking tokens.
    Observed on all seven local 2.1.239 assistant rows, every one of which is
    such a row. Summing them would understate nothing and misreport turn count.
    """
    fields = ("input_tokens", "output_tokens", "thinking_tokens",
              "cache_creation_input_tokens", "cache_read_input_tokens")
    totals = {field: 0 for field in fields}
    model_turns = [t for t in turns if not t.get("api_error")]
    for turn in model_turns:
        for field in fields:
            value = turn["usage"].get(field)
            if isinstance(value, int):
                totals[field] += value
    totals["turns"] = len(model_turns)
    totals["api_error_turns"] = len(turns) - len(model_turns)
    return totals


# -- raw directory ---------------------------------------------------------


def raw_body_paths(raw_dir: Path) -> list[Path]:
    """Request bodies OTEL wrote, plus probe captures, in stable order."""
    if not raw_dir.is_dir():
        return []
    return sorted(p for p in raw_dir.iterdir()
                  if p.is_file() and p.suffix == ".json" and not p.name.endswith(".response.json"))


def raw_body_records(raw_dir: Path) -> list[dict]:
    """Parse transient request files, skipping unreadable/non-object entries."""
    records = []
    for path in raw_body_paths(raw_dir):
        try:
            raw = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(raw, dict):
            records.append(raw)
    return records


def is_auxiliary_request(raw: dict) -> bool:
    """Whether this is the title/helper request beside a trial turn.

    This is the measured CLI rule: the declared trial always has tools and a
    reminder; the title request has neither. Thinking/output format describe
    the auxiliary surface but do not decide classification.
    """
    body = request_body(raw)
    if body.get("tools"):
        return False
    for message in body.get("messages") or []:
        for text in _block_texts(message.get("content")):
            if REMINDER_TAG.search(text or ""):
                return False
    return True


def partition_request_records(raw_records) -> tuple[list[dict], list[dict]]:
    """Return primary and auxiliary transient requests without deleting either."""
    primary, auxiliary = [], []
    for raw in raw_records:
        if not isinstance(raw, dict):
            continue
        (auxiliary if is_auxiliary_request(raw) else primary).append(raw)
    return primary, auxiliary


def observed_surface_records(raw_records, baseline: dict | None) -> list[dict]:
    """Distinct request surfaces a trial actually sent, with occurrence counts.

    Per-turn correlation by `request_id` is not available from a raw-body file
    alone -- OTEL names them by a body uuid and the request id arrives on the
    response side. Grouping every body in a per-trial raw directory answers the
    question the ticket asks (did this trial carry its assigned prompt) without
    that correlation, and makes mid-trial drift visible as a second group.
    """
    grouped: dict[str, dict] = {}
    for raw in raw_records:
        if not isinstance(raw, dict):
            continue
        summary, _ = summarize_request(raw)
        key = surface_key(summary)
        entry = grouped.get(key)
        if entry is None:
            entry = {
                "surface_key": key,
                "count": 0,
                "system_joined_sha256": summary["system_joined_sha256"],
                "system_joined_normalized_sha256": summary["system_joined_normalized_sha256"],
                "system_joined_stable_sha256": summary["system_joined_stable_sha256"],
                "tools_sha256": summary["tools_sha256"],
                "mid_turn_system": summary["mid_turn_system"],
                "system_reminder": summary["system_reminder"],
                "system_chars": sum(b["chars"] for b in summary["system_blocks"]),
                "tools": summary["tools"],
                "model": summary["model"],
                "entrypoint": summary["entrypoint"],
                "thinking": summary["thinking"],
                "output_config": summary["output_config"],
                "output_format": summary["output_format"],
            }
            if baseline is not None:
                differing = surface_diff(summary, baseline)
                entry["matches_baseline"] = not differing
                entry["differing_surfaces"] = differing
            grouped[key] = entry
        entry["count"] += 1
    return sorted(grouped.values(), key=lambda e: -e["count"])


def observed_surfaces(raw_dir: Path, baseline: dict | None) -> list[dict]:
    """Distinct request surfaces a trial actually sent, with occurrence counts."""
    return observed_surface_records(raw_body_records(raw_dir), baseline)


def purge_raw(raw_dir: Path) -> bool:
    """Delete a transient raw directory. Refuses anything inside the repository."""
    raw_dir = raw_dir.resolve()
    repo = Path(__file__).resolve().parent.parent
    if raw_dir == repo or repo in raw_dir.parents:
        raise ValueError(f"raw directory is inside the repository, refusing to treat it as transient: {raw_dir}")
    if not raw_dir.is_dir():
        return False
    shutil.rmtree(raw_dir)
    return True


# -- manifest --------------------------------------------------------------


def load_baselines(spec: dict, base: Path) -> dict:
    baselines = {}
    for arm, path in (spec.get("baselines") or {}).items():
        summary = json.loads((base / path).read_text())
        missing = [k for k in BASELINE_REQUIRED if summary.get(k) is None]
        if missing:
            raise ValueError(
                f"baseline for arm {arm!r} ({path}) is missing {', '.join(missing)}; "
                "it predates the prompt-stable digests and would grade every trial at a "
                "second fixture as a mismatch. Re-capture it with this module.")
        baselines[arm] = summary
    return baselines


def cli_version_report(trials: list[dict]) -> dict:
    """Which CLI versions the run actually used, as an observation per run.

    The version is recorded per turn rather than asserted as a campaign
    constant: the operator updates Claude Code through this harness's lifetime,
    so a run can legitimately span two versions. A change is reported, not
    rejected -- pooling across versions inside one campaign is allowed, and the
    report exists so the write-up can say so explicitly instead of the drift
    passing unnoticed.
    """
    seen: dict[str, list[str]] = {}
    for trial in trials:
        for turn in trial.get("turns") or []:
            version = turn.get("version")
            if not version:
                continue
            seen.setdefault(version, [])
            trial_id = trial.get("trial_id")
            if trial_id and trial_id not in seen[version]:
                seen[version].append(trial_id)
    versions = sorted(seen)
    return {
        "observed": versions,
        "changed_mid_run": len(versions) > 1,
        "trials_by_version": {v: sorted(seen[v]) for v in versions},
        "note": (
            "Version is a per-run observation, not a campaign constant. More "
            "than one value means the CLI was updated mid-run; record it in the "
            "report. Pooling across versions within one campaign is permitted "
            "(bakeoff 9 decision, 2026-08-25)."
            if len(versions) > 1 else
            "Single version across the run."
        ),
    }


def build_manifest(spec: dict, base: Path, *, purge: bool = False) -> dict:
    """Assemble a run manifest from a trial spec. See the module docstring."""
    baselines = load_baselines(spec, base)
    trials = []
    purged = []
    for entry in spec.get("trials") or []:
        arm = entry.get("arm")
        baseline = baselines.get(arm)
        turns: list[dict] = []
        session = entry.get("session")
        if session:
            session_path = base / session
            if session_path.is_file():
                turns = turn_records(session_path.read_text().splitlines())
        raw_dir = entry.get("raw_dir")
        surfaces = []
        if raw_dir:
            surfaces = observed_surfaces(base / raw_dir, baseline)
        if surfaces:
            if baseline is None:
                verdict = "unchecked"
            elif all(s.get("matches_baseline") for s in surfaces):
                verdict = "match"
            else:
                verdict = "mismatch"
        else:
            verdict = "unrecorded"
        trials.append({
            "trial_id": entry.get("trial_id"),
            "arm": arm,
            "fixture_id": entry.get("fixture_id"),
            "stratum": entry.get("stratum"),
            "cwd": entry.get("cwd"),
            "surface_verdict": verdict,
            "distinct_surfaces": len(surfaces),
            "request_surfaces": surfaces,
            "usage_totals": usage_totals(turns),
            "turns": turns,
        })
        if purge and raw_dir:
            if purge_raw(base / raw_dir):
                purged.append(raw_dir)

    manifest = {
        "schema": MANIFEST_SCHEMA_VERSION,
        "cli_versions": cli_version_report(trials),
        "created_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "campaign": spec.get("campaign"),
        "run_id": spec.get("run_id"),
        "canonicalization": {
            "structural": "sha256(json.dumps(value, sort_keys=True).encode('utf-8'))",
            "text": "sha256(text.encode('utf-8'))",
            "date_normalized": "ISO dates replaced with <date> before hashing",
            "system_normalized": "the Primary working directory value replaced with <cwd>, then dates normalized",
        },
        "retention": {
            "policy": RETENTION_POLICY,
            "raw_bodies_retained": False,
            "raw_dirs_purged": purged,
            "withheld": [
                "credentials and request headers other than " + ", ".join(HEADER_ALLOWLIST),
                "metadata.user_id (device id, account uuid)",
                "messages[0] reminder payload (presence, tag count, size, hash only)",
                "message text and tool-argument values",
                "sessionId (recorded as session_sha256)",
            ],
        },
        "environment": spec.get("environment") or {},
        "baselines": {
            arm: {
                "source": (spec.get("baselines") or {})[arm],
                "surface_key": surface_key(summary),
                "system_joined_sha256": summary.get("system_joined_sha256"),
                "system_joined_normalized_sha256": summary.get("system_joined_normalized_sha256"),
                "tools_sha256": summary.get("tools_sha256"),
                "system_reminder": summary.get("system_reminder"),
                "mid_turn_system": summary.get("mid_turn_system"),
            }
            for arm, summary in baselines.items()
        },
        "trials": trials,
        "totals": {
            "trials": len(trials),
            "turns": sum(len(t["turns"]) for t in trials),
            "surface_match": sum(1 for t in trials if t["surface_verdict"] == "match"),
            "surface_mismatch": sum(1 for t in trials if t["surface_verdict"] == "mismatch"),
            "surface_unrecorded": sum(1 for t in trials if t["surface_verdict"] == "unrecorded"),
        },
    }
    return manifest


def validate_manifest(manifest: dict) -> list[str]:
    """Schema and retention problems in a manifest. Empty means it is usable."""
    problems = []
    if manifest.get("schema") != MANIFEST_SCHEMA_VERSION:
        problems.append(f"schema is {manifest.get('schema')!r}, expected {MANIFEST_SCHEMA_VERSION!r}")
    for key in ("created_utc", "canonicalization", "retention", "environment", "trials", "totals"):
        if key not in manifest:
            problems.append(f"missing top-level key: {key}")
    if (manifest.get("retention") or {}).get("raw_bodies_retained") is not False:
        problems.append("retention.raw_bodies_retained must be false")
    for trial in manifest.get("trials") or []:
        where = trial.get("trial_id") or "<unnamed trial>"
        for key in ("arm", "surface_verdict", "request_surfaces", "usage_totals", "turns"):
            if key not in trial:
                problems.append(f"{where}: missing key {key}")
        if trial.get("surface_verdict") == "mismatch":
            problems.append(f"{where}: request surface does not match its arm baseline")
        if trial.get("surface_verdict") == "unrecorded":
            problems.append(f"{where}: request surface was not recorded")
        if not (trial.get("turns") or []):
            problems.append(f"{where}: has no turns")
        for turn in trial.get("turns") or []:
            for key in ("version", "effort", "model", "request_id", "cwd", "stop_reason", "usage"):
                if key not in turn:
                    problems.append(f"{where} turn {turn.get('turn_index')}: missing key {key}")
    problems.extend(retention_problems(manifest))
    return problems


# -- command line ----------------------------------------------------------


def _cmd_summarize(args) -> int:
    raw = json.loads(args.raw.read_text())
    summary, sidecar = summarize_request(raw, label=args.label, host=args.host)
    if args.out:
        if args.text_out:
            summary["system_text_ref"] = args.text_out.name
            write_text_record(args.text_out, sidecar)
        write_record(args.out, summary)
        print(f"wrote {args.out}")
    else:
        print(json.dumps(summary, indent=2))
    return 0


def _cmd_admit(args) -> int:
    """The record half of the admission gate. The probe still refuses the request."""
    raw = json.loads(args.raw.read_text())
    summary, _ = summarize_request(raw, label=args.label)
    baseline = json.loads(args.baseline.read_text())
    differing = surface_diff(summary, baseline)
    verdict = {
        "surface_key": surface_key(summary),
        "baseline": str(args.baseline),
        "admitted": not differing,
        "differing_surfaces": differing,
    }
    print(json.dumps(verdict, indent=2))
    return 0 if not differing else 1


def _cmd_ingest(args) -> int:
    spec = json.loads(args.spec.read_text())
    base = args.base or args.spec.parent
    manifest = build_manifest(spec, base, purge=args.purge_raw)
    problems = validate_manifest(manifest)
    if problems and not args.allow_problems:
        print("manifest rejected:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    manifest["problems"] = problems
    write_record(args.out, manifest)
    print(f"wrote {args.out}: {manifest['totals']}")
    return 0


def _cmd_check(args) -> int:
    manifest = json.loads(args.manifest.read_text())
    problems = validate_manifest(manifest)
    if problems:
        print("problems:\n  " + "\n  ".join(problems))
        return 1
    print(f"{args.manifest}: {MANIFEST_SCHEMA_VERSION} ok, {manifest['totals']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("summarize", help="raw request body -> sanitized surface summary")
    p.add_argument("raw", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--text-out", type=Path, help="also write the system-prompt text sidecar")
    p.add_argument("--label")
    p.add_argument("--host")
    p.set_defaults(func=_cmd_summarize)

    p = sub.add_parser("admit", help="compare a captured request against an arm baseline")
    p.add_argument("raw", type=Path)
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--label")
    p.set_defaults(func=_cmd_admit)

    p = sub.add_parser("ingest", help="trial spec -> run manifest")
    p.add_argument("spec", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--base", type=Path, help="root for relative paths in the spec")
    p.add_argument("--purge-raw", action="store_true", help="delete each trial's raw directory after ingest")
    p.add_argument("--allow-problems", action="store_true", help="write the manifest even when it validates dirty")
    p.set_defaults(func=_cmd_ingest)

    p = sub.add_parser("check", help="validate a manifest against the schema and the retention boundary")
    p.add_argument("manifest", type=Path)
    p.set_defaults(func=_cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
