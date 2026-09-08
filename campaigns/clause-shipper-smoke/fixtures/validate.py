#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

CAMPAIGN = Path(__file__).resolve().parents[1]
ROOT = CAMPAIGN.parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from clause_campaign import ClauseCampaign  # noqa: E402


def main() -> int:
    problems: list[str] = []
    try:
        campaign = ClauseCampaign.load(CAMPAIGN / "campaign.toml")
        if len(campaign.plan()["cases"]) != 4:
            problems.append("declaration must produce four planned trials")
    except (OSError, ValueError) as exc:
        problems.append(str(exc))

    for problem in problems:
        print(problem)
    print(f"{len(problems)} problems")
    return bool(problems)


if __name__ == "__main__":
    raise SystemExit(main())
