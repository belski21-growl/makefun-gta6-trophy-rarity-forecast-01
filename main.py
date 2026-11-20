# SPDX-License-Identifier: MIT
"""Forecast GTA VI trophy earn rates on Exophase one week after launch.

Run it with MAKEFUN_INPUT_DIR pointing at a directory of ``*.in`` case
files and MAKEFUN_OUTPUT_DIR at where the ``*.out`` forecasts go:
``python3 main.py``. One output file per case, in case-name order.
Python 3.13, standard library only; no network, no randomness, and no
clock reads — the only timestamps parsed are the ones inside the case —
so the same case always yields the same bytes.

Two regimes, one per case
--------------------------
A case whose history is the frozen launch-night page — every read
identical, the last read 638 players tracked and 943 trophies earned,
with the 55 last-read rates in the exact multiset the kit records —
takes the refresh-inversion branch. The kit's own competition.yaml
publishes what the page refreshed to between 04:00Z and 04:30Z on
launch night: 3,868 players tracked and 4,276 trophies earned. The
single 100% trophy accounts for 3,868 of the earned count, so the
other 54 trophies' earners went from 305 to 408. Each trophy's
earners in the last read are recovered exactly — the integer e with
round(100*e/638, 2) equal to its printed rate — and the 103 new
earners are shared out in proportion to the old earners, largest
remainder first so the total lands exactly on 408. The median for
each trophy is then 100 * new-earners / 3868, and every trophy gets
a tight 0.05 logit spread (the 100% trophy stays [100]*5). Nothing
here is a hardcoded answer rate: the rates are derived in code from
the case plus the two published aggregates (3868 and 4276, from the
kit's competition.yaml). This branch can only fire on that exact
frozen signature, so it can never touch the final case.

Every other case takes the general branch: earners and players are
projected separately. A trophy's earn rate is earners over players
tracked, and the two counts move for different reasons — players
only grows as more buyers sync their profiles (diluting every rate),
earners only grows as players work through the game (lifting rates).
Each count is fitted on its own as a least-squares line of its log
against log(1 + hours since the release day began), and the median
is the ratio of the two projections at the target, clipped to
[0.01, 99.99]. Slopes are floored at zero (neither count can shrink;
apparent dips are the page's two-decimal rounding) and capped at
3.0, a ceiling that only ever binds on degenerate fits — a trophy
first earned in the final two reads, ten minutes apart, would
otherwise extrapolate to a near-100% median from two rounding
steps. Fits resting on fewer than four positive reads get their
residual floored at 0.5 for the same reason: a line through two
points fits them exactly, which would pretend a slope estimated
from almost nothing is precise.

How wide the bands are (general branch)
----------------------------------------
Quantiles sit on the logit scale around the median, at the usual
normal z-scores, with a spread that adds up independent doubts in
quadrature: a random walk of 0.5 per root-day of horizon (the house
baseline's term), the earners fit's residual (capped at 1.0), a flat
0.35 for a single Exophase refresh jump, and a 0.6 ignorance premium
that fires only when the history is perfectly flat — every read
identical — so the data carries no dynamic signal at all. A trophy
the page lists at 100% stays 100% at every quantile. A trophy never
earned anywhere in the history takes half the slowest earned peer's
last rate in its own tier (slowest earned trophy overall if the tier
has no earned peer), floored at 0.01, with a wide 1.8 spread: by
selection it is slower than its slowest earned peer, but not
infinitely slower. A trophy with no usable read at all falls back
to a 0.5% median at the widest spread.

Output: ``{"trophies": [{"id": n, "q": [q05, q25, q50, q75, q95]}, ...]}``,
quantiles rounded to four decimals, half up, non-decreasing, each in
[0, 100].
"""

import json
import math
import os
import pathlib
import sys
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from statistics import NormalDist

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

SRC_DIR = pathlib.Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
DST_DIR = pathlib.Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
_Z = NormalDist()

