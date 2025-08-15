from fuzzywuzzy import process

def ban_players(df):
    ban_ids = []
    while True:
        search_name = input("Enter player name to ban (or press enter to finish): ").strip()
        
        if search_name.lower() == '':
            break
        
        # Perform fuzzy matching with a lower score cutoff and no player limit
        matches = process.extractBests(search_name, df['Name'].tolist(), score_cutoff=50)
        
        if not matches:
            print("No matches found. Please try again.")
            continue
        
        # Display matches
        print("Matches found:")
        for idx, (name, score) in enumerate(matches, 1):
            player_index = df[df['Name'] == name].index[0]
            player_id = df.loc[player_index, 'ID']
            print(f"{idx}. {name} (ID: {player_id}, Index: {player_index}, Score: {score})")
        
        # Ask user to select a match
        while True:
            choice = input("Enter the number of the player to ban (or 'skip' to search again): ")
            if choice.lower() == 'skip':
                break
            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(matches):
                    selected_name = matches[choice_idx][0]
                    selected_index = df[df['Name'] == selected_name].index[0]
                    selected_id = df.loc[selected_index, 'ID']
                    ban_ids.append(selected_index)
                    print(f"Banned: {selected_name} (ID: {selected_id}, Index: {selected_index})")
                    break
                else:
                    print("Invalid choice. Please try again.")
            except ValueError:
                print("Invalid input. Please enter a number or 'skip'.")
    
    return ban_ids

def force_players(df, force_ids):
    force_ids = []
    while True:
        search_name = input("Enter player name to force (or press enter to finish): ").strip()
        
        if search_name.lower() == '':
            break
        
        # Perform fuzzy matching with a lower score cutoff and no limit
        matches = process.extractBests(search_name, df['Name'].tolist(), score_cutoff=50)
        
        if not matches:
            print("No matches found. Please try again.")
            continue
        
        # Display matches
        print("Matches found:")
        for idx, (name, score) in enumerate(matches, 1):
            player_index = df[df['Name'] == name].index[0]
            player_id = df.loc[player_index, 'ID']
            print(f"{idx}. {name} (ID: {player_id}, Index: {player_index}, Score: {score})")
        
        # Ask user to select a match
        while True:
            choice = input("Enter the number of the player to force (or 'skip' to search again): ")
            if choice.lower() == 'skip':
                break
            try:
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(matches):
                    selected_name = matches[choice_idx][0]
                    selected_index = df[df['Name'] == selected_name].index[0]
                    selected_id = df.loc[selected_index, 'ID']
                    force_ids.append(selected_index)  # Add to force_ids instead of ban_ids
                    print(f"Forced: {selected_name} (ID: {selected_id}, Index: {selected_index})")
                    break
                else:
                    print("Invalid choice. Please try again.")
            except ValueError:
                print("Invalid input. Please enter a number or 'skip'.")
    
    return force_ids

def run_ban_force(df):
    should_ban = input("Do you want to ban players? (yes/no): ").strip().lower()
    if should_ban == 'yes':
        ban_ids = ban_players(df)
    else:
        ban_ids = []
    
    should_force = input("Do you want to force players? (yes/no): ").strip().lower()
    if should_force == 'yes':
        force_ids = force_players(df, ban_ids)
    else:
        force_ids = []
    
    return ban_ids, force_ids