import pulp as plp
from pulp import PULP_CBC_CMD
from collections import defaultdict
import pandas as pd

class FPLChallengeOptimiser:
    def __init__(self, gameweek, projections_data):
        self.gameweek = gameweek
        self.projections_data = projections_data

    def setup_problem(self, problem_name, objective=plp.LpMaximize):
        self.player_ids = self.projections_data['ID'].tolist()
        self.player_count = len(self.player_ids)

        print(f"Setting up problem with name: {problem_name}.")
        self.model = plp.LpProblem(problem_name, objective)

        # Setup the decision variables
        self.lineup = [plp.LpVariable(f"lineup_{i}", lowBound=0, upBound=1, cat="Integer") for i in self.player_ids]
        self.captain = [plp.LpVariable(f"captain_{i}", lowBound=0, upBound=1, cat="Integer") for i in self.player_ids]
    
        # Set the objective function (the number of points scored by the team, with captain's points doubled)
        self.model +=  plp.lpSum([self.lineup[i] * self.projections_data.loc[i, 'Predicted_Points'] for i in range(self.player_count)]) + \
                    plp.lpSum([self.captain[i] * self.projections_data.loc[i, 'Predicted_Points'] for i in range(self.player_count)])

    def total_players_constraint(self, total_players):
        self.model += plp.lpSum(self.lineup) == total_players
    
    def exclude_players_constraint(self, exclude_id_list):
        for id in exclude_id_list:
            self.model += self.lineup[id] == 0

    def force_players_constraint(self, force_id_list):
        for id in force_id_list:
            self.model += self.lineup[id] == 1
    
    def captain_count_constraint(self, captain_count):
        self.model += plp.lpSum(self.captain) == captain_count

        # Constraint that all captains must be in the lineup
        for i in range(self.player_count):
            self.model += self.captain[i] <= self.lineup[i]

    def position_count_constraints(self, position_counts):
        for position, counts in position_counts.items():
            min_count = counts.get("min_count")
            max_count = counts.get("max_count")

            # Apply minimum constraint if specified
            if min_count is not None:
                self.model += plp.lpSum(
                    [self.lineup[i] for i in range(self.player_count) if self.projections_data.loc[i, 'Position'] == position]
                ) >= min_count

            # Apply maximum constraint if specified
            if max_count is not None:
                self.model += plp.lpSum(
                    [self.lineup[i] for i in range(self.player_count) if self.projections_data.loc[i, 'Position'] == position]
                ) <= max_count
    
    def budget_constraint(self, budget_max, budget_min=0):
        self.model += plp.lpSum([self.lineup[i] * self.projections_data.loc[i, 'Cost'] for i in range(self.player_count)]) <= budget_max
        self.model += plp.lpSum([self.lineup[i] * self.projections_data.loc[i, 'Cost'] for i in range(self.player_count)]) >= budget_min

    def max_players_from_same_team_constraint(self, max_players_per_team):
        for team in self.projections_data['Team'].unique():
            self.model += plp.lpSum([self.lineup[i] for i in range(self.player_count) if self.projections_data.loc[i, 'Team'] == team]) <= max_players_per_team

    def solve(self):
        self.model.solve(PULP_CBC_CMD(msg=0))
        print(f"Status: {plp.LpStatus[self.model.status]}")

    def print_players_by_position(self):
        self.selected_players = defaultdict(list)
        for i in range(self.player_count):
            if self.lineup[i].value() == 1:
                player = self.projections_data.loc[i]
                self.selected_players[player['Position']].append({
                    'Name': player['Name'],
                    'Team': player['Team'],
                    'Cost': player['Cost'],
                    'Predicted_Points': player['Predicted_Points'],
                    'Captain': self.captain[i].value() == 1
                })

        self.total_points = 0
        self.total_cost = 0
        for position in ['Goalkeeper', 'Defender', 'Midfielder', 'Forward']:
            if position in self.selected_players:
                print(f"\n{position}:")
                for player in self.selected_players[position]:
                    captain_str = " (C)" if player['Captain'] else ""
                    points = player['Predicted_Points'] * (2 if player['Captain'] else 1)
                    print(f"  {player['Name']}{captain_str} - {player['Team']} - Cost: {player['Cost']}m - Predicted Points: {points}")
                    self.total_points += points
                    self.total_cost += player['Cost']
        print(f"\nTotal Predicted Points: {round(self.total_points, 2)}")
        print(f"Total Cost: {round(self.total_cost, 2)}m")