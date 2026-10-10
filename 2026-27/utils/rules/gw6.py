"""Projection adjustment for GW6: Matchwinner."""

from __future__ import annotations

import pandas as pd

from utils.projections import generate_team_projections

WINNING_GOAL_POINTS = 10


def gw6_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """Add expected points for scoring a winning goal in each fixture."""
    teams = generate_team_projections(6).set_index(["Fixture_ID", "Is_Home"])
    adjusted = projections.copy()
    winning_goals = []
    for fixtures in adjusted["Fixture_Projections"]:
        expected_winning_goals = 0.0
        for fixture in fixtures:
            team = teams.loc[(fixture["Fixture_ID"], fixture["Is_Home"])]
            team_goals = team["Team_Expected_Goals"]
            if team_goals > 0:
                # XLTHM uses the same scorer weights for each team goal.
                expected_winning_goals += (
                    team["Win_Probability"]
                    * fixture["Projected_Goals"]
                    / team_goals
                )
        winning_goals.append(expected_winning_goals)

    adjusted["Base_Predicted_Points"] = adjusted["Predicted_Points"]
    adjusted["Winning_Goal_Probability"] = winning_goals
    adjusted["Winning_Goal_xPts"] = (
        adjusted["Winning_Goal_Probability"] * WINNING_GOAL_POINTS
    )
    adjusted["Predicted_Points"] = (
        adjusted["Base_Predicted_Points"] + adjusted["Winning_Goal_xPts"]
    ).round(2)
    return adjusted
