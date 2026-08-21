"""Interactive player banning and forcing with fuzzy name matching."""

from fuzzywuzzy import process


def _choose_player_indices(df, action: str) -> list[int]:
    selected_indices: list[int] = []
    while True:
        search_name = input(
            f"Enter player name to {action} (or press enter to finish): "
        ).strip()
        if not search_name:
            break

        matches = process.extractBests(
            search_name, df["Name"].tolist(), score_cutoff=50
        )
        if not matches:
            print("No matches found. Please try again.")
            continue

        print("Matches found:")
        for number, (name, score) in enumerate(matches, 1):
            row_index = df.index[df["Name"] == name][0]
            player_id = df.loc[row_index, "ID"]
            print(
                f"{number}. {name} (ID: {player_id}, Index: {row_index}, "
                f"Score: {score})"
            )

        while True:
            choice = input(
                f"Enter the number of the player to {action} "
                "(or 'skip' to search again): "
            )
            if choice.lower() == "skip":
                break
            try:
                choice_index = int(choice) - 1
            except ValueError:
                print("Invalid input. Please enter a number or 'skip'.")
                continue
            if not 0 <= choice_index < len(matches):
                print("Invalid choice. Please try again.")
                continue

            selected_name = matches[choice_index][0]
            selected_index = int(df.index[df["Name"] == selected_name][0])
            selected_indices.append(selected_index)
            past_tense = "Banned" if action == "ban" else "Forced"
            print(
                f"{past_tense}: {selected_name} "
                f"(ID: {df.loc[selected_index, 'ID']}, Index: {selected_index})"
            )
            break
    return selected_indices


def ban_players(df):
    return _choose_player_indices(df, "ban")


def force_players(df, _existing_indices=None):
    return _choose_player_indices(df, "force")


def run_ban_force(df):
    should_ban = input("Do you want to ban players? (yes/no): ").strip().lower()
    ban_indices = ban_players(df) if should_ban == "yes" else []

    should_force = input("Do you want to force players? (yes/no): ").strip().lower()
    force_indices = force_players(df) if should_force == "yes" else []
    return ban_indices, force_indices
