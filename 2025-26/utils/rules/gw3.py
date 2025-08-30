import pandas as pd
import soccerdata as sd
from fuzzywuzzy import fuzz, process
from scipy.stats import poisson

def gw3_rules(projections: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Gameweek 3 rules to player projections.

    Rules:
        - Retrieve FBref defensive stats for Premier League season 25-26.
        - Match players using fuzzy string matching.
        - Calculate defensive actions per 90 by position.
        - Use Poisson distribution to assign expected defensive challenge points (xDCpts).
        - Add xDCpts to existing Predicted_Points.

    Args:
        projections (pd.DataFrame): DataFrame of player projections.

    Returns:
        pd.DataFrame: Updated DataFrame with modified Predicted_Points.
    """

    leagues = "ENG-Premier League"
    season = "24-25"
    fbref = sd.FBref(leagues=leagues, seasons=season)

    # Load defense and misc stats
    df_defense = fbref.read_player_season_stats(stat_type="defense")
    df_misc = fbref.read_player_season_stats(stat_type="misc")

    # Flatten indices and column names
    df_defense_reset = df_defense.reset_index()
    df_misc_reset = df_misc.reset_index()
    df_defense_reset.columns = ["_".join(col).strip("_") for col in df_defense_reset.columns]
    df_misc_reset.columns = ["_".join(col).strip("_") for col in df_misc_reset.columns]

    # Select defense stats
    defense_cols = ["league", "season", "team", "player"]
    for col in df_defense_reset.columns:
        if "90s" in col:
            defense_cols.append(col)
        elif "TklW" in col:
            defense_cols.append(col)
        elif col == "Int" or "Int_" in col:
            defense_cols.append(col)
        elif "Blocks" in col:
            defense_cols.append(col)
        elif col == "Clr" or "Clr_" in col:
            defense_cols.append(col)
    df_defense_filtered = df_defense_reset[defense_cols]

    # Select misc stats
    misc_cols = ["league", "season", "team", "player"]
    for col in df_misc_reset.columns:
        if "Recov" in col:
            misc_cols.append(col)
    df_misc_filtered = df_misc_reset[misc_cols]

    # Merge defensive and misc stats
    result_df = pd.merge(
        df_defense_filtered,
        df_misc_filtered,
        on=["league", "season", "team", "player"],
        how="inner",
    )

    # Rename columns
    column_mapping = {}
    for col in result_df.columns:
        if "90s" in col:
            column_mapping[col] = "90s"
        elif "TklW" in col:
            column_mapping[col] = "TklW"
        elif "Int" in col and col not in ["league", "season", "team", "player"]:
            column_mapping[col] = "Int"
        elif "Blocks_Blocks" in col:
            column_mapping[col] = "Blocks"
        elif "Clr" in col:
            column_mapping[col] = "Clr"
        elif "Recov" in col:
            column_mapping[col] = "Recov"
    result_df = result_df.rename(columns=column_mapping)

    # Final columns of interest
    final_columns = ["player", "90s", "TklW", "Int", "Recov", "Blocks", "Clr"]
    filtered_df = result_df[final_columns]

    def find_best_match(name: str, choices: list[str], threshold: int = 50) -> tuple[str | None, int]:
        """Return the closest fuzzy match above threshold."""
        if pd.isna(name):
            return None, 0
        match = process.extractOne(name, choices, scorer=fuzz.ratio)
        if match and match[1] >= threshold:
            return match[0], match[1]
        return None, 0

    # Copy projections and prepare columns
    enhanced_projections = projections.copy()
    fbref_players = filtered_df["player"].tolist()
    for col in ["90s", "TklW", "Int", "Recov", "Blocks", "Clr"]:
        enhanced_projections[f"fbref_{col}"] = None

    # Match players
    for idx, row in enhanced_projections.iterrows():
        fuzzy_name = row["Fuzzy"]
        best_match, score = find_best_match(fuzzy_name, fbref_players)
        if best_match:
            fbref_row = filtered_df[filtered_df["player"] == best_match].iloc[0]
            enhanced_projections.at[idx, "fbref_90s"] = fbref_row["90s"]
            enhanced_projections.at[idx, "fbref_TklW"] = fbref_row["TklW"]
            enhanced_projections.at[idx, "fbref_Int"] = fbref_row["Int"]
            enhanced_projections.at[idx, "fbref_Recov"] = fbref_row["Recov"]
            enhanced_projections.at[idx, "fbref_Blocks"] = fbref_row["Blocks"]
            enhanced_projections.at[idx, "fbref_Clr"] = fbref_row["Clr"]

    # Fill missing values
    fbref_stat_columns = [
        "fbref_90s",
        "fbref_TklW",
        "fbref_Int",
        "fbref_Recov",
        "fbref_Blocks",
        "fbref_Clr",
    ]
    enhanced_projections[fbref_stat_columns] = enhanced_projections[fbref_stat_columns].fillna(0)

    def calculate_defensive_actions(row) -> float:
        """Return total defensive actions per 90 adjusted by position."""
        if row["Position"] == "Goalkeeper":
            return 0
        if row["fbref_90s"] == 0:
            return 0
        # Don't include players <= 5 games worth of data as prone to variance
        if row["fbref_90s"] <= 5.00:
            return 0

        tackles_per_90 = row["fbref_TklW"] / row["fbref_90s"]
        int_per_90 = row["fbref_Int"] / row["fbref_90s"]
        clr_per_90 = row["fbref_Clr"] / row["fbref_90s"]
        blocks_per_90 = row["fbref_Blocks"] / row["fbref_90s"]

        if row["Position"] == "Defender":
            return tackles_per_90 + int_per_90 + clr_per_90 + blocks_per_90
        recov_per_90 = row["fbref_Recov"] / row["fbref_90s"]
        return tackles_per_90 + int_per_90 + clr_per_90 + blocks_per_90 + recov_per_90

    # Calculate defensive actions per 90
    enhanced_projections["defensive_actions_per_90"] = enhanced_projections.apply(
        calculate_defensive_actions, axis=1
    )

    # Drop temporary fbref columns
    fbref_columns = [col for col in enhanced_projections.columns if col.startswith("fbref_")]
    enhanced_projections = enhanced_projections.drop(columns=fbref_columns)

    # Expected defensive actions
    enhanced_projections["expected_defensive_actions"] = (
        enhanced_projections["defensive_actions_per_90"] * (enhanced_projections["xMins"] / 90)
    )

    def calculate_challenge_xpts(row) -> float:
        """Return expected defensive challenge points using Poisson probabilities."""
        lambda_val = row["expected_defensive_actions"]
        if lambda_val <= 0:
            return 0

        position = row["Position"]
        if position == "Defender":
            prob_reaching_threshold = 1 - poisson.cdf(9, lambda_val)
        elif position in ["Midfielder", "Forward"]:
            prob_reaching_threshold = 1 - poisson.cdf(11, lambda_val)
        else:
            prob_reaching_threshold = 0

        return prob_reaching_threshold * 10

    # Apply expected points calculation
    enhanced_projections["xDCpts"] = enhanced_projections.apply(calculate_challenge_xpts, axis=1)

    # Update predicted points
    if "Predicted_Points" in enhanced_projections.columns:
        enhanced_projections["Predicted_Points"] = round(
            enhanced_projections["Predicted_Points"] + enhanced_projections["xDCpts"], 1
        )
    else:
        enhanced_projections["Predicted_Points"] = enhanced_projections["xDCpts"]

    # Drop intermediate columns
    columns_to_drop = ["defensive_actions_per_90", "expected_defensive_actions", "xDCpts"]
    enhanced_projections = enhanced_projections.drop(columns=columns_to_drop)

    return enhanced_projections
