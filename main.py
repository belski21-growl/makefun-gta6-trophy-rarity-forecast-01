# SPDX-License-Identifier: MIT
"""Week-one earn-rate forecast for every GTA VI trophy on Exophase (PS5).

Usage: point MAKEFUN_INPUT_DIR at a directory of ``*.in`` case files and
MAKEFUN_OUTPUT_DIR at where the ``*.out`` forecasts go, then run
``python3 main.py``. One output file per case, in case-name order.
Python 3.13, standard library only; no network, no randomness, no clock
reads, so the same case always yields the same bytes.

How the forecast is built
--------------------------
A trophy's earn rate is earners divided by players tracked, and the two
halves drift for different reasons: the denominator only grows as more
buyers sync their profiles (diluting every rate), while the numerator
only grows as players work through the game (lifting rates). Each half
is therefore projected on its own, as a straight line of the log count
against log(1 + hours since the release day began), fitted by least
squares over all reads in the case. The median is the ratio of the two
projections at the target, clipped to [0.01, 99.99]. Slopes are floored
at zero (neither count can shrink; apparent dips are the page's
two-decimal rounding) and capped at 3.0, a ceiling that only ever binds
on degenerate fits -- a trophy first earned in the final two reads,
ten minutes apart, would otherwise extrapolate to a near-100% median
from two rounding steps. Fits resting on fewer than four positive
reads get their residual floored at 0.5 for the same reason: a line
through two points fits them exactly, which would pretend a slope
estimated from almost nothing is precise.

How wide the bands are
-----------------------
Quantiles sit on the logit scale around the median, at the usual normal
z-scores, with a spread that adds up independent doubts in quadrature:
a random walk of 0.5 per root-day of horizon (the house baseline's
term), the earners fit's residual (capped at 1.0), a flat 0.35 for a
single Exophase refresh jump, and a 0.6 ignorance premium that fires
only when the history is perfectly flat -- every read identical -- so
the data carries no dynamic signal at all. The launch-night refresh is
the reason the refresh term exists: the page sat frozen at 638 players
from 23:48Z to 04:00Z, then jumped to 3,868 at 04:30Z; trophies earned
went 943 to 4,276, but the single 100% trophy alone accounts for 3,868
of those, so the other 54 trophies' earners grew only about 1.5x
against 6.1x player growth -- their rates fell roughly fourfold, about
1.4 logit units. A trophy the page lists at 100% stays 100% at every
quantile. A trophy never earned anywhere in the history takes half the
slowest earned peer's last rate in its own tier (slowest earned trophy
overall if the tier has no earned peer), floored at 0.01, with a wide
1.8 spread: by selection it is slower than its slowest earned peer,
but not infinitely slower. A trophy with no usable read at all falls
back to a 0.5% median at the widest spread.

Output: ``{"trophies": [{"id": n, "q": [q05, q25, q50, q75, q95]}, ...]}``,
quantiles rounded to four decimals, half up, non-decreasing, each in
[0, 100].
"""

import json, math, os, sys
import pathlib
from datetime import datetime as Timestamp, timezone as UTCZone

# The grader runs with -P, which leaves /bot off sys.path; restore it so a
# helper shipped beside this file would still import. This entry is one file.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

INPUT = pathlib.Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT = pathlib.Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

Q_LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)

# Logit spread pieces (see the module docstring for why each is there).
RW_VOL = 0.5            # random-walk volatility, per root-day of horizon
REFRESH_SIGMA = 0.35    # one Exophase refresh jump
FLAT_SIGMA = 0.6        # ignorance premium for a perfectly flat history
NEVER_SPREAD = 1.8      # spread for a trophy never earned in the history
TIER_SHARE = 0.5        # never-earned median as a share of slowest earned peer
SPREAD_MAX = 2.5        # hard cap on the logit spread
SLOPE_MAX = 3.0         # hard cap on a fitted log-time slope
FEW_READS = 4           # fits from fewer positive reads get a residual floor
FEW_RESID_FLOOR = 0.5   # that floor

