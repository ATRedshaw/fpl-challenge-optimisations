import os
import pandas as pd
import yaml
from utils.projections import generate_projections
from utils.rules import gw2_rules
from utils.decisions import run_ban_force
from utils.solver import FPLChallengeOptimiser
from utils.data import save_projections, save_optimal_prediction

if __name__ == "__main__":
    FILE_PATH = os.path.abspath(__file__)
    SEASON = FILE_PATH.split('/')[-2]
    GAMEWEEK = int(FILE_PATH.split('/')[-1].replace('gw','').replace('.py',''))
    print('\nRunning GW', GAMEWEEK, 'for', SEASON)

    # Load constraints from YAML
    # ==================================================================
    constraints_path = os.path.join(SEASON, 'data', 'constraints.yaml')
    with open(constraints_path, 'r') as f:
        constraints = yaml.safe_load(f)
    try:
        constraints = constraints[f'GW{GAMEWEEK}']
    except:
        print(f"Constraints not found for GW{GAMEWEEK}. Terminating.")
        exit()

    print(f"Constraints loaded from {constraints_path}")

    # Load projections and make gameweek changes
    # ==================================================================
    try:
        projections = generate_projections(GAMEWEEK)
        projections = gw2_rules(projections)
    except Exception as e:
        print(f"Error generating projections. Loading saved predictions.")
        try:
            saved_path = os.path.join(SEASON, 'data', 'projections', f'gw{GAMEWEEK}.csv')
            projections = pd.read_csv(saved_path)
        except Exception as e:
            print(f"Error loading saved projections. Terminating.")
            exit()

    print(f"Projections generated for GW{GAMEWEEK}")

    # Enforce player banning/forcing
    # ===================================================================
    ban_ids, force_ids = run_ban_force(projections)
    
    # Solver
    # ===================================================================
    solver = FPLChallengeOptimiser(GAMEWEEK, projections)
    solver.setup_problem(f"fpl-{SEASON.replace('-', '')}-gw{GAMEWEEK}-challenge")

    solver.exclude_players_constraint(ban_ids)
    solver.force_players_constraint(force_ids)

    solver.total_players_constraint(constraints['total_players'])
    solver.captain_count_constraint(constraints['captain_count'])
    solver.position_count_constraints(constraints['position_constraints'])
    solver.max_players_from_same_team_constraint(constraints['max_per_team'])
    
    # Solve and print results
    # ===================================================================
    solver.solve()
    solver.print_players_by_position()

    # Save projections
    # ===================================================================
    save_projections(projections, SEASON, GAMEWEEK)
    save_optimal_prediction(solver.selected_players, SEASON, GAMEWEEK)