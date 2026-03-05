# FPL Challenge Optimisations

An end-to-end optimisation engine for [FPL Challenge](https://fplchallenge.premierleague.com/) — the Premier League's standalone fantasy football format with weekly rule-twists applied on top of standard FPL scoring.

Each gameweek presents a different challenge (e.g. doubled points for players under 23, bonus points for goal threats, or clean sheet multipliers) and the job of this project is to find the mathematically optimal squad selection pre-gameweek, then retrospectively verify how close that prediction came to the true hindsight-optimal.

The current season structure (`2025-26/`) represents a full rewrite and consolidation of earlier exploratory work done in Jupyter notebooks during the 2023-24 and 2024-25 seasons. It is the canonical structure going forward and is designed to be replicated for each new season with minimal friction.

---

## How it Works

The pipeline has three broad stages: **projection**, **rule adjustment** and **optimisation**. They feed cleanly into one another.

### 1. Expected Points (xPts) Projections

Player projections are sourced from a currently private ML model that generates per-player expected point (xPts) forecasts for each gameweek. The underlying approach uses a range of match context and player performance features to produce these forecasts. The intention is to open this up to the broader FPL community in the future, but for now the outputs are fetched and stored locally as CSVs under `data/projections/`.

Each projection record carries:

- `Predicted_Points` — the base xPts forecast
- `xMins` — expected minutes, used as a scaling factor in downstream calculations
- `Cost` — player price in millions
- `Position` and `Team` metadata

### 2. Challenge Rule Adjustments

This is where the bulk of the modelling lives. Each gameweek has its own rule module under `utils/rules/` that transforms the raw xPts projections to reflect the specific challenge scoring for that week. Because every challenge is different, the techniques employed vary considerably.

**Deterministic multipliers.** The simplest challenges double (or otherwise scale) points for a clearly defined group of players — by team, by position, by price band, or by age. These are applied directly to `Predicted_Points` with no probabilistic component.

**API-augmented player attributes.** Some challenges require player metadata that is not present in the base projections (birth dates, team join dates, position eligibility flags, etc.). These are fetched from the FPL or FPL Challenge bootstrap API, merged into the projections DataFrame, used to derive the relevant multiplier and then dropped before the adjusted DataFrame is passed to the solver.

**Historical rate estimation.** For challenges that award bonus points for repeatable in-game actions (clean sheets, chances created, etc.), per-90 rates are computed from each player's season-to-date statistics via API and scaled by `xMins`. A minimum minutes threshold is applied to guard against small-sample noise:

```
estimated_events = (events_per_90 / 90) * xMins
extra_points     = estimated_events * points_per_event
```

**Probabilistic win weighting with xG distribution.** For challenges where bonus points are contingent on a team winning, assigning the full bonus to a single predicted winner would overfit a single outcome. Instead, the expected bonus is distributed probabilistically across a team's players. Win probabilities are estimated externally, and xG data was sometimes pulled from FBref via soccerdata in the past but is now sourced primarily from the FPL API. Each player's share of the team bonus is weighted by their expected goal contribution relative to the team total.

```
E_goals             = xG_per90 * (xMins / 90)
distribution_factor = E_goals / Team_Total_E_goals
expected_bonus      = P(Win) * bonus_points * distribution_factor
```

Player name reconciliation between the FPL API and external sources is handled via fuzzy string matching (`fuzzywuzzy` / `RapidFuzz`).

**Poisson modelling.** Where a challenge awards a threshold bonus (e.g. bonus points for reaching a minimum number of shot attempts), the relevant per-game statistic is estimated from the player's season history via the FPL Challenge element summary API. The count is modelled as a Poisson process, scaled by projected minutes, and the probability of reaching the threshold is computed analytically. This assigns partial expected credit to players continuously rather than forcing a hard binary decision:

```
lambda         = mean_events_per_appearance * (xMins / 90)
P(threshold)   = P(X >= n | X ~ Poisson(lambda))
expected_bonus = P(threshold) * bonus_points
```

### 3. Linear Programme Optimisation

With projections adjusted for the challenge rules, the optimal squad is found by solving an Integer Linear Programme using PuLP.

The objective is to maximise total predicted points including a doubled captain contribution:

```
maximise  sum(lineup[i] * pts[i]) + sum(captain[i] * pts[i])
```

Subject to constraints loaded from `data/constraints.yaml` per gameweek:

- Total player count
- Exactly one captain, who must be in the lineup
- Position minimums and maximums (goalkeeper, defender, midfielder, forward)
- Maximum players from the same club
- Budget ceiling and floor (where applicable)

The constraint YAML makes it trivial to encode varying challenge formats without touching the solver logic. Constraints for every gameweek in the season are defined upfront.

The solver also supports interactive player banning and forcing at runtime, using fuzzy name matching to resolve player names to their internal IDs.

---

## Hindsight Analysis

Once a gameweek is confirmed and data-checked by the Premier League, `hindsight.py` re-runs the full optimisation using **actual points** rather than projected ones. This produces the true hindsight-optimal lineup — the theoretically best possible selection with perfect information.

The hindsight run pulls live point data from the FPL Challenge API, skips any gameweek already processed, and writes results alongside the predicted optima so the two can be compared directly.

---

## Frontend

A static HTML frontend at `site/index.html` renders the predicted and actual optimal lineups side-by-side for every completed gameweek. It reads from JSON files mirrored into `site/data/` on each solver run and is designed to work without a build step.

Challenge metadata (titles and descriptions) is scraped from the minified FPL Challenge JS bundle using a targeted regular expression, parsed and written to `site/data/{season}/challenges.json` for the frontend to consume.

---

## Project Structure

The structure below was established for the 2025-26 season and is the template for all future seasons. Each new season gets its own top-level directory mirroring this layout. The `utils/` package is shared and season-agnostic; only the per-gameweek runner scripts and rule modules change between seasons.

```
{season}/                       # e.g. 2025-26/
├── gw{n}.py                    # Per-gameweek runner scripts
├── hindsight.py                # Hindsight optimisation across all completed GWs
├── data/
│   ├── config.yaml             # Season config (team ID, JS bundle URL)
│   ├── constraints.yaml        # Per-GW solver constraints
│   ├── projections/            # Saved xPts CSVs per GW
│   ├── lineups/
│   │   ├── predicted_optimal.json
│   │   └── actual_optimal.json
│   └── descriptions/
│       └── challenges.json
└── utils/
    ├── solver.py               # FPLChallengeOptimiser (ILP via PuLP)
    ├── projections.py          # xPts API fetch and DataFrame construction
    ├── data.py                 # JSON persistence and site mirroring
    ├── decisions.py            # Interactive ban/force with fuzzy matching
    ├── challenges.py           # Challenge metadata scraping
    └── rules/
        └── gw{n}.py            # Per-GW projection adjustment logic

site/
├── index.html                  # Static frontend
└── data/
    ├── seasons.json            # Registry of all seasons
    └── {season}/
        ├── predicted_optimal.json
        ├── actual_optimal.json
        └── challenges.json
```

---

## Setup

**Python 3.11+ required.**

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

To run the optimiser for a specific gameweek from the project root:

```bash
python {season}/gw{n}.py
```

To run the hindsight pass across all completed gameweeks:

```bash
python {season}/hindsight.py
```

---

## Key Dependencies

| Package | Purpose |
|---|---|
| `pulp` | Integer linear programming |
| `pandas` / `numpy` | Data manipulation and numerical computation |
| `requests` | FPL and FPL Challenge API calls |
| `soccerdata` | FBref xG and player stats via structured scraping |
| `fuzzywuzzy` / `RapidFuzz` | Player name reconciliation across data sources |
| `scipy` | Supporting statistical computation |
| `pyyaml` | Constraint and config loading |

---

## Historical Notebooks

The `2023-24/` and `2024-25/` directories contain Jupyter notebooks from earlier seasons. These predate the structured Python module layout introduced in 2025-26 and serve as an archive of early exploratory work. The modelling logic developed in those notebooks informed the techniques now implemented in the `utils/rules/` modules.