# Acklam's rational approximation for the standard normal quantile.
_ACKLAM_A = [
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285984469534e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
]
_ACKLAM_B = [
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
]
_ACKLAM_C = [
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
]
_ACKLAM_D = [
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
]


def _horner(coeffs, value):
    total = 0.0
    for coeff in coeffs:
        total = total * value + coeff
    return total


def _norm_quantile(prob):
    """Standard normal quantile by Acklam's rational approximation."""
    if prob < 0.02425:
        q = math.sqrt(-2.0 * math.log(prob))
        return _horner(_ACKLAM_C, q) / _horner(_ACKLAM_D + [1.0], q)
    if prob > 0.97575:
        q = math.sqrt(-2.0 * math.log(1.0 - prob))
        return -(_horner(_ACKLAM_C, q) / _horner(_ACKLAM_D + [1.0], q))
    q = prob - 0.5
    return _horner(_ACKLAM_A, q * q) * q / _horner(_ACKLAM_B + [1.0], q * q)


def _round4(value):
    """Round to 4 decimals, half up, the way JavaScript Math.round does;
    whole numbers come back as int so json writes 100, not 100.0."""
    scaled = value * 10000
    base = math.floor(scaled)
    if scaled - base >= 0.5:
        base += 1
    rounded = base / 10000
    return int(rounded) if rounded.is_integer() else rounded


def _clamp_pct(pct):
    return min(99.99, max(0.01, pct))


def _to_logit(pct):
    bounded = _clamp_pct(pct)
    return math.log(bounded / (100.0 - bounded))


def _from_logit(lg):
    if lg < 0:
        grown = math.exp(lg)
        return 100.0 * grown / (1.0 + grown)
    return 100.0 / (1.0 + math.exp(-lg))


def _read_time(text):
    return Timestamp.fromisoformat(text.replace("Z", "+00:00"))


def _fit_log_line(xs, ys):
    """Least squares y = intercept + slope*x; also the residual spread.

    Returns (intercept, slope, residual-std). A degenerate x (all equal)
    gives slope 0 and the mean as intercept."""
    count = len(xs)
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    spread_xx = sum((x - mean_x) ** 2 for x in xs)
    if spread_xx <= 0:
        resid = math.sqrt(sum((y - mean_y) ** 2 for y in ys) / count) if count else 0.0
        return mean_y, 0.0, resid
    cross = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = cross / spread_xx
    intercept = mean_y - slope * mean_x
    dof = max(count - 2, 1)
    resid = math.sqrt(sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys)) / dof)
    return intercept, slope, resid


def _log_hours(moment, origin):
    seconds = max((moment - origin).total_seconds(), 0.0)
    return math.log1p(seconds / 3600.0)


def _players_log_at(observations, x_target):
    """Projected log players at the target, never below the last read."""
    xs = []
    ys = []
    for x, players, _rate in observations:
        if players and players > 0:
            xs.append(x)
            ys.append(math.log(players))
    if len(xs) >= 2:
        intercept, slope, _resid = _fit_log_line(xs, ys)
        slope = min(max(0.0, slope), SLOPE_MAX)
        projected = intercept + slope * x_target
    elif xs:
        projected = ys[-1]
    else:
        projected = 0.0
    latest = None
    for _x, players, _rate in reversed(observations):
        if players and players > 0:
            latest = players
            break
    if latest is not None:
        projected = max(projected, math.log(latest))
    return projected


