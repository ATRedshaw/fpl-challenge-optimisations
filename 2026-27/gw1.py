"""Run the 2026-27 Gameweek 1 FPL Challenge optimisation."""

import sys
from pathlib import Path

import pandas as pd
import yaml
from hindsight import run_hindsight
from utils.challenges import update_challenges
from utils.constraints import update_constraints
from utils.data import save_optimal_prediction, save_projections
from utils.decisions import run_ban_force
from utils.projections import generate_projections
from utils.rules.gw1 import gw1_rules
from utils.solver import FPLChallengeOptimiser

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    season_root = Path(__file__).resolve().parent
    season = season_root.name
    gameweek = int(Path(__file__).stem.removeprefix("gw"))
    print(f"\nRunning GW{gameweek} for {season}")

    # Update challenge descriptions and constraints
    # ==================================================================
    update_challenges()
    update_constraints(gameweek)

    # Load constraints from YAML
    # ==================================================================
    constraints_path = season_root / "data" / "constraints.yaml"
    with constraints_path.open(encoding="utf-8") as constraints_file:
        all_constraints = yaml.safe_load(constraints_file) or {}
    constraints = all_constraints.get(f"GW{gameweek}")
    if not constraints:
        raise KeyError(f"Constraints not found for GW{gameweek}: {constraints_path}")
    print(f"Constraints loaded from {constraints_path.relative_to(season_root.parent)}")

    # Load projections and make gameweek changes
    # ==================================================================
    try:
        projections = gw1_rules(generate_projections(gameweek))
    except Exception as error:
        print(f"Live projection generation failed: {error}")
        saved_path = season_root / "data" / "projections" / f"gw{gameweek}.csv"
        if not saved_path.exists():
            raise
        print(f"Loading the last saved projections from {saved_path}")
        projections = pd.read_csv(saved_path)
    print(f"Projections generated for GW{gameweek}")

    # Enforce player banning/forcing
    # ==================================================================
    ban_indices, force_indices = run_ban_force(projections)

    # Solver
    # ==================================================================
    solver = FPLChallengeOptimiser(gameweek, projections)
    solver.setup_problem(f"fpl-{season.replace('-', '')}-gw{gameweek}-challenge")
    solver.exclude_players_constraint(ban_indices)
    solver.force_players_constraint(force_indices)
    solver.total_players_constraint(constraints["total_players"])
    solver.position_count_constraints(constraints["position_constraints"])
    solver.max_players_from_same_team_constraint(constraints["max_per_team"])
    if constraints.get("budget_max") is not None:
        solver.budget_constraint(
            constraints["budget_max"], constraints.get("budget_min", 0)
        )

    # Solve and print results
    # ==================================================================
    solver.solve()
    solver.print_players_by_position()

    # Save projections
    # ==================================================================
    save_projections(projections, season, gameweek)
    prediction_saved = save_optimal_prediction(
        solver.selected_players, season, gameweek
    )

    # Run hindsight for completed gameweeks
    # ==================================================================
    if prediction_saved:
        print("\nChecking for completed gameweeks to process...")
        try:
            run_hindsight(season_root)
        except Exception as error:
            print(
                "Prediction saved, but automatic hindsight processing failed: "
                f"{error}"
            )