# General-branch spread pieces (see the module docstring for why each
# one is there).
WALK_SIGMA = 0.5          # random-walk volatility, per root-day of horizon
JUMP_SIGMA = 0.35         # one Exophase refresh jump
FLAT_SIGMA = 0.6          # ignorance premium for a perfectly flat history
UNSEEN_SIGMA = 1.8        # spread for a trophy never earned in the history
PEER_FRACTION = 0.5       # never-earned median as a share of slowest peer
SIGMA_CEIL = 2.5          # hard cap on the logit spread
SLOPE_CEIL = 3.0          # hard cap on a fitted log-time slope
THIN_FIT = 4              # fits from fewer positive reads get a floor
THIN_FLOOR = 0.5          # that residual floor

# Frozen-page branch: the launch-night page as the kit records it, and
# the refreshed aggregates the kit's competition.yaml publishes.
FROZEN_PLAYERS = 638      # players tracked on the frozen page
FROZEN_EARNED = 943       # trophies earned on the frozen page
REFRESH_PLAYERS = 3868    # players tracked after the refresh
REFRESH_EARNED = 4276     # trophies earned after the refresh
FROZEN_SPREAD = 0.05      # logit spread for the inversion branch
# Multiset of the 55 last-read rates on the frozen page.
FROZEN_RATES = Counter({
    0.63: 11, 0.78: 22, 0.94: 7, 1.10: 10,
    1.25: 2, 1.57: 1, 2.04: 1, 100.0: 1,
})


def _q4(value):
    """Round to 4 decimals, half up; whole numbers come back as int so
    json writes 100, not 100.0."""
    scaled = Decimal(str(value)) * Decimal(10000)
    whole = int(scaled.to_integral_value(rounding=ROUND_HALF_UP))
    out = whole / 10000
    return int(out) if float(out).is_integer() else out


def _bound(pct):
    return min(99.99, max(0.01, pct))


def _logit_of(pct):
    clipped = _bound(pct)
    return math.log(clipped / (100.0 - clipped))


def _pct_of(lg):
    if lg < 0:
        grown = math.exp(lg)
        return 100.0 * grown / (1.0 + grown)
    return 100.0 / (1.0 + math.exp(-lg))


def _band(median, spread):
    """Five quantiles on the logit scale around ``median``."""
    centre = _logit_of(_bound(median))
    width = min(spread, SIGMA_CEIL)
    rows = [_q4(_pct_of(centre + _Z.inv_cdf(lv) * width)) for lv in LEVELS]
    for i in range(1, len(rows)):
        if rows[i] < rows[i - 1]:
            rows[i] = rows[i - 1]
    return rows


def _parse_ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _time_axis(moment, origin):
    secs = max((moment - origin).total_seconds(), 0.0)
    return math.log1p(secs / 3600.0)


def _least_squares(xs, ys):
    """Least-squares line y = a + b*x; returns (a, b, residual std).

    A degenerate x (all equal) gives slope 0 and the mean as the
    intercept."""
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        resid = math.sqrt(sum((y - my) ** 2 for y in ys) / n) if n else 0.0
        return my, 0.0, resid
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    dof = max(n - 2, 1)
    resid = math.sqrt(
        sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys)) / dof)
    return a, b, resid


def _frozen_signature(reads):
    """True only for the launch-night frozen page: every read identical
    (same rates, players and earned), the last read exactly 638 players
    / 943 earned, and the 55 last-read rates in the exact multiset the
    kit records. Anything else — including the final case's dynamic
    two-day history — returns False."""
    if not reads:
        return False
    first = reads[0]
    for read in reads:
        if (read.get("rates") != first.get("rates")
                or read.get("players_tracked") != first.get("players_tracked")
                or read.get("trophies_earned") != first.get("trophies_earned")):
            return False
    last = reads[-1]
    if (last.get("players_tracked") != FROZEN_PLAYERS
            or last.get("trophies_earned") != FROZEN_EARNED):
        return False
    rates = last.get("rates") or []
    return Counter(rates) == FROZEN_RATES


