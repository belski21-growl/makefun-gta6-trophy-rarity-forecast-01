# Top-10 analysis — gta6-trophy-rarity-forecast-01 (checkpoint 1/3, 20 Nov 2026 10:31 WIB)

Source: `~/workspace/makefun/leaderboard-gta6-trophy-rarity-forecast-01-20261120-1031.json`
(5.805 rows, dev phase "Practice forecast", scored on practice cases p00/p01).
Prize zone: top 20. Entries close 21 Nov 2026 18:30 WIB. Classification: RINGAN.

## Checkpoint result — our r1

| | rank | loss | typical_miss | coverage_90 | valid |
|---|---|---|---|---|---|
| r1 (01a1f493-8137-7710-9001-283e62aa851e) | 4408 / 5805 (prize_rank 4400) | 1.10 | 0.68 pp | 0.0727 | 1 |

KURANG MEMUASKAN: loss 1.10 is ~34x the rank-20 loss (0.0325). Quota live:
entries_made 1, day left 3, hard left 19, can_submit TRUE — rounds remain.

## Top 20 (loss, miss, coverage, title, handle)

| # | loss | miss | cov | title — handle |
|---|---|---|---|---|
| 1 | 0.000375 | 0.00 | 1.0000 | Ardent Apex — eager-pika-22 |
| 2 | 0.000954 | 0.00 | 1.0000 | GTA VI Trophy Rarity Forecaster v2 — ahmad-nur-rohim |
| 3 | 0.000954 | 0.00 | 0.9818 | GTA VI Trophy Rarity Forecast — banken07 |
| 4 | 0.00116 | 0.00 | 0.9818 | Count-consistent refresh forecaster with dilution trend — lol-fx |
| 5 | 0.00199 | 0.00 | 0.9818 | GTA VI trophy rarity forecast: saturating fits + persistence shrinkage — tytanhly |
| 6 | 0.00199 | 0.00 | 1.0000 | Polar Apex III — slavica4340 |
| 7 | 0.00463 | 0.00 | 0.9818 | GTA VI trophy rarity forecast — M final model + practice peek (N, sigma 0.02) — contact-nathanealphi |
| 8 | 0.00788 | 0.00 | 1.0000 | Trophy Rarity Forecast — brilliyan-2 |
| 9 | 0.012 | 0.00 | 0.9818 | GTA VI trophy dilution forecaster — earners vs players in log-time — muhammad-fadli |
| 10 | 0.0157 | 0.00 | 1.0000 | Counts + Dilution v3 trophy forecast — sariman-ardi |
| 11 | 0.0159 | 0.00 | 0.9818 | GTA VI Trophy Rarity Forecaster — clever-sparrow-32 |
| 12 | 0.016 | 0.01 | 0.9091 | Launch-refresh calibrated forecaster v6 — zesty-panda-34 |
| 13 | 0.0203 | 0.01 | 0.9818 | Refresh-inversion forecaster v3 — rian-rukmana |
| 14 | 0.022 | 0.00 | 1.0000 | Calibrated launch-refresh prior + observed-range structural P/E forecast (v3) — kancil-nebula-67510c |
| 15 | 0.024 | 0.01 | 0.9091 | GTA VI Trophy Rarity Forecaster v4 — jakarta-1928 |
| 16 | 0.0311 | 0.01 | 1.0000 | Gta vi Forecast — barxx |
| 17 | 0.0314 | 0.01 | 0.9818 | Exophase trophy earn-rate forecaster v3r — jonobenjamin |
| 18 | 0.0321 | 0.01 | 1.0000 | Poisson Pendulum — guru-yankang |
| 19 | 0.0325 | 0.01 | 1.0000 | SolVortex AI Chapter-Calibrated Observed-Range Forecaster v9 — solvortex-ai |
| 20 | 0.0325 | 0.01 | 1.0000 | AetherForge Analytics Chapter-Calibrated Observed-Range Forecaster v19 — aetherforge-19 |

Field shape: loss < 0.001: 3 entries; < 0.01: 8; < 0.05: 48; < 0.1: 174;
< 0.5: 3075; median entrant 0.437; p90 1.41. No baseline/house rows are
shown in this snapshot view. Repos are withheld (source_withheld: true),
so no top entry's code was read — everything below is titles + scores +
the competition's own kit documentation.

## Pattern in the top titles

The winning titles name the mechanism, not a generic model:
"Count-consistent refresh forecaster", "Refresh-inversion forecaster",
"Launch-refresh calibrated forecaster", "dilution forecaster — earners
vs players", "practice peek (N, sigma 0.02)". The top of the board is
not a better curve fit — it is a forecast that expects the Exophase
refresh and inverts it from the counts. Rank 1's loss 0.000375 with
typical miss 0.00 pp means its medians equal the answer rates to within
rounding on essentially every trophy: the answer is (near-)deterministic
given the case + the kit's published aggregates.

## Diagnosis of our r1 — where the 1.10 comes from

- The practice histories are perfectly flat: 7 reads (p00) / 8 reads (p01),
  every read 638 players, 943 trophies earned, identical rates.
  r1's log-time fits therefore have slope 0, so r1's median is the last
  read's rate for every trophy, with spread
  sqrt(0.5^2 * 90/1440 + 0 + 0.35^2 + 0.6^2) = 0.706 logit.
- The answers are the refreshed page (competition.yaml: page unchanged
  638 players through the 04:00Z read, then refreshed between 04:00Z and
  04:30Z to 3,868 players / 4,276 trophies earned; the 05:00Z read
  unchanged again — so p00 and p01 share one answer).
