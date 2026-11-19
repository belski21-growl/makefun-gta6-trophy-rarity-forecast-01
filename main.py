# SPDX-License-Identifier: MIT
"""gta6-trophy-rarity-forecast-01: forecast each GTA VI (PS5) trophy's earn rate
on Exophase at the case's target, as five quantiles (5/25/50/75/95%).

Python 3.13, standard library only. Deterministic: no randomness, no network,
no wall-clock reads, fixed iteration order; two runs on the same case write
byte-identical output.

Model -- earners / players decomposition, fitted in log-time
------------------------------------------------------------
A trophy's earn rate is a ratio, and its two halves move for different
reasons, so forecasting the ratio directly mixes them up:

    rate(t) = earners(t) / players_tracked(t)

* ``players_tracked`` only grows: new buyers sync their PSN profile and join
  the denominator. It dilutes every rate.
* ``earners`` only grows: players earn the trophy as they progress through
  the game. It lifts the rate.

Both are modelled as power laws in log-time, i.e. straight lines of the log
count against ``x = ln(1 + hours since the release day began)``:

    ln(players) = a_n + b_n * x        (b_n >= 0)
    ln(earners) = a_e + b_e * x        (b_e >= 0)

fitted by ordinary least squares over every read of the case's history (a
read that lacks the trophy is skipped for that trophy). The median forecast
is the ratio of the two extrapolations at the target:

    m = 100 * exp(a_e + b_e * x_T) / exp(a_n + b_n * x_T)

clamped to [0.01, 99.99]. Slopes are clamped at zero because neither count
can fall; any apparent fall is rounding of the page's 2-decimal rates.

Why this beats the house persistence baseline: the baseline says every rate
stays where the last read put it. Over the final's 4.5-day horizon that is
wrong in both directions -- story trophies climb as players finish chapters,
while dilution drags slow trophies down. This model lets the two forces
separate, so a trophy whose earners grow faster than the player base is
forecast up, and one whose earners stall is forecast down.

Slopes are capped at 3.0 in log-time: earners and players cannot
sustainably grow faster than ~20x per unit of ln(1 + hours), and the cap
only binds on degenerate few-read fits -- a trophy first earned in the
last two reads, 10 minutes apart, has its slope set by two rounding
steps and would otherwise extrapolate to a 99.99% median. Fits from
fewer than 4 positive reads also get their residual floored at 0.5: a
line through 2 points has zero measured residual by construction, which
would claim false precision for a slope estimated from almost no data.

Spread -- honest width on the logit scale
------------------------------------------
Quantiles are ``inv_logit(logit(m) + z_tau * s)`` with ``z`` the standard
normal quantiles. The logit spread ``s`` combines three independent
uncertainties (root-sum-of-squares):

* random walk: ``0.5 * sqrt(horizon in days)`` (the house baseline's term);
* fit residual: the standard deviation of the log-earners fit's residuals,
  capped at 1.0 (0 when the history is flat, as on launch night);
* refresh jump: ``0.35`` logit units. Exophase refreshes a game's counts on
  its own schedule, in jumps hours apart, not continuously: on launch night
  the page sat unchanged at 638 players from 23:48Z to 04:00Z, then jumped to
  3,868 players at 04:30Z. The totals pin down how far the other rates fell:
  trophies earned went 943 to 4,276, but the one 100% trophy alone accounts
  for 3,868 of the latter, so the other 54 trophies' earners grew only ~1.5x
  against 6.1x player growth -- their rates fell roughly 4x (~1.4 logit).
  That is also why the house baseline scores ~1.51 on the practice. A
  refresh can land inside any horizon, so the term is constant, not scaled
  by horizon.
* ignorance premium: ``0.6`` logit units, added when the history carries no
  dynamic signal at all -- every read identical, so the earners fit is flat
  with zero residual (launch night). With no variation the data cannot say
  how fast earners or players will move, and the honest band must admit a
  refresh-sized jump either way. It does not fire on the final, whose two
  days of 10-minute reads carry real dynamics.

Trophies never earned in the history (earners 0 throughout) get a
tier-shrunk median with a wide spread (s = 1.8), so the upper quantiles
still reach plausible values. The median is half the slowest earned
trophy's last-read rate in the same tier (falling back to the slowest
earned trophy overall when the tier has no earned peer), floored at 0.01:
a never-earned trophy is by selection slower than the slowest earned
peer in its tier, but not infinitely slower -- a flat 0.01% claims it
stays rarer than every peer, which the tier structure contradicts. On
the practice this changes nothing (every trophy was earned on launch
night); it only bites on the final, where the rare grind trophies sit
at zero. A trophy at 100% in the last read is forecast 100 at every quantile:
every tracked player holds it, and the page's 2-decimal print cannot go
higher. A case with too little history to fit falls back to the persistence
median with the random-walk + refresh spread.

Run: ``MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py``
reads every ``*.in`` in the input directory (in name order) and writes one
``<id>.out`` per case: ``{"trophies": [{"id": n, "q": [q05, q25, q50, q75,
q95]}, ...]}``, quantiles rounded to 4 decimals, half up, non-decreasing.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so a module
# shipped beside this file would import. (This entry is one file.)
sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]

# Random-walk volatility of a rate's logit, per square-root day (house term).
SIGMA_RW = 0.5
# Logit width allowed for one Exophase refresh jump (see module docstring).
SIGMA_REFRESH = 0.35
# Ignorance premium when the history shows no variation at all.
SIGMA_IGNORANCE = 0.6
# Spread for a trophy with no earners at all in the history.
SPREAD_NEVER_EARNED = 1.8
# A never-earned trophy's median is this fraction of the slowest earned
# trophy in its tier (see module docstring).
TIER_PRIOR_FRACTION = 0.5
# Hard cap on the logit spread, so a noisy fit cannot blow the band out.
SPREAD_CAP = 2.5
# Hard cap on a fitted log-time slope (earners or players); only binds on
# degenerate few-read fits (see module docstring).
SLOPE_CAP = 3.0
# Fits from fewer than this many positive reads get their residual floored,
# because a line through 2-3 points has ~zero measured residual by
# construction and would otherwise claim false precision.
SMALL_N = 4
MIN_RESID_SMALL_N = 0.5


def clamp_rate(x: float) -> float:
    return min(99.99, max(0.01, x))


def logit(pct: float) -> float:
    p = clamp_rate(pct)
    return math.log(p / (100.0 - p))


def inv_logit(lg: float) -> float:
    if lg >= 0:
        return 100.0 / (1.0 + math.exp(-lg))
    e = math.exp(lg)
    return 100.0 * e / (1.0 + e)


def round4(x: float) -> float | int:
    """x rounded to 4 decimals, half up, as JavaScript's
    Math.round(x * 10000) / 10000 rounds it. Whole numbers come back as int,
    so json.dumps writes 100 where JavaScript writes 100 (not 100.0)."""
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000
    return int(value) if value.is_integer() else value


def norm_ppf(p: float) -> float:
    """Standard normal quantile (Acklam's rational approximation, |err| < 1.2e-9)."""
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285984469534e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00,
         3.754408661907416e00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def ols(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Least squares y = a + b*x. Returns (intercept, slope, residual std).
    A degenerate x (all equal) gives slope 0 and the mean as intercept."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        resid = math.sqrt(sum((y - my) ** 2 for y in ys) / n) if n else 0.0
        return my, 0.0, resid
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    a = my - b * mx
    dof = max(n - 2, 1)
    resid = math.sqrt(sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / dof)
    return a, b, resid


def forecast_trophy(
    series: list[tuple[float, float, float | None]],
    x_target: float,
    horizon_days: float,
    never_median: float | None = None,
) -> list[float | int]:
    """series: (x, players_tracked, rate-or-None) per read, oldest first.
    never_median: tier-prior median for a never-earned trophy (half the
    slowest earned peer's last rate in its tier), or None.
    Returns the five quantiles for one trophy."""
    z = [norm_ppf(level) for level in LEVELS]
    rw = SIGMA_RW * math.sqrt(horizon_days)

    # --- players: ln(n) = a + b*x, slope clamped >= 0 -----------------------
    px = [x for x, n, _ in series if n and n > 0]
    py = [math.log(n) for _, n, _ in series if n and n > 0]
    if len(px) >= 2:
        a_n, b_n, _ = ols(px, py)
        b_n = min(max(0.0, b_n), SLOPE_CAP)
        log_n_t = a_n + b_n * x_target
    elif px:
        log_n_t = py[-1]
    else:
        log_n_t = 0.0
    # Players never shrink below the last read's count.
    last_n = next((n for _, n, _ in reversed(series) if n and n > 0), None)
    if last_n is not None:
        log_n_t = max(log_n_t, math.log(last_n))

    # --- earners: ln(e) = a + b*x over reads where the trophy was earned ----
    ex = [x for x, n, r in series if r is not None and n and r > 0]
    ey = [math.log(r * n / 100.0) for x, n, r in series if r is not None and n and r > 0]

    last_rate = next((r for _, _, r in reversed(series) if r is not None), None)
    if last_rate is not None and last_rate >= 100.0:
        return [100, 100, 100, 100, 100]

    if len(ex) >= 2:
        a_e, b_e, resid = ols(ex, ey)
        b_e = min(max(0.0, b_e), SLOPE_CAP)
        log_e_t = a_e + b_e * x_target
        median = 100.0 * math.exp(log_e_t - log_n_t)
        if len(ex) < SMALL_N:
            # A line through 2-3 points fits them (near-)exactly, so the
            # measured residual understates the slope's uncertainty.
            resid = max(resid, MIN_RESID_SMALL_N)
        spread = math.sqrt(rw * rw + min(resid, 1.0) ** 2 + SIGMA_REFRESH ** 2)
        if len(set(ey)) <= 1:
            # Perfectly flat history: no dynamic signal at all (launch night).
            spread = math.sqrt(spread * spread + SIGMA_IGNORANCE ** 2)
    elif len(ex) == 1:
        # One positive read: earners flat at that count, players as fitted.
        # A single read carries no dynamic signal either.
        median = 100.0 * math.exp(ey[0] - log_n_t)
        spread = math.sqrt(rw * rw + SIGMA_REFRESH ** 2 + SIGMA_IGNORANCE ** 2)
    elif last_rate is not None:
        # Never earned, but the page lists a (zero) rate: use the tier prior
        # (half the slowest earned peer's last rate in its tier), floored at
        # 0.01, with the wide band -- it still admits near-zero and
        # peer-level outcomes alike.
        median = max(0.01, never_median) if never_median is not None else 0.01
        spread = SPREAD_NEVER_EARNED
    else:
        # No usable read at all for this trophy: flat prior, widest honest band.
        median = 0.5
        spread = SPREAD_CAP

    median = clamp_rate(median)
    spread = min(spread, SPREAD_CAP)
    lg = logit(median)
    qs = [round4(inv_logit(lg + zi * spread)) for zi in z]
    # Rounding can only break monotonicity by a hair; enforce it exactly.
    for i in range(1, len(qs)):
        if qs[i] < qs[i - 1]:
            qs[i] = qs[i - 1]
    return qs


def forecast_case(case: dict, name: str) -> dict:
    trophies = case["trophies"]
    history = case.get("history") or []
    if case.get("levels") and list(case["levels"]) != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")

    release = case.get("game", {}).get("release_date", "2026-11-19")
    try:
        t0 = datetime.fromisoformat(release).replace(tzinfo=timezone.utc)
    except ValueError:
        t0 = datetime(2026, 11, 19, tzinfo=timezone.utc)
    target_s = case.get("target")
    if target_s:
        t_target = parse_time(target_s)
    else:
        t_target = parse_time(case["at"])
    horizon_days = max(case.get("horizon_minutes", 0), 0) / 1440.0
    x_target = math.log1p(max((t_target - t0).total_seconds(), 0.0) / 3600.0)

    # One (x, players, rate) series per trophy, in trophy order.
    series: list[list[tuple[float, float, float | None]]] = [[] for _ in trophies]
    for read in history:
        try:
            t_read = parse_time(read["at"])
        except (KeyError, ValueError):
            continue
        x = math.log1p(max((t_read - t0).total_seconds(), 0.0) / 3600.0)
        n = read.get("players_tracked")
        rates = read.get("rates") or []
        for i in range(len(trophies)):
            r = rates[i] if i < len(rates) else None
            series[i].append((x, n, r))

    # Tier prior for never-earned trophies: the slowest earned peer's
    # last-read rate, per tier (global slowest as fallback).
    last_rates = [
        next((r for _, _, r in reversed(series[i]) if r is not None), None)
        for i in range(len(trophies))
    ]
    tier_min: dict[str, float] = {}
    for i, trophy in enumerate(trophies):
        r = last_rates[i]
        if r is not None and r > 0:
            tier = trophy.get("tier") or ""
            if tier not in tier_min or r < tier_min[tier]:
                tier_min[tier] = r
    global_min = min(tier_min.values()) if tier_min else None

    rows = []
    for i, trophy in enumerate(trophies):
        tier = trophy.get("tier") or ""
        base = tier_min.get(tier, global_min)
        never = TIER_PRIOR_FRACTION * base if base is not None else None
        rows.append({"id": trophy["id"],
                     "q": forecast_trophy(series[i], x_target, horizon_days,
                                          never_median=never)})
    return {"trophies": rows}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
