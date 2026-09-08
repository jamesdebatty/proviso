# inspect_swe binary acquisition — pinned excerpt

Preserved 2026-08-25 so the citation survives a scratch-directory purge. This
mechanism was previously cited as a path inside a `/tmp` clone, which did not
survive the purge. Cite this file or the upstream commit instead.

- Repository: https://github.com/meridianlabs-ai/inspect_swe
- Commit: `0ccc009694cc6f75023bf1dffffcf119885a5eef`
- Commit date: 2026-08-21T13:29:00-07:00
- File: `src/inspect_swe/_claude_code/agentbinary.py`
- File sha256: `0cb63272261291232053b74b6d12d7d23eefa6cd9cba69fee7de550a1f9faeca`
- Access date: 2026-08-25
- Evidence class: **primary** (source code)
- Scope: how Claude Code binaries are resolved and checksum-verified.
- Limitation: shallow clone of the default branch at one moment. Line numbers
  drift between commits; the commit and file hash above are the stable
  reference.

## License of the excerpted material

The code quoted below is from `inspect_swe`, redistributed here under its own
licence. This notice is MIT's only redistribution obligation, and it applies to
the excerpt, not to the rest of this repository.

```
SPDX-License-Identifier: MIT

Copyright (c) 2025 Meridian Labs

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**This is corroboration, not T-005's source of record.** The mechanism reads
Anthropic's own install script to find the download base URL — that install
script is the primary source, and `inspect_swe` is one reading of it. T-005
derived the mechanism from the install script directly
(`sources/2026-08-25-t005-environment-acquisition.md`). This excerpt exists so
the citation in `wayfinder/tickets/T-005-environment-acquisition.md` is
checkable without a network fetch or a surviving clone.

## Full file at the pinned commit

```python
import re
from pathlib import Path

from pydantic import BaseModel
from typing_extensions import Literal

from .._util.agentbinary import AgentBinarySource, AgentBinaryVersion
from .._util.appdirs import package_cache_dir
from .._util.download import download_text_file
from .._util.sandbox import SandboxPlatform


def claude_code_binary_source() -> AgentBinarySource:
    cached_binary_dir = package_cache_dir("claude-code-downloads")

    async def resolve_version(
        version: Literal["stable", "latest"] | str, platform: SandboxPlatform
    ) -> AgentBinaryVersion:
        base_url = await _claude_code_download_base_url()
        version = await _claude_code_version(base_url, version)
        manifest = await _claude_code_manifest(base_url, version)
        expected_checksum = _checksum_for_platform(manifest, platform)
        download_url = f"{base_url}/{version}/{platform}/claude"
        return AgentBinaryVersion(version, expected_checksum, download_url)

    def cached_binary_path(version: str, platform: SandboxPlatform) -> Path:
        return cached_binary_dir / f"claude-{version}-{platform}"

    def list_cached_binaries() -> list[Path]:
        return list(cached_binary_dir.glob("claude-*"))

    return AgentBinarySource(
        agent="claude code",
        binary="claude",
        resolve_version=resolve_version,
        cached_binary_path=cached_binary_path,
        list_cached_binaries=list_cached_binaries,
        post_download=None,
        post_install=None,
    )


async def _claude_code_download_base_url() -> str:
    INSTALL_SCRIPT_URL = "https://claude.ai/install.sh"
    script_content = await download_text_file(INSTALL_SCRIPT_URL)
    for pattern in [
        r'DOWNLOAD_BASE_URL="(https://[^"]+)"',
        r'GCS_BUCKET="(https://[^"]+)"',
    ]:
        match = re.search(pattern, script_content)
        if match is not None:
            return match.group(1)
    raise RuntimeError("Unable to determine download base URL for claude code.")


async def _claude_code_version(base_url: str, target: str) -> str:
    # validate target
    target_pattern = r"^(stable|latest|[0-9]+\.[0-9]+\.[0-9]+(-[^[:space:]]+)?)$"
    if re.match(target_pattern, target) is None:
        raise RuntimeError(
            "Invalid version target (must be 'stable', 'latest', or a semver version number)"
        )

    # resolve target alias if required
    if target in ["stable", "latest"]:
        version_url = f"{base_url}/{target}"
        version = await download_text_file(version_url)
        return version
    else:
        return target


class PlatformInfo(BaseModel):
    checksum: str
    size: int


class Manifest(BaseModel):
    version: str
    platforms: dict[str, PlatformInfo]


async def _claude_code_manifest(base_url: str, version: str) -> Manifest:
    manifest_url = f"{base_url}/{version}/manifest.json"
    manifest_json = await download_text_file(manifest_url)
    return Manifest.model_validate_json(manifest_json)


def _checksum_for_platform(manifest: Manifest, platform: SandboxPlatform) -> str:
    if platform not in manifest.platforms:
        raise RuntimeError(f"Platform '{platform}' not found in manifest.")
    return manifest.platforms[platform].checksum
```
