"""Minimum detectable effect for the bakeoff 9 design.

The preregistration commits 10 tasks x 3 reps per cell and an Accept rule that
needs a **>=40% relative** fall in the unsupported-claim rate with a
task-clustered 95% CI excluding zero. This module answers what that design can
actually resolve, as a function of the control base rate `p0` and of
between-task heterogeneity, so the question can be settled before freeze
without spending anything. T-015.

Model. Task `i` has a latent control rate `u_i ~ Beta`, with mean `p0` and
intraclass correlation `icc = 1/(1+a+b)`; the treated rate on the same task is
`u_i * (1 - r)`. Arms share fixtures, so tasks are **paired** and the task
effect cancels -- the optimistic assumption, and the one the design actually
makes. Each arm draws `reps` Bernoulli trials at its latent rate. Analysis is
the paired t on task-level differences, which is the clustered-by-task analysis
the protocol declares.

`accept_power` is the probability the Accept rule fires: CI lower bound above
zero **and** the observed relative fall at or above the threshold. It is
strictly below `detect_power`, the probability of merely excluding zero,
because an unbiased point estimate lands below a true effect half the time.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Two-sided Student-t critical values by degrees of freedom (tasks - 1).
# Holm-Bonferroni across the four falsification criteria and the interaction
# makes 0.05/5 the most stringent threshold any one of them can face, so both
# levels are carried. Tabulated rather than computed: the task counts worth
# considering are few, and a table is checkable against any t table.
T_CRIT = {
    9: {0.05: 2.262157, 0.01: 3.249836},    # 10 tasks, the declared design
    14: {0.05: 2.144787, 0.01: 2.976843},   # 15
    19: {0.05: 2.093024, 0.01: 2.860935},   # 20
    29: {0.05: 2.045230, 0.01: 2.756386},   # 30
    39: {0.05: 2.022691, 0.01: 2.707913},   # 40
    49: {0.05: 2.009575, 0.01: 2.679952},   # 50
}
ALPHAS = (0.05, 0.01)


def t_crit(tasks: int, alpha: float) -> float:
    """Critical value for the paired t on `tasks` clusters."""
    try:
        return T_CRIT[tasks - 1][alpha]
    except KeyError:
        raise ValueError(f"no tabulated critical value for {tasks} tasks at alpha={alpha}")

TASKS = 10
REPS = 3
THRESHOLD = 0.40


def beta_params(mean: float, icc: float) -> tuple[float, float]:
    """Beta shape parameters for a given mean and intraclass correlation."""
    if not 0.0 < mean < 1.0:
        raise ValueError("mean must be strictly between 0 and 1")
    if not 0.0 < icc < 1.0:
        raise ValueError("icc must be strictly between 0 and 1")
    total = 1.0 / icc - 1.0
    return mean * total, (1.0 - mean) * total


def _draw_rate(rng: random.Random, rate: float, reps: int) -> float:
    return sum(rng.random() < rate for _ in range(reps)) / reps


def trial(rng: random.Random, a: float, b: float, r: float, tasks: int, reps: int):
    """One simulated cell. Returns (relative fall, CI lower bound at each alpha)."""
    control, diffs = [], []
    for _ in range(tasks):
        u = rng.betavariate(a, b)
        x1 = _draw_rate(rng, u, reps)
        x2 = _draw_rate(rng, u * (1.0 - r), reps)
        control.append(x1)
        diffs.append(x1 - x2)
    mean_d = sum(diffs) / tasks
    mean_c = sum(control) / tasks
    var = sum((d - mean_d) ** 2 for d in diffs) / (tasks - 1)
    se = math.sqrt(var / tasks)
    relative = mean_d / mean_c if mean_c > 0 else 0.0
    lower = {a: mean_d - t_crit(tasks, a) * se for a in ALPHAS}
    return relative, lower


def power(p0: float, icc: float, r: float, *, alpha: float = 0.05,
          tasks: int = TASKS, reps: int = REPS, sims: int = 4000,
          seed: int = 20260825, threshold: float = THRESHOLD) -> dict:
    """Probability the design detects an effect, and that Accept fires."""
    a, b = beta_params(p0, icc)
    rng = random.Random(seed)
    detected = accepted = 0
    for _ in range(sims):
        relative, lower = trial(rng, a, b, r, tasks, reps)
        if lower[alpha] > 0:
            detected += 1
            if relative >= threshold:
                accepted += 1
    return {"detect_power": detected / sims, "accept_power": accepted / sims}


def mde(p0: float, icc: float, *, alpha: float = 0.05, target: float = 0.80,
        key: str = "accept_power", ceiling: float = 0.95, **kw) -> float | None:
    """Smallest true relative fall reaching `target` power, or None above ceiling.

    Bisection is valid because power rises monotonically in the true effect.
    """
    if power(p0, icc, ceiling, alpha=alpha, **kw)[key] < target:
        return None
    lo, hi = 0.0, ceiling
    for _ in range(12):
        mid = (lo + hi) / 2
        if power(p0, icc, mid, alpha=alpha, **kw)[key] >= target:
            hi = mid
        else:
            lo = mid
    return hi


# -- bakeoff 8 heterogeneity anchor ----------------------------------------

BAKEOFF8 = ROOT / "campaigns/clause-bakeoff-8-2026-08-11/out/bakeoff-20260814T055452Z/judgments"


def icc_anova(task_rates: dict[str, list[int]]) -> dict:
    """One-way ANOVA intraclass correlation over per-task binary outcomes."""
    tasks = [v for v in task_rates.values() if v]
    k = len(tasks)
    m = len(tasks[0])
    if k < 2 or any(len(v) != m for v in tasks) or m < 2:
        raise ValueError("need >=2 tasks with equal, >=2 repetitions")
    rates = [sum(v) / m for v in tasks]
    grand = sum(rates) / k
    msb = m * sum((p - grand) ** 2 for p in rates) / (k - 1)
    msw = sum(m * p * (1 - p) for p in rates) / (k * (m - 1))
    denom = msb + (m - 1) * msw
    icc = 0.0 if denom == 0 else max(0.0, (msb - msw) / denom)
    return {"tasks": k, "reps": m, "p0": grand, "icc": icc}


def bakeoff8_anchor(directory: Path = BAKEOFF8, arm: str = "A", judge: str = "codex") -> dict:
    """Defect presence per task and repetition in bakeoff 8's control arm.

    Bakeoff 8 is the tool-less single-turn regime bakeoff 9 declares
    incomparable. This is a plausibility anchor for heterogeneity, never a prior.
    """
    rates: dict[str, list[int]] = {}
    for path in sorted(directory.glob(f"*-{judge}.json")):
        row = json.loads(path.read_text())
        answers = (row.get("judgment") or {}).get("answers") or {}
        entry = answers.get(arm)
        if entry is None:
            continue
        rates.setdefault(row["task_id"], []).append(int(bool(entry.get("material_errors"))))
    out = icc_anova(rates)
    out.update({"judge": judge, "arm": arm, "regime": "incomparable-to-bakeoff-9"})
    return out


# -- cli -------------------------------------------------------------------

BASE_RATES = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60)
ICCS = (0.05, 0.15, 0.30)


def _cmd_grid(args) -> int:
    print(f"MDE at {int(args.target * 100)}% power, {TASKS} tasks x {REPS} reps, "
          f"paired, alpha={args.alpha}, sims={args.sims}")
    print("relative fall needed for the Accept rule to fire (None = unreachable at <=95%)")
    print("  p0  " + "".join(f"  icc={i:<6}" for i in ICCS))
    for p0 in BASE_RATES:
        cells = []
        for icc in ICCS:
            value = mde(p0, icc, alpha=args.alpha, target=args.target, sims=args.sims)
            cells.append("  none    " if value is None else f"  {value:>6.0%}  ")
        print(f"  {p0:.2f}" + "".join(cells))
    return 0


def _cmd_power(args) -> int:
    result = power(args.p0, args.icc, args.r, alpha=args.alpha, sims=args.sims)
    print(json.dumps({"p0": args.p0, "icc": args.icc, "r": args.r,
                      "alpha": args.alpha, **result}, indent=2))
    return 0


def _cmd_sizing(args) -> int:
    """Tasks needed to pull the MDE down to a stated true effect.

    Asking for 80% power *at* a true 40% fall is unanswerable at any sample
    size: the Accept rule needs the point estimate to clear the same bar the
    true value sits on, so its power there approaches 50% from below and never
    80%. Sizing is therefore stated as "what does the design resolve", not "how
    many tasks make the committed threshold detectable".
    """
    print(f"tasks needed for MDE <= {args.effect:.0%} at {int(args.target * 100)}% power, "
          f"p0={args.p0}, icc={args.icc}, alpha={args.alpha}")
    for reps in (3, 5, 10):
        hit = None
        for tasks in sorted(t + 1 for t in T_CRIT):
            value = mde(args.p0, args.icc, alpha=args.alpha, target=args.target,
                        tasks=tasks, reps=reps, sims=args.sims)
            if value is not None and value <= args.effect:
                hit = (tasks, value)
                break
        if hit:
            print(f"  {reps} reps: {hit[0]} tasks ({hit[0] * reps * 2} responses), "
                  f"MDE {hit[1]:.0%}")
        else:
            print(f"  {reps} reps: not reached at 50 tasks")
    return 0


def _cmd_anchor(args) -> int:
    print(json.dumps(bakeoff8_anchor(judge=args.judge), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("grid", help="MDE over base rate x heterogeneity")
    p.add_argument("--alpha", type=float, default=0.05, choices=ALPHAS)
    p.add_argument("--target", type=float, default=0.80)
    p.add_argument("--sims", type=int, default=4000)
    p.set_defaults(func=_cmd_grid)

    p = sub.add_parser("power", help="power at one point")
    p.add_argument("p0", type=float)
    p.add_argument("icc", type=float)
    p.add_argument("r", type=float)
    p.add_argument("--alpha", type=float, default=0.05, choices=ALPHAS)
    p.add_argument("--sims", type=int, default=4000)
    p.set_defaults(func=_cmd_power)

    p = sub.add_parser("sizing", help="tasks needed at the committed threshold")
    p.add_argument("--p0", type=float, default=0.30)
    p.add_argument("--icc", type=float, default=0.15)
    p.add_argument("--effect", type=float, default=0.50)
    p.add_argument("--alpha", type=float, default=0.05, choices=ALPHAS)
    p.add_argument("--target", type=float, default=0.80)
    p.add_argument("--sims", type=int, default=2000)
    p.set_defaults(func=_cmd_sizing)

    p = sub.add_parser("anchor", help="bakeoff 8 heterogeneity anchor")
    p.add_argument("--judge", default="codex")
    p.set_defaults(func=_cmd_anchor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
