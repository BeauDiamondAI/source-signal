# Source Signal — learn which of your discovery sources actually earn their place

A tiny, dependency-free tool for anyone running an AI research or discovery
pipeline across multiple sources. Instead of guessing which sources are worth
your attention, it measures it from what you actually use, and turns that into a
spend policy that keeps re-earning itself.

**One file. Python 3.8+. No installs. Your data stays local.**

---

## Why this exists (and how it was built)

If you pull signal from a bunch of places (X, Reddit, YouTube, newsletters,
Slack, RSS), you eventually hardcode a hunch about which ones matter: "X and
YouTube are great, Instagram is noisy, TikTok is junk." That hunch is usually
half-wrong, and it freezes. A source you wrote off six months ago might be your
best source today and you would never know.

This tool replaces the hunch with measurement. But the interesting part is HOW
it got designed, because it is the real lesson:

I had a rough scoring idea and thought it was nearly done. Then I handed the
whole design to a *different* AI model, from a different lab, and asked one
question: **what is wrong with this?** Sixty seconds later it had:

1. **Fixed the ranking metric.** My version ranked sources by hit-rate (what
   fraction of a source's items you use). It pointed out hit-rate is the wrong
   number: a source giving you 10 usable items at a lower rate beats one giving
   1 at a high rate. **Rank by total useful output, not the ratio.**

2. **Caught the flaw I had missed entirely.** If two sources surface the SAME
   item, the second one added nothing. You have to credit a source only for
   items *no other source surfaced*. Otherwise you keep paying for a platform
   that is just echoing another one. **This is the single number that tells you
   whether a noisy source is genuinely additive or just expensive noise.**

3. Added Beta smoothing (so a source with 2 items and 1 used does not show a
   misleading 50 percent), a usefulness floor, cost-efficiency tie-breaking, and
   a permanent exploration budget so benched sources get re-tested.

The design you are holding is its design, not mine. That practice — taking your
best output and handing it to a *different* model whose whole job is to start
from your answer and improve it — is called **cognitive stacking**, and it is
the cheapest high-leverage habit in AI work right now. A task-completion model
spends 100 percent of its attention on the task. A second model spends 100
percent of its attention on making the first one's work better. Same cost,
different cognitive position.

---

## Install

There is nothing to install. Copy `source_signal.py` somewhere and run it.

```bash
python3 source_signal.py status
```

---

## Use it in four moves

**1. After a discovery run, record what each source surfaced (the denominator).**
A "run" is any id you choose — a date, a topic, a batch.

```bash
python3 source_signal.py surfaced --run 2026-06-11 --source reddit --count 21
python3 source_signal.py surfaced --run 2026-06-11 --source x --count 15
python3 source_signal.py surfaced --run 2026-06-11 --source youtube --count 11 --cost 11
```

`--cost` is optional (use it for sources that cost API credits, so the policy can
prefer cheaper sources at equal value).

**2. When you actually USE an item, record it (the numerator).**
If another source also surfaced the same item, list it with `--also` so the item
does not get double-counted as "unique."

```bash
python3 source_signal.py used --run 2026-06-11 --source reddit \
    --item "reddit.com/.../thread" --reason "strong accessible hook"

python3 source_signal.py used --run 2026-06-11 --source x \
    --item "the-same-story" --reason "but reddit had it first" --also reddit
```

The `--reason` is required on purpose. One honest line per selection keeps the
log auditable later, when you want to know *why* a source looked good.

**3. See what you have learned.**

```bash
python3 source_signal.py status
```

```
source          surf  used  uniq  uniq/run   yield  status
reddit            21     4     3    1.3333  0.1538  EARNS IT
x                 15     2     2       1.0  0.1500  EARNS IT
youtube           11     1     1    0.6667  0.1250  EARNS IT
instagram          8     0     0    0.3333  0.0769  calibrating
```

`uniq` (unique-used) is the number that drives the ranking. `instagram` surfaced
8 and you used 0 — the data is starting to tell you something the hunch only
suspected.

**4. Get the recommended spend policy for next run.**

```bash
python3 source_signal.py policy
```

It ranks your sources by absolute unique-used, tells you roughly how much
attention each one earns, and — importantly — lists the benched sources it wants
you to re-test every so often, because this is a bandit, not a frozen list.

---

## The knobs

Open the file and edit `CONFIG` near the top:

- `beta_alpha` / `beta_beta` — the shared smoothing prior. Identical for every
  source so nothing is favored at the start.
- `usefulness_floor_per_run` — how much a source must produce to "earn its place."
- `exploration_fraction` — how often benched sources get re-tested (default 15%).
- `attention_top` / `attention_floor` — the attention budget spread.
- `calibration_decisions` — how many of your selections must involve a source
  before it is judged rather than "still calibrating."

---

## Data and reset

Everything lives in `./source_signal_data/` as plain JSONL you can read and edit.
Delete that folder to start over.

---

## License

MIT. Use it, change it, ship it. If it is useful, the thing worth passing on is
the habit, not the script: take your AI's best answer, hand it to a different
model, and ask what is wrong with it. That is where this came from.