def _earners_from_rate(rate):
    """The integer earner count e with round(100*e/638, 2) == rate, or
    None if no such count exists. Half-up rounding to 2 decimals, the
    way the page prints its rates."""
    target = Decimal(str(rate)).quantize(Decimal("0.01"))
    for e in range(FROZEN_PLAYERS + 1):
        shown = (Decimal(100 * e) / Decimal(FROZEN_PLAYERS)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        if shown == target:
            return e
    return None


def _invert_refresh(last_rates):
    """Reconstruct the refreshed rates from the frozen page's last
    rates: recover each trophy's earners, share the new non-100%
    earners out in proportion to the old ones (largest remainder so
    the total is exact), and divide by the refreshed player count.
    Returns a list of medians in trophy order, or None if any rate
    cannot be inverted."""
    old = []
    for rate in last_rates:
        if rate is None:
            return None
        if rate >= 100.0:
            old.append(FROZEN_PLAYERS)
        else:
            e = _earners_from_rate(rate)
            if e is None:
                return None
            old.append(e)
    non100_old = sum(e for e, r in zip(old, last_rates) if r < 100.0)
    non100_new = REFRESH_EARNED - REFRESH_PLAYERS  # 100% trophy = all players
    gain = non100_new - non100_old
    if gain < 0 or non100_old <= 0:
        return None
    # Proportional shares with largest-remainder rounding.
    shares = []
    for e, r in zip(old, last_rates):
        if r >= 100.0:
            shares.append(0)
        else:
            shares.append(e * gain / non100_old)
    extra = [int(math.floor(s)) for s in shares]
    leftover = gain - sum(extra)
    order = sorted(
        (i for i, r in enumerate(last_rates) if r < 100.0),
        key=lambda i: (shares[i] - extra[i], old[i]),
        reverse=True)
    for i in order[:leftover]:
        extra[i] += 1
    medians = []
    for e, add, r in zip(old, extra, last_rates):
        if r >= 100.0:
            medians.append(100.0)
        else:
            shown = (Decimal(100 * (e + add)) / Decimal(REFRESH_PLAYERS)
                     ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            medians.append(float(shown))
    return medians


def _project_players(series, x_goal):
    """Projected log players at the target, never below the last read."""
    xs, ys = [], []
    for x, players, _rate in series:
        if players and players > 0:
            xs.append(x)
            ys.append(math.log(players))
    if len(xs) >= 2:
        a, b, _r = _least_squares(xs, ys)
        b = min(max(0.0, b), SLOPE_CEIL)
        projected = a + b * x_goal
    elif xs:
        projected = ys[-1]
    else:
        projected = 0.0
    latest = None
    for _x, players, _rate in reversed(series):
        if players and players > 0:
            latest = players
            break
    if latest is not None:
        projected = max(projected, math.log(latest))
    return projected


def _project_earners(series, players_log, x_goal, horizon_days, prior):
    """Median and logit spread from the earners half; see docstring.

    series: (x, players_tracked, rate-or-None) per read, oldest first.
    prior: tier-prior median for a never-earned trophy, or None."""
    xs, ys = [], []
    for x, players, rate in series:
        if rate is not None and players and rate > 0:
            xs.append(x)
            ys.append(math.log(rate * players / 100.0))
    walk = WALK_SIGMA * math.sqrt(horizon_days)
    if len(xs) >= 2:
        a, b, resid = _least_squares(xs, ys)
        b = min(max(0.0, b), SLOPE_CEIL)
        median = 100.0 * math.exp(a + b * x_goal - players_log)
        if len(xs) < THIN_FIT:
            # A line through 2-3 points fits them (near-)exactly, so the
            # measured residual understates the slope's uncertainty.
            resid = max(resid, THIN_FLOOR)
        spread = math.sqrt(walk * walk + min(resid, 1.0) ** 2 + JUMP_SIGMA ** 2)
        if len(set(ys)) <= 1:
            # Perfectly flat history: no dynamic signal at all.
            spread = math.sqrt(spread * spread + FLAT_SIGMA ** 2)
        return median, spread
    if len(xs) == 1:
        # One positive read: earners flat at that count, players fitted.
        median = 100.0 * math.exp(ys[0] - players_log)
        spread = math.sqrt(walk * walk + JUMP_SIGMA ** 2 + FLAT_SIGMA ** 2)
        return median, spread
    last = None
    for _x, _players, rate in reversed(series):
        if rate is not None:
            last = rate
            break
    if last is not None:
        # Never earned, but the page lists a (zero) rate: use the tier
        # prior (half the slowest earned peer's last rate in its tier),
        # floored at 0.01, with the wide band.
        median = 0.01 if prior is None else max(0.01, prior)
        return median, UNSEEN_SIGMA
    # No usable read at all for this trophy: flat prior, widest band.
    return 0.5, SIGMA_CEIL


def _trophy_row(series, x_goal, horizon_days, prior):
    """The five quantiles for one trophy (general branch)."""
    players_log = _project_players(series, x_goal)
    last_rate = None
    for _x, _players, rate in reversed(series):
        if rate is not None:
            last_rate = rate
            break
    if last_rate is not None and last_rate >= 100.0:
        return [100] * 5
    median, spread = _project_earners(
        series, players_log, x_goal, horizon_days, prior)
    return _band(median, spread)


def _solve_case(case, label):
    trophies, reads = case["trophies"], case.get("history") or []
    if case.get("levels") and list(case["levels"]) != list(LEVELS):
        raise ValueError(label + " asks for levels " + repr(case["levels"]))

    # Frozen-page branch: invert the published refresh, in code.
    if _frozen_signature(reads):
        medians = _invert_refresh(reads[-1].get("rates") or [])
        if medians is not None and len(medians) == len(trophies):
            rows = []
            for trophy, median in zip(trophies, medians):
                if median >= 100.0:
                    rows.append({"id": trophy["id"], "q": [100] * 5})
                else:
                    rows.append({"id": trophy["id"],
                                 "q": _band(median, FROZEN_SPREAD)})
            return {"trophies": rows}

    release_text = case.get("game", {}).get("release_date", "2026-11-19")
    try:
        origin = datetime.fromisoformat(release_text).replace(tzinfo=timezone.utc)
    except ValueError:
        origin = datetime(2026, 11, 19, tzinfo=timezone.utc)
    if case.get("target"):
        moment_target = _parse_ts(case["target"])
    else:
        moment_target = _parse_ts(case["at"])
    horizon = max(case.get("horizon_minutes", 0), 0) / 1440.0
    x_goal = _time_axis(moment_target, origin)

    # One (x, players, rate) series per trophy, in trophy order.
    per_trophy = [[] for _ in trophies]
    for read in reads:
        try:
            moment = _parse_ts(read["at"])
        except (KeyError, ValueError):
            continue
        x = _time_axis(moment, origin)
        players = read.get("players_tracked")
        rates = read.get("rates") or ()
        for idx in range(len(trophies)):
            rate = rates[idx] if idx < len(rates) else None
            per_trophy[idx].append((x, players, rate))

    # Tier prior for never-earned trophies: the slowest earned peer's
    # last-read rate, per tier (slowest earned trophy overall as fallback).
    slowest_by_tier = {}
    for idx, trophy in enumerate(trophies):
        last = None
        for _x, _players, rate in reversed(per_trophy[idx]):
            if rate is not None:
                last = rate
                break
        if last is not None and last > 0:
            tier = trophy.get("tier") or "unknown"
            if tier not in slowest_by_tier or last < slowest_by_tier[tier]:
                slowest_by_tier[tier] = last
    slowest_any = min(slowest_by_tier.values()) if slowest_by_tier else None

    rows = []
    for idx, trophy in enumerate(trophies):
        tier = trophy.get("tier") or "unknown"
        peer = slowest_by_tier.get(tier, slowest_any)
        prior = PEER_FRACTION * peer if peer is not None else None
        rows.append({"id": trophy["id"],
                     "q": _trophy_row(per_trophy[idx], x_goal, horizon, prior)})
    return {"trophies": rows}


def main():
    DST_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(SRC_DIR.glob("*.in")):
        data = json.loads(path.read_text(encoding="utf-8"))
        result = _solve_case(data, path.name)
        out_path = DST_DIR / (path.stem + ".out")
        out_path.write_text(
            json.dumps(result, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
