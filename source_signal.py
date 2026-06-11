#!/usr/bin/env python3
"""source_signal.py — Learn which of your discovery sources actually earn their place.

A small, self-contained measurement layer for anyone running an AI research or
discovery pipeline across multiple sources (X, Reddit, YouTube, newsletters,
Slack channels, RSS, whatever). Instead of guessing which sources are worth your
attention, it MEASURES it from what you actually use, and turns that into a spend
policy that keeps re-earning itself.

The design came out of a cognitive-stacking session: a rough scoring idea handed
to a different AI model, which corrected two things that matter and added the rest.

What makes it more than a hit-counter:
- Ranks by ABSOLUTE unique-used count, not used/surfaced ratio. A source giving
  you 10 usable items beats one giving 1 at a higher ratio.
- UNIQUE-yield: an item only counts for a source if no OTHER source surfaced it
  that run. This is what tells you whether a source is additive or just echoing
  another one. (You record which other sources also had it at selection time.)
- Beta smoothing (a shared prior for every source) so a source that surfaced 2
  items and you used 1 does not show a misleading 50 percent and outrank a
  source that gave you 10 usable items out of 40.
- A bandit, not a frozen leaderboard: a permanent exploration budget keeps
  re-testing benched sources so one that starts producing again can climb back,
  and you catch when a source's quality changes over time.

No dependencies beyond the Python standard library. Python 3.8+.

QUICK START
  # 1. After a discovery run, record what each source surfaced (the denominator):
  python3 source_signal.py surfaced --run r1 --source reddit --count 21
  python3 source_signal.py surfaced --run r1 --source x --count 15

  # 2. When you USE an item, record it (the numerator). --also lists any other
  #    sources that surfaced the same item; leave it off if the item was unique:
  python3 source_signal.py used --run r1 --source reddit \
      --item "the-thread-url" --reason "great accessible hook"
  python3 source_signal.py used --run r1 --source x \
      --item "same-story" --reason "but reddit had it too" --also reddit

  # 3. See what you have learned:
  python3 source_signal.py status

  # 4. Get the recommended spend policy (which sources to prioritize next run):
  python3 source_signal.py policy

Data lives in ./source_signal_data/ as plain JSONL. Delete it to reset.
Tune the knobs in CONFIG below.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "source_signal_data")
SURFACED = os.path.join(DATA_DIR, "surfaced.jsonl")
USED = os.path.join(DATA_DIR, "used.jsonl")

CONFIG = {
    # Shared Beta prior for every source (identical -> neutral, no source favored
    # at the start). Beta(1, 4) expects ~20% of surfaced items to be useful.
    "beta_alpha": 1.0,
    "beta_beta": 4.0,
    # A source must clear this many useful-per-run (smoothed) to count as "earning
    # its place" rather than "still being evaluated / exploration only."
    "usefulness_floor_per_run": 0.5,
    # Fraction of runs a benched source is still included, so it can climb back.
    "exploration_fraction": 0.15,
    # Attention budget: how many items to prioritize from the top vs bottom source.
    "attention_top": 15,
    "attention_floor": 3,
    # Mark a source "still calibrating" until this many of your selections involve
    # it (avoids judging a source on 2 data points).
    "calibration_decisions": 30,
}


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _append(path: str, row: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read(path: str) -> list:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def cmd_surfaced(a) -> int:
    _append(SURFACED, {
        "ts": _now(), "run": a.run, "source": a.source.lower(),
        "count": int(a.count), "cost": float(a.cost),
    })
    return 0


def cmd_used(a) -> int:
    if not a.reason.strip():
        sys.stderr.write("A one-line --reason is required (keeps the log honest and auditable).\n")
        return 1
    also = [s.strip().lower() for s in (a.also or "").split(",") if s.strip()]
    _append(USED, {
        "ts": _now(), "run": a.run, "source": a.source.lower(),
        "item": a.item, "reason": a.reason.strip(),
        "tag": a.tag, "also_surfaced_by": also,
    })
    return 0


def aggregate() -> dict:
    surfaced = _read(SURFACED)
    used = _read(USED)
    sources = sorted({r["source"] for r in surfaced} | {u["source"] for u in used})

    runs_of: dict = {s: set() for s in sources}
    stats: dict = {}
    for s in sources:
        stats[s] = {
            "source": s, "surfaced": 0, "used": 0, "unique_used": 0,
            "cost": 0.0, "runs": 0,
        }
    for r in surfaced:
        s = r["source"]
        stats[s]["surfaced"] += int(r.get("count", 0))
        stats[s]["cost"] += float(r.get("cost", 0.0))
        runs_of[s].add(r["run"])
    for s in sources:
        stats[s]["runs"] = len(runs_of[s])
    for u in used:
        s = u["source"]
        stats[s]["used"] += 1
        if not u.get("also_surfaced_by"):
            stats[s]["unique_used"] += 1

    alpha, beta = CONFIG["beta_alpha"], CONFIG["beta_beta"]
    floor = CONFIG["usefulness_floor_per_run"]
    for s, st in stats.items():
        runs = max(st["runs"], 0)
        # Smoothed unique-useful per run (neutral 0.5 with no data).
        st["unique_per_run"] = round((st["unique_used"] + 1.0) / (runs + 2.0), 4)
        # Beta-smoothed yield rate (diagnostic: how often this source's items land).
        st["yield_rate"] = round((st["unique_used"] + alpha) / (st["surfaced"] + alpha + beta), 4)
        st["unique_per_cost"] = None if st["cost"] <= 0 else round(st["unique_used"] / st["cost"], 4)
        st["clears_floor"] = st["unique_per_run"] >= floor
        st["calibrating"] = st["used"] < CONFIG["calibration_decisions"]
    return {"sources": stats, "n_runs": len({r["run"] for r in surfaced} | {u["run"] for u in used})}


def cmd_status(a) -> int:
    data = aggregate()
    if not data["sources"]:
        print("No data yet. Record some `surfaced` and `used` events first.")
        return 0
    print(f"Source signal ({data['n_runs']} runs)\n")
    print(f"{'source':14}{'surf':>6}{'used':>6}{'uniq':>6}{'uniq/run':>10}{'yield':>8}  status")
    order = sorted(data["sources"], key=lambda s: data["sources"][s]["unique_used"], reverse=True)
    for s in order:
        st = data["sources"][s]
        status = "EARNS IT" if st["clears_floor"] else ("calibrating" if st["calibrating"] else "below floor")
        print(f"{s:14}{st['surfaced']:>6}{st['used']:>6}{st['unique_used']:>6}"
              f"{st['unique_per_run']:>10}{st['yield_rate']:>8}  {status}")
    return 0


def cmd_policy(a) -> int:
    data = aggregate()
    stats = data["sources"]
    if not stats:
        print("No data yet. All sources are neutral at cold start: run them all, "
              "record what you use, and the ranking will earn itself.")
        return 0
    # Rank by absolute unique-used; cost-efficiency breaks ties among floor-clearers.
    def key(s):
        st = stats[s]
        eff = st["unique_per_cost"] if st["unique_per_cost"] is not None else float("inf")
        return (1 if st["clears_floor"] else 0, st["unique_used"], eff)
    ranked = sorted(stats, key=key, reverse=True)
    n = len(ranked)
    top, flo = CONFIG["attention_top"], CONFIG["attention_floor"]
    print(f"Recommended spend policy ({data['n_runs']} runs)\n")
    print("Prioritize your attention/budget roughly like this next run:\n")
    for i, s in enumerate(ranked):
        st = stats[s]
        frac = 1.0 - (i / max(n - 1, 1))
        budget = int(round(flo + frac * (top - flo)))
        tag = "earns it" if st["clears_floor"] else ("calibrating" if st["calibrating"] else "exploration only")
        print(f"  {s:14} ~{budget:>2} items   ({tag}, {st['unique_used']} unique used)")
    benched = [s for s in ranked if not stats[s]["clears_floor"] and not stats[s]["calibrating"]]
    if benched:
        every = max(1, round(1.0 / CONFIG["exploration_fraction"]))
        print(f"\nKeep re-testing these about 1 run in {every} (they may start producing again): "
              f"{', '.join(benched)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("surfaced", help="Record how many items a source surfaced in a run")
    p.add_argument("--run", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--count", required=True, type=int)
    p.add_argument("--cost", type=float, default=0.0, help="Optional API/credit cost for this source")
    p.set_defaults(func=cmd_surfaced)

    p = sub.add_parser("used", help="Record an item you actually used")
    p.add_argument("--run", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--item", required=True, help="URL or id")
    p.add_argument("--reason", required=True, help="One line; keeps the log auditable")
    p.add_argument("--tag", default="", help="Optional category, e.g. hook / seed / quote")
    p.add_argument("--also", default="", help="Comma list of OTHER sources that also surfaced this item")
    p.set_defaults(func=cmd_used)

    sub.add_parser("status", help="Show the current source matrix").set_defaults(func=cmd_status)
    sub.add_parser("policy", help="Show the recommended spend policy").set_defaults(func=cmd_policy)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
