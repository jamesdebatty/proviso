#!/usr/bin/env python3
"""Checksum-verified acquisition of a pinned Claude Code binary, plus the
manifest fields that let a reader rebuild this campaign's environment.

Built for `wayfinder/tickets/T-005-environment-acquisition.md`. The method note
is `sources/2026-08-25-t005-environment-acquisition.md`.

**This is an additive extension of `capture-spine/1`, not a second manifest
shape.** `MANIFEST_SCHEMA_VERSION` in `scripts/capture_spine.py` is unchanged
and this module never writes it. `capture-spine/1` already declares
`environment` a free-form pin block, and T-002's method note marks it "T-005
extends this". Everything here lives under three new keys inside that block --
`acquisition`, `model_roles`, `system_prompt_flags` -- alongside a
`pin_extension` marker. A `capture-spine/1` reader that does not know about
them still validates the manifest; `environment_problems()` is the extra check.

Mechanism, ported from `inspect_swe`'s `_claude_code/agentbinary.py:16-24` and
confirmed against Anthropic's own install script (fetched 2026-08-25 from
`https://claude.ai/install.sh`, which redirects to
`https://downloads.claude.ai/claude-code-releases/bootstrap.sh`):

  1. resolve `DOWNLOAD_BASE_URL` out of the install script rather than
     hardcoding it, so a base-URL rotation is visible instead of silent;
  2. GET `<base>/<version>/manifest.json` -- Anthropic's release manifest,
     `platforms[<platform>] = {checksum, size}`, checksum being lowercase hex
     sha256 of the uncompressed binary;
  3. GET `<base>/<version>/<platform>/claude`;
  4. verify sha256 against the release manifest, and refuse anything else.

Deliberately *not* ported: `inspect_swe`'s runner. `claude_code()` adds
`--print --output-format stream-json --verbose` by default
(`_claude_code/claude_code.py:326`), which the preregistration forbids, and its
bridge redirects `ANTHROPIC_BASE_URL` to Inspect's model routing, which moves
billing off the subscription. Only the acquisition helpers cross over.

Network use is read-only GETs of a plain-text version string, a small JSON
release manifest, and the binary itself. Nothing here authenticates, and
nothing here can buy inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform as _platform
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# -- constants -------------------------------------------------------------

#: Marker for the additive extension. The manifest's own `schema` stays
#: `capture-spine/1`; this only says which optional keys are present.
PIN_EXTENSION = "t005-environment-pin/1"

#: Anthropic's published entry point. Redirects; the base URL is read out of
#: the body, never assumed from the redirect target.
INSTALL_SCRIPT_URL = "https://claude.ai/install.sh"

#: Fallback only, and recorded as such when used. The install script is the
#: authority.
FALLBACK_DOWNLOAD_BASE_URL = "https://downloads.claude.ai/claude-code-releases"

DOWNLOAD_BASE_RE = re.compile(r'(?m)^\s*DOWNLOAD_BASE_URL\s*=\s*"([^"]+)"')

CHECKSUM_ALGORITHM = "sha256"
SHA256_HEX = re.compile(r"^[a-f0-9]{64}$")

#: The platform strings Anthropic's release manifest keys on.
PLATFORMS = (
    "darwin-arm64", "darwin-x64",
    "linux-arm64", "linux-arm64-musl",
    "linux-x64", "linux-x64-musl",
    "win32-arm64", "win32-x64",
)

#: Model-role variables the CLI reads from its own environment -- no Inspect
#: bridge involved. The first five are the ones T-005 names; the sixth is
#: present in the pinned binary and is accepted so a reader can pin it.
MODEL_ROLE_VARS = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
    "CLAUDE_CODE_SUBAGENT_MODEL",
)

#: The H-harness ablation's manipulation, as plain CLI flags. Pinned as a
#: mapping so that a later edit to the ablation cannot silently swap replace
#: for append: `environment_problems()` rejects any other value.
SYSTEM_PROMPT_FLAGS = {
    "replace": "--system-prompt",
    "append": "--append-system-prompt",
}

#: Chunk size for streaming hashes. The binary is ~325 MB; never read it whole.
CHUNK = 1 << 20


class AcquisitionError(RuntimeError):
    """Acquisition refused. The message says which check failed."""


# -- the ported mechanism --------------------------------------------------


def _http_get(url: str, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "bakeoff9-environment-pin"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - https only, read-only
        return resp.read()


def _http_download(url: str, destination: Path, timeout: float = 60.0) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "bakeoff9-environment-pin"})
    with urllib.request.urlopen(req, timeout=timeout) as response, open(destination, "wb") as output:  # noqa: S310 - https only, read-only
        for chunk in iter(lambda: response.read(CHUNK), b""):
            output.write(chunk)


def _download_from_fetch(fetch, url: str, destination: Path) -> None:
    """Stream a response-like test fetcher, while retaining the old bytes stub API."""
    response = fetch(url)
    with open(destination, "wb") as output:
        if isinstance(response, bytes):
            for offset in range(0, len(response), CHUNK):
                output.write(response[offset:offset + CHUNK])
            return
        for chunk in iter(lambda: response.read(CHUNK), b""):
            output.write(chunk)


def resolve_download_base(script_text: str) -> str:
    """The download base URL as Anthropic's install script defines it."""
    match = DOWNLOAD_BASE_RE.search(script_text)
    if not match:
        raise AcquisitionError(
            "install script defines no DOWNLOAD_BASE_URL; refusing to guess one"
        )
    return match.group(1).rstrip("/")


