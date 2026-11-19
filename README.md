# makefun-gta6-trophy-rarity-forecast-01

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/belski21-growl/makefun-gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/belski21-growl/makefun-gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Forecast each Grand Theft Auto VI (PS5) trophy's earn rate on Exophase at 2026-11-26 00:00 UTC as five quantiles (5/25/50/75/95%), from the house's recorded reads up to the deadline. Python 3.13, standard library only.

## Model

A trophy's earn rate is a ratio, and its two halves move for different reasons, so the program forecasts them separately and divides:

- `players_tracked` only grows (new buyers syncing dilutes every rate);
- `earners` only grows (players progress through the game and lift the rate).

Each is fitted as a power law in log-time — a least-squares line of the log count against `ln(1 + hours since the release day began)` — over every read in the case's history, slopes clamped at zero and capped at 3.0 (the cap only binds on degenerate few-read fits, where two reads 10 minutes apart would otherwise extrapolate a rare trophy to 99.99%). The median is the ratio of the two extrapolations at the target. A trophy never earned in the history gets half the slowest earned peer's rate in its tier, not a flat 0.01%. The logit spread combines a random-walk term (`0.5·√days`), the earners fit's residual, and a constant `0.35` for one Exophase refresh jump (on launch night the page sat unchanged at 638 players, then jumped to 3,868 and every rate but the 100% one fell ~25%).

## Run it

```sh
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

Reads every `*.in` in the input directory and writes one `<id>.out` per case: `{"trophies": [{"id": n, "q": [q05, q25, q50, q75, q95]}, ...]}`. Deterministic — two runs write byte-identical output. No network at runtime.

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
