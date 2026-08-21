"""Integer linear-programming solver used by FPL Challenge gameweeks."""

from collections import defaultdict

import pandas as pd
import pulp as plp
from pulp import PULP_CBC_CMD


class FPLChallengeOptimiser:
    def __init__(self, gameweek, projections_data: pd.DataFrame):
        self.gameweek = gameweek
        self.projections_data = projections_data.reset_index(drop=True).copy()

    def setup_problem(self, problem_name, objective=plp.LpMaximize):
        self.player_ids = self.projections_data["ID"].tolist()
        self.player_count = len(self.player_ids)
        print(f"Setting up problem with name: {problem_name}.")
        self.model = plp.LpProblem(problem_name, objective)

        self.lineup = [
            plp.LpVariable(f"lineup_{player_id}", 0, 1, cat="Integer")
            for player_id in self.player_ids
        ]
        self.captain = [
            plp.LpVariable(f"captain_{player_id}", 0, 1, cat="Integer")
            for player_id in self.player_ids
        ]
        self.model += plp.lpSum(
            self.lineup[index]
            * self.projections_data.loc[index, "Predicted_Points"]
            for index in range(self.player_count)
        ) + plp.lpSum(
            self.captain[index]
            * self.projections_data.loc[index, "Predicted_Points"]
            for index in range(self.player_count)
        )

    def total_players_constraint(self, total_players):
        self.model += plp.lpSum(self.lineup) == total_players

    def exclude_players_constraint(self, exclude_index_list):
        for index in exclude_index_list:
            self.model += self.lineup[index] == 0

    def force_players_constraint(self, force_index_list):
        for index in force_index_list:
            self.model += self.lineup[index] == 1

    def captain_count_constraint(self, captain_count):
        self.model += plp.lpSum(self.captain) == captain_count
        for index in range(self.player_count):
            self.model += self.captain[index] <= self.lineup[index]

    def position_count_constraints(self, position_counts):
        for position, counts in position_counts.items():
            eligible = [
                self.lineup[index]
                for index in range(self.player_count)
                if self.projections_data.loc[index, "Position"] == position
            ]
            if counts.get("min_count") is not None:
                self.model += plp.lpSum(eligible) >= counts["min_count"]
            if counts.get("max_count") is not None:
                self.model += plp.lpSum(eligible) <= counts["max_count"]

    def budget_constraint(self, budget_max, budget_min=0):
        total_cost = plp.lpSum(
            self.lineup[index] * self.projections_data.loc[index, "Cost"]
            for index in range(self.player_count)
        )
        self.model += total_cost <= budget_max
        self.model += total_cost >= budget_min

    def max_players_from_same_team_constraint(self, max_players_per_team):
        for team in self.projections_data["Team"].unique():
            self.model += plp.lpSum(
                self.lineup[index]
                for index in range(self.player_count)
                if self.projections_data.loc[index, "Team"] == team
            ) <= max_players_per_team

    def solve(self):
        self.model.solve(PULP_CBC_CMD(msg=0))
        status = plp.LpStatus[self.model.status]
        print(f"Status: {status}")
        if status != "Optimal":
            raise RuntimeError(f"Solver did not find an optimal lineup: {status}")

    def print_players_by_position(self):
        self.selected_players = defaultdict(list)
        for index in range(self.player_count):
            if self.lineup[index].value() == 1:
                player = self.projections_data.loc[index]
                self.selected_players[player["Position"]].append(
                    {
                        "ID": player["ID"],
                        "Name": player["Name"],
                        "Team": player["Team"],
                        "Cost": player["Cost"],
                        "Predicted_Points": player["Predicted_Points"],
                        "Captain": self.captain[index].value() == 1,
                    }
                )

        self.total_points = 0
        self.total_cost = 0
        for position in ["Goalkeeper", "Defender", "Midfielder", "Forward"]:
            if position not in self.selected_players:
                continue
            print(f"\n{position}:")
            for player in self.selected_players[position]:
                captain_str = " (C)" if player["Captain"] else ""
                points = player["Predicted_Points"] * (
                    2 if player["Captain"] else 1
                )
                print(
                    f"  {player['Name']}{captain_str} - {player['Team']} - "
                    f"Cost: {player['Cost']}m - Predicted Points: {points}"
                )
                self.total_points += points
                self.total_cost += player["Cost"]
        print(f"\nTotal Predicted Points: {round(self.total_points, 2)}")
        print(f"Total Cost: {round(self.total_cost, 2)}m")