def detect_platform(system: str | None = None, machine: str | None = None) -> str:
    """This machine's release-manifest platform key.

    Mirrors the install script's own case analysis. Rosetta is *not* detected:
    an x64 shell on an ARM Mac resolves to `darwin-x64`, which runs but is not
    the build the pin names, so pass `--platform` explicitly there.
    """
    system = (system or _platform.system()).lower()
    machine = (machine or _platform.machine()).lower()
    arch = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if arch is None:
        raise AcquisitionError(f"unsupported architecture: {machine}")
    if system == "darwin":
        return f"darwin-{arch}"
    if system == "linux":
        musl = Path("/lib/libc.musl-x86_64.so.1").exists() or Path("/lib/libc.musl-aarch64.so.1").exists()
        return f"linux-{arch}-musl" if musl else f"linux-{arch}"
    raise AcquisitionError(f"unsupported operating system: {system}")


def release_manifest_url(base: str, version: str) -> str:
    return f"{base.rstrip('/')}/{version}/manifest.json"


def binary_url(base: str, version: str, platform_key: str) -> str:
    return f"{base.rstrip('/')}/{version}/{platform_key}/claude"


def platform_entry(release_manifest: dict, platform_key: str) -> dict:
    """`{checksum, size}` for one platform, or a refusal."""
    entry = (release_manifest.get("platforms") or {}).get(platform_key)
    if not entry:
        raise AcquisitionError(
            f"platform {platform_key!r} is absent from the release manifest "
            f"(has {sorted((release_manifest.get('platforms') or {}))})"
        )
    checksum = str(entry.get("checksum") or "").lower()
    if not SHA256_HEX.match(checksum):
        raise AcquisitionError(f"release manifest checksum for {platform_key!r} is not a sha256 hex digest")
    return {"checksum": checksum, "size": entry.get("size")}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: Path, expected_sha256: str) -> str:
    """Raise unless `path` hashes to `expected_sha256`. Returns the digest."""
    expected = str(expected_sha256 or "").lower()
    if not SHA256_HEX.match(expected):
        raise AcquisitionError(f"expected checksum {expected_sha256!r} is not a sha256 hex digest")
    actual = sha256_file(path)
    if actual != expected:
        raise AcquisitionError(
            f"checksum verification failed for {path}: expected {expected}, got {actual}"
        )
    return actual


def acquire(
    version: str,
    dest: Path,
    *,
    expected_sha256: str,
    platform_key: str | None = None,
    base_url: str | None = None,
    fetch=None,
    download=None,
) -> dict:
    """Download the pinned binary and install it at `dest` only if it verifies.

    `expected_sha256` is required and comes from the campaign manifest, not
    from the network: a downloader that trusts a checksum served beside the
    artifact verifies transport, not provenance. When the release manifest is
    reachable its checksum is cross-checked against it, and a disagreement is
    a refusal rather than a preference.

    On any failure the partial download is deleted and `dest` is left alone.
    """
    default_fetch = fetch is None
    fetch = fetch or _http_get
    platform_key = platform_key or detect_platform()
    if platform_key not in PLATFORMS:
        raise AcquisitionError(f"unknown platform key: {platform_key!r}")
    if not SHA256_HEX.match(str(expected_sha256 or "").lower()):
        raise AcquisitionError(f"expected checksum {expected_sha256!r} is not a sha256 hex digest")
    expected = expected_sha256.lower()

    base = base_url or resolve_download_base(fetch(INSTALL_SCRIPT_URL).decode("utf-8", "replace"))
    published = None
    try:
        release = json.loads(fetch(release_manifest_url(base, version)).decode("utf-8", "replace"))
        published = platform_entry(release, platform_key)["checksum"]
    except AcquisitionError:
        raise
    except Exception:
        published = None  # the historical build's manifest may be gone; the pin still governs
    if published is not None and published != expected:
        raise AcquisitionError(
            f"release manifest publishes {published} for {version}/{platform_key}, "
            f"but the campaign manifest pins {expected}; refusing to install either"
        )

    url = binary_url(base, version, platform_key)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".partial")
    try:
        if download is not None:
            download(url, partial)
        elif default_fetch:
            _http_download(url, partial)
        else:
            _download_from_fetch(fetch, url, partial)
        verify_file(partial, expected)
        partial.replace(dest)
        dest.chmod(0o755)
    finally:
        if partial.exists():
            partial.unlink()

    return {
        "version": version,
        "platform": platform_key,
        "url": url,
        "checksum": expected,
        "checksum_confirmed_by_release_manifest": published is not None,
        "path": str(dest),
    }