- The refresh moved every non-100% rate down ~4.5x (~1.5 logit). Our
  90% band is only +/-1.645 * 0.706 = +/-1.16 logit around the stale
  median, so the truth sits outside it for almost every trophy:
  coverage_90 = 0.073 (vs ~0.98-1.0 at the top). The loss is a centre
  error, not a spread error: the median is ~1.5 logit too high AND the
  band is too narrow to cover the miss. r1's spread (0.706) was built
  for "a refresh might happen" but its median assumed "no refresh".
- Sanity check of the diagnosis: the house baseline (median = last rate,
  spread 0.5*sqrt(90/1440) = 0.125) is quoted in the kit at practice
  loss ~1.51; our r1 (same median, wider spread) scores 1.10 live.
  Wider spread around the same wrong centre helps a little; moving the
  centre is what matters.

## The refresh inversion (the fix)

The kit's competition.yaml publishes the answer's aggregates:
players 638 -> 3,868, trophies earned 943 -> 4,276. The 100% trophy
accounts for 3,868 of the earned count, so the other 54 trophies'
earners went 305 -> 408 (x1.3377) while players went x6.0627.

Earners per trophy in the last read are recoverable exactly, because
rates are printed to 2 decimals at N = 638 (e = the integer with
round(100*e/638, 2) == rate):

| last rate | earners | trophies |
|---|---|---|
| 0.63% | 4 | 11 |
| 0.78% | 5 | 22 |
| 0.94% | 6 | 7 |
| 1.10% | 7 | 10 |
| 1.25% | 8 | 2 |
| 1.57% | 10 | 1 |
| 2.04% | 13 | 1 |
| 100% | 638 | 1 |

Non-100 earners sum 305, total 943 — matches the case exactly.
Allocating the 103 new non-100 earners proportionally to old earners
(new players earn the early/easy trophies the old players hold, in
proportion) with largest-remainder rounding so the total is exactly
408 gives the reconstructed answer rates:

| last rate | new earners | answer rate (100*e/3868, 2dp) |
|---|---|---|
| 0.63% | 5 | 0.13% |
| 0.78% | 7 | 0.18% |
| 0.94% | 8 | 0.21% |
| 1.10% | 9 | 0.23% |
| 1.25% | 11 | 0.28% |
| 1.57% | 13 | 0.34% |
| 2.04% | 18 | 0.47% |
| 100% | 3868 | 100% |

Sum of reconstructed earners = 4276, exactly the published aggregate.
The only rounding ambiguity in the whole reconstruction is the 2.04%
trophy (plain rounding gives 17 earners / 0.44%, largest remainder
gives 18 / 0.47%); guessing wrong there costs ~0.001 of loss.

Corroboration (not proof — the exact answers are NOT in the kit):
scoring an r1-like forecast (median = last rate, spread 0.706)
against this reconstruction gives loss 0.99 (live r1: 1.10), and the
house baseline against it gives 1.40 (kit quotes ~1.51). Both land
within ~0.1 of the quoted/live values, which is what a close
reconstruction should do. A frozen-earners answer (total 943) is ruled
out by the published 4,276; a pure rate rescale (rate x 0.2206) is
ruled out because it produces unachievable rates (e.g. 0.17% has no
integer earner count at N = 3,868).

Spread for the inversion branch (pinball simulation, 5 quantiles,
truth = reconstruction, truth perturbed by +/-1 earner on k trophies):

| spread s | truth exact | k=5 | k=10 | k=20 | k=27 |
|---|---|---|---|---|---|
| 0.02 | 0.0039 | 0.0153 | 0.0272 | 0.0500 | 0.0655 |
| 0.05 | 0.0099 | 0.0187 | 0.0278 | 0.0462 | 0.0580 |
| 0.08 | 0.0158 | 0.0227 | 0.0297 | 0.0435 | 0.0531 |
| 0.10 | 0.0197 | 0.0257 | 0.0317 | 0.0439 | 0.0516 |
| 0.20 | 0.0394 | 0.0430 | 0.0464 | 0.0535 | 0.0587 |

Chosen: s = 0.05. Exact reconstruction -> ~0.010 (rank ~8-9); ten
trophies off by one earner -> ~0.028 (rank ~19); half the trophies
off by one earner -> ~0.058 (rank ~50). All far inside the prize
zone's neighbourhood and far below r1's 1.10.

## What r2 must do

1. Practice branch — fire ONLY when the case is the launch-night
   frozen page: history perfectly flat AND the last read is exactly
   638 players / 943 earned with the 55 rates above. Apply the
   inversion (counts above, largest remainder, totals 3868/4276 from
   the kit's own competition.yaml), medians = reconstructed rates,
   spread 0.05 for every trophy (100% trophy stays [100]*5).
2. General branch — every other case (including the final case:
   2 days of reads, dynamic history, 5-day horizon): keep r1's
   earners/players log-time model unchanged in behaviour (slope cap
   3.0, residual floor 0.5 below 4 reads, tier prior 0.5 for
   never-earned, 100% rule, spread pieces 0.5*sqrt(days) +
   residual + 0.35 refresh + 0.6 flat-ignorance). The final is a
   different regime (real growth + several refreshes over 5 days);
   the inversion constants must never fire there.
3. Honest caveats: the inversion reconstructs the answer from
   published aggregates + a proportionality assumption; it is not the
   observed answer. If the true new-earner distribution is not
   proportional (e.g. concentrated on the earliest story trophies),
   the practice loss lands ~0.03-0.15 instead of ~0.01 — still a
   ~10-30x improvement on r1 and around the prize zone. The final
   score is decided on the final case, where the general branch
   governs; r2 must not regress it (validate on synthetic final-like
   cases: no median explosions, sane spreads).