def _earners_forecast(observations, players_log, x_target, horizon_days, never_median):
    """Median and logit spread from the earners half; see module docstring.

    observations: (x, players_tracked, rate-or-None) per read, oldest first.
    never_median: tier-prior median for a never-earned trophy, or None."""
    xs = []
    ys = []
    for x, players, rate in observations:
        if rate is not None and players and rate > 0:
            xs.append(x)
            ys.append(math.log(rate * players / 100.0))
    walk = RW_VOL * math.sqrt(horizon_days)
    if len(xs) >= 2:
        intercept, slope, resid = _fit_log_line(xs, ys)
        slope = min(max(0.0, slope), SLOPE_MAX)
        median = 100.0 * math.exp(intercept + slope * x_target - players_log)
        if len(xs) < FEW_READS:
            # A line through 2-3 points fits them (near-)exactly, so the
            # measured residual understates the slope's uncertainty.
            resid = max(resid, FEW_RESID_FLOOR)
        spread = math.sqrt(walk * walk + min(resid, 1.0) ** 2 + REFRESH_SIGMA ** 2)
        if len(set(ys)) <= 1:
            # Perfectly flat history: no dynamic signal at all (launch night).
            spread = math.sqrt(spread * spread + FLAT_SIGMA ** 2)
        return median, spread
    if len(xs) == 1:
        # One positive read: earners flat at that count, players as fitted.
        # A single read carries no dynamic signal either.
        median = 100.0 * math.exp(ys[0] - players_log)
        spread = math.sqrt(walk * walk + REFRESH_SIGMA ** 2 + FLAT_SIGMA ** 2)
        return median, spread
    last = None
    for _x, _players, rate in reversed(observations):
        if rate is not None:
            last = rate
            break
    if last is not None:
        # Never earned, but the page lists a (zero) rate: use the tier prior
        # (half the slowest earned peer's last rate in its tier), floored at
        # 0.01, with the wide band -- it still admits near-zero and
        # peer-level outcomes alike.
        if never_median is None:
            median = 0.01
        else:
            median = max(0.01, never_median)
        return median, NEVER_SPREAD
    # No usable read at all for this trophy: flat prior, widest honest band.
    return 0.5, SPREAD_MAX


def _quantiles_from(median, spread):
    centre = _to_logit(_clamp_pct(median))
    capped = min(spread, SPREAD_MAX)
    out = []
    for level in Q_LEVELS:
        out.append(_round4(_from_logit(centre + _norm_quantile(level) * capped)))
    # Rounding can only break monotonicity by a hair; enforce it exactly.
    for idx in range(1, len(out)):
        if out[idx] < out[idx - 1]:
            out[idx] = out[idx - 1]
    return out


def _forecast_one(observations, x_target, horizon_days, never_median):
    """The five quantiles for one trophy."""
    players_log = _players_log_at(observations, x_target)
    last_rate = None
    for _x, _players, rate in reversed(observations):
        if rate is not None:
            last_rate = rate
            break
    if last_rate is not None and last_rate >= 100.0:
        return [100] * 5
    median, spread = _earners_forecast(
        observations, players_log, x_target, horizon_days, never_median)
    return _quantiles_from(median, spread)


def _forecast_case(case, label):
    trophies, reads = case["trophies"], case.get("history") or []
    if case.get("levels") and list(case["levels"]) != list(Q_LEVELS):
        raise ValueError(label + " asks for levels " + repr(case["levels"]))

    release_text = case.get("game", {}).get("release_date", "2026-11-19")
    try:
        origin = Timestamp.fromisoformat(release_text).replace(tzinfo=UTCZone.utc)
    except ValueError:
        origin = Timestamp(2026, 11, 19, tzinfo=UTCZone.utc)
    target_text = case.get("target")
    if target_text:
        moment_target = _read_time(target_text)
    else:
        moment_target = _read_time(case["at"])
    horizon = max(case.get("horizon_minutes", 0), 0) / 1440.0
    x_target = _log_hours(moment_target, origin)

    # One (x, players, rate) observation list per trophy, in trophy order.
    per_trophy = [[] for _ in trophies]
    for read in reads:
        try:
            moment = _read_time(read["at"])
        except (KeyError, ValueError):
            continue
        x = _log_hours(moment, origin)
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
        never = TIER_SHARE * peer if peer is not None else None
        rows.append({"id": trophy["id"],
                     "q": _forecast_one(per_trophy[idx], x_target, horizon, never)})
    result = {}
    result["trophies"] = rows
    return result


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT.glob("*.in")):
        data = json.loads(path.read_text(encoding="utf-8"))
        result = _forecast_case(data, path.name)
        out_path = OUTPUT / (path.stem + ".out")
        out_path.write_text(
            json.dumps(result, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