# -- the manifest fields ---------------------------------------------------


def build_acquisition(
    *,
    version: str,
    platform_key: str,
    binary_sha256: str,
    base_url: str,
    size_bytes: int | None = None,
    base_url_source: str = INSTALL_SCRIPT_URL,
    confirmed_utc: str | None = None,
) -> dict:
    """The `environment.acquisition` block."""
    return {
        "method": "checksum-verified download, ported from inspect_swe _claude_code/agentbinary.py:16-24",
        "install_script_url": base_url_source,
        "download_base_url": base_url,
        "release_manifest_url": release_manifest_url(base_url, version),
        "binary_url": binary_url(base_url, version, platform_key),
        "platform": platform_key,
        "checksum_algorithm": CHECKSUM_ALGORITHM,
        "checksum": binary_sha256.lower(),
        "size_bytes": size_bytes,
        "release_manifest_confirmed_utc": confirmed_utc,
        "tool": "python3 scripts/environment_pin.py acquire",
    }


def build_environment_pin(
    *,
    version: str,
    platform_key: str,
    binary_sha256: str,
    base_url: str,
    model_roles: dict,
    size_bytes: int | None = None,
    confirmed_utc: str | None = None,
) -> dict:
    """The three additive keys, plus the extension marker.

    Merge into an existing `capture-spine/1` manifest's `environment` block;
    nothing here replaces a key that block already defines.
    """
    return {
        "pin_extension": PIN_EXTENSION,
        "acquisition": build_acquisition(
            version=version,
            platform_key=platform_key,
            binary_sha256=binary_sha256,
            base_url=base_url,
            size_bytes=size_bytes,
            confirmed_utc=confirmed_utc,
        ),
        "model_roles": dict(model_roles),
        "system_prompt_flags": dict(SYSTEM_PROMPT_FLAGS),
    }


def environment_problems(environment: dict | None) -> list[str]:
    """Problems in the additive block. Empty means a reader can rebuild from it.

    Silent on a manifest that carries no `pin_extension`: `capture-spine/1`
    predates this extension and stays valid without it.
    """
    env = environment or {}
    if "pin_extension" not in env:
        return []
    problems = []
    if env.get("pin_extension") != PIN_EXTENSION:
        problems.append(f"pin_extension is {env.get('pin_extension')!r}, expected {PIN_EXTENSION!r}")
    for key in ("binary_version", "binary_sha256"):
        if not env.get(key):
            problems.append(f"environment: missing {key}")

    acq = env.get("acquisition")
    if not isinstance(acq, dict):
        problems.append("environment.acquisition is missing")
    else:
        for key in ("download_base_url", "binary_url", "release_manifest_url",
                    "platform", "checksum_algorithm", "checksum"):
            if not acq.get(key):
                problems.append(f"environment.acquisition: missing {key}")
        if acq.get("checksum_algorithm") not in (None, CHECKSUM_ALGORITHM):
            problems.append(f"environment.acquisition: checksum_algorithm must be {CHECKSUM_ALGORITHM}")
        checksum = str(acq.get("checksum") or "")
        if checksum and not SHA256_HEX.match(checksum):
            problems.append("environment.acquisition: checksum is not a lowercase sha256 hex digest")
        plat = acq.get("platform")
        if plat and plat not in PLATFORMS:
            problems.append(f"environment.acquisition: unknown platform {plat!r}")
        version = env.get("binary_version")
        base = acq.get("download_base_url")
        if version and plat and base:
            if acq.get("binary_url") != binary_url(base, version, plat):
                problems.append(
                    "environment.acquisition: binary_url does not address "
                    "binary_version/platform under download_base_url"
                )
            if acq.get("release_manifest_url") != release_manifest_url(base, version):
                problems.append(
                    "environment.acquisition: release_manifest_url does not address "
                    "binary_version under download_base_url"
                )
        pinned = str(env.get("binary_sha256") or "")
        if pinned and checksum and pinned.lower() != checksum:
            problems.append(
                "environment.acquisition: checksum disagrees with environment.binary_sha256"
            )

    roles = env.get("model_roles")
    if not isinstance(roles, dict):
        problems.append("environment.model_roles is missing")
    else:
        for name, value in roles.items():
            if name not in MODEL_ROLE_VARS:
                problems.append(f"environment.model_roles: {name!r} is not a model-role variable")
            elif not isinstance(value, str) or not value.strip():
                problems.append(f"environment.model_roles: {name} has no value")

    flags = env.get("system_prompt_flags")
    if flags != SYSTEM_PROMPT_FLAGS:
        problems.append(
            f"environment.system_prompt_flags must be {SYSTEM_PROMPT_FLAGS}, got {flags!r}"
        )
    return problems


# -- command line ----------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _cmd_pin(args) -> int:
    """Emit the additive block for a local binary. Network use is optional."""
    binary = Path(args.binary).expanduser()
    if not binary.is_file():
        print(f"no such binary: {binary}", file=sys.stderr)
        return 1
    plat = args.platform or detect_platform()
    checksum = sha256_file(binary)
    size = binary.stat().st_size
    base = FALLBACK_DOWNLOAD_BASE_URL
    confirmed = None
    if not args.offline:
        try:
            base = resolve_download_base(_http_get(INSTALL_SCRIPT_URL).decode("utf-8", "replace"))
            release = json.loads(_http_get(release_manifest_url(base, args.version)).decode("utf-8", "replace"))
            entry = platform_entry(release, plat)
            if entry["checksum"] != checksum:
                print(
                    f"local binary hashes to {checksum} but the release manifest "
                    f"publishes {entry['checksum']} for {args.version}/{plat}",
                    file=sys.stderr,
                )
                return 1
            confirmed = _now()
        except Exception as exc:  # noqa: BLE001 - a pin is still emittable offline
            print(f"note: release manifest not confirmed ({exc})", file=sys.stderr)

    block = build_environment_pin(
        version=args.version,
        platform_key=plat,
        binary_sha256=checksum,
        base_url=base,
        model_roles=dict(
            (name, os.environ[name]) for name in MODEL_ROLE_VARS if os.environ.get(name)
        ) or {"ANTHROPIC_MODEL": args.model},
        size_bytes=size,
        confirmed_utc=confirmed,
    )
    problems = environment_problems({**block, "binary_version": args.version, "binary_sha256": checksum})
    if problems:
        print("pin rejected:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print(json.dumps(block, indent=2))
    return 0


def _cmd_acquire(args) -> int:
    manifest = json.loads(Path(args.manifest).read_text())
    env = manifest.get("environment") or {}
    problems = environment_problems(env)
    if problems:
        print("manifest environment rejected:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    if "pin_extension" not in env:
        print(
            f"acquisition refused: manifest environment has no {PIN_EXTENSION} extension",
            file=sys.stderr,
        )
        return 1
    acq = env.get("acquisition") or {}
    try:
        result = acquire(
            env["binary_version"],
            Path(args.dest).expanduser(),
            expected_sha256=acq["checksum"],
            platform_key=args.platform or acq.get("platform"),
            base_url=args.base_url,
        )
    except AcquisitionError as exc:
        print(f"acquisition refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cmd_verify(args) -> int:
    try:
        digest = verify_file(Path(args.binary).expanduser(), args.checksum)
    except AcquisitionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"{args.binary}: {CHECKSUM_ALGORITHM} {digest} ok")
    return 0


def _cmd_check(args) -> int:
    manifest = json.loads(Path(args.manifest).read_text())
    environment = manifest.get("environment") or {}
    problems = environment_problems(environment)
    if problems:
        print("problems:\n  " + "\n  ".join(problems))
        return 1
    if "pin_extension" in environment:
        print(f"{args.manifest}: {PIN_EXTENSION} ok")
    else:
        print(f"{args.manifest}: environment ok (no {PIN_EXTENSION} extension)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("pin", help="local binary -> the additive environment block")
    p.add_argument("binary", type=Path)
    p.add_argument("--version", required=True)
    p.add_argument("--platform")
    p.add_argument("--model", default="claude-opus-5", help="ANTHROPIC_MODEL when none is set in this environment")
    p.add_argument("--offline", action="store_true", help="do not contact the release service")
    p.set_defaults(func=_cmd_pin)

    p = sub.add_parser("acquire", help="manifest -> a checksum-verified binary on this machine")
    p.add_argument("manifest", type=Path)
    p.add_argument("--dest", required=True)
    p.add_argument("--platform")
    p.add_argument("--base-url", help="skip install-script resolution (for a mirror)")
    p.set_defaults(func=_cmd_acquire)

    p = sub.add_parser("verify", help="check a local binary against a checksum")
    p.add_argument("binary", type=Path)
    p.add_argument("--checksum", required=True)
    p.set_defaults(func=_cmd_verify)

    p = sub.add_parser("check", help="validate a manifest's additive environment block")
    p.add_argument("manifest", type=Path)
    p.set_defaults(func=_cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
