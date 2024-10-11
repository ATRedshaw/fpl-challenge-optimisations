import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time

def get_tooltip_info(url):
    print('Getting tooltip info...')
    time.sleep(10)
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    tooltip_info = []
    for th in soup.find_all('th'):
        displayed_text = th.text.strip()
        tooltip = th.get('data-tip')
        if tooltip:
            tooltip_soup = BeautifulSoup(tooltip, 'html.parser')
            strong_text = tooltip_soup.find('strong')
            if strong_text:
                strong_tooltip = strong_text.text.strip()
                explanation = tooltip_soup.text.replace(strong_text.text, '').strip()
                if not any(info['displayed_text'] == displayed_text for info in tooltip_info):
                    tooltip_info.append({
                        'displayed_text': displayed_text,
                        'strong_tooltip': strong_tooltip,
                        'explanation': explanation
                    })
        
    return tooltip_info

def get_fbref_squad_links(url):
    time.sleep(10)
    # Send a GET request to the URL
    response = requests.get(url)
    
    # Parse the HTML content
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Find the first table on the page
    first_table = soup.find('table')
    
    if not first_table:
        return []  # Return an empty list if no table is found
    
    # Find all 'a' tags within the first table
    all_links = first_table.find_all('a')
    
    # Extract href attributes and filter for links starting with "/en/squads/"
    fbref_squad_links = set()  # Using a set to automatically remove duplicates
    for link in all_links:
        href = link.get('href')
        if href and href.startswith('/en/squads/'):
            full_url = f"https://fbref.com{href}"
            fbref_squad_links.add(full_url)
    
    # Convert set back to list and return
    return list(fbref_squad_links)

def clean_column_name(name):
    return re.sub(r'[^a-zA-Z0-9]', '_', name.lower()).strip('_')

def convert_to_tooltip_names(columns, tooltip_info):
    tooltip_dict = {info['displayed_text']: clean_column_name(info['strong_tooltip']) 
                    for info in tooltip_info if info['strong_tooltip']}
    
    return [tooltip_dict.get(col, col) for col in columns]

def flatten_column_names(columns, tooltip_info):
    if isinstance(columns, pd.MultiIndex):
        flat_columns = []
        for col in columns:
            if col[0].startswith('Unnamed:'):
                flat_columns.append(col[1])
            else:
                flat_columns.append(f"{col[0]}_{col[1]}" if col[1] != '' else col[0])
        return flat_columns
    else:
        return columns

def process_against_table(table):
    # Check if the first column starts with 'vs '
    if table.columns[0].startswith('squad_') and table.iloc[0, 0].startswith('vs '):
        # Remove 'vs ' from the first column values
        table.iloc[:, 0] = table.iloc[:, 0].str.replace('vs ', '')
        
        # Modify column names to end with '_AGAINST'
        new_columns = [col + '_AGAINST' for col in table.columns]
        table.columns = new_columns
    
    return table

def get_tables(url, tooltip_info):
    print('Getting team tables...')
    time.sleep(10)
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    all_tables = pd.read_html(url)
    
    processed_tables = []
    for i, table in enumerate(all_tables):
        # Find the corresponding table in the HTML
        html_table = soup.find_all('table')[i]
        
        # Find the closest h2 tag before the table
        h2 = html_table.find_previous('h2')
        if h2:
            # Extract the main heading text (without the span)
            heading = h2.contents[0].strip()
            heading_prefix = clean_column_name(heading)
        else:
            heading_prefix = f"table_{i+1}"
        
        # First, flatten the column names
        flattened_columns = flatten_column_names(table.columns, tooltip_info)
        # Then, convert to tooltip names
        converted_columns = convert_to_tooltip_names(flattened_columns, tooltip_info)
        # Add the heading prefix to each column name
        prefixed_columns = [f"{heading_prefix}_{col}" for col in converted_columns]
        
        table.columns = prefixed_columns
        
        # Process the table if it's an "against" table
        table = process_against_table(table)
        
        processed_tables.append(table)
    
    return processed_tables

def join_tables(tables):
    if not tables:
        return None

    def get_team_column(table):
        # Check if 'premier_league_Squad' is in the columns
        if 'premier_league_Squad' in table.columns:
            return 'premier_league_Squad'
        # Otherwise, return the first column name
        return table.columns[0]

    # Start with the first table
    result = tables[0].rename(columns={get_team_column(tables[0]): 'Team'})

    # Join with the remaining tables
    for i in range(1, len(tables)):
        current_table = tables[i]
        team_column = get_team_column(current_table)
        
        # Rename the team column to 'Team'
        current_table = current_table.rename(columns={team_column: 'Team'})
        
        # Merge with the result
        result = result.merge(current_table, on='Team', how='outer')

    return result

def get_player_tables(url, tooltip_info):
    print(f'Getting player tables (url: {url})...')

    team_name = url.split('/')[-1]
    team_hyphen_count = team_name.count('-')
    if team_hyphen_count == 1:
        team_name = team_name.split('-')[0]
    elif team_hyphen_count > 1:
        team_name = ' '.join(team_name.split('-')[:-1])

    time.sleep(10)
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    all_tables = pd.read_html(url)
    
    processed_tables = []
    for i, table in enumerate(all_tables):
        # Find the corresponding table in the HTML
        html_table = soup.find_all('table')[i]
        
        # Find the closest h2 tag before the table
        h2 = html_table.find_previous('h2')
        if h2:
            # Extract the main heading text (without the span)
            heading = h2.contents[0].strip()
            heading_prefix = clean_column_name(heading)
        else:
            heading_prefix = f"table_{i+1}"
        
        # First, flatten the column names 
        flattened_columns = flatten_column_names(table.columns, tooltip_info)
        # Then, convert to tooltip names
        converted_columns = convert_to_tooltip_names(flattened_columns, tooltip_info)
        # Add the heading prefix to each column name
        prefixed_columns = [f"{heading_prefix}_{col}" for col in converted_columns]
        
        table.columns = prefixed_columns
        
        # Check if 'Player' is in any of the column names
        if any('player' in col.lower() for col in table.columns):
            # Find the exact column name containing 'player'
            player_column = next(col for col in table.columns if 'player' in col.lower())
            
            # Remove rows where Player is 'Squad Total' or 'Opponent Total'
            table = table[~table[player_column].isin(['Squad Total', 'Opponent Total'])]
            
            # Only append the table if it's not empty after removing rows
            if not table.empty:
                processed_tables.append(table)
    
    return processed_tables, team_name

def join_player_tables(tables, team_name):
    # Join all player tables on 'Player' column

    for i, table in enumerate(tables):
        #Renmame the first column to 'Player
        tables[i] = table.rename(columns={table.columns[0]: 'Player'})

    for i in range(1, len(tables)):
        tables[0] = tables[0].merge(tables[i], on='Player', how='outer')

    # Replace NaN values with 0
    tables[0] = tables[0].fillna(0)

    tables[0]['Player_Team_Name'] = team_name

    return tables[0]

def fbref_main():
    base_url = 'https://fbref.com'
    premier_league_url = f'{base_url}/en/comps/9/Premier-League-Stats'
    
    # Get tooltip information
    team_tooltip_info = get_tooltip_info(premier_league_url)
    
    # Get and process tables
    team_tables = get_tables(premier_league_url, team_tooltip_info)
    
    combined_team_table = join_tables(team_tables)

    team_links = get_fbref_squad_links(premier_league_url)
    player_tooltip_info = get_tooltip_info(team_links[0])
    player_tables_list = []
    for team_link in team_links:
        # Get and join player tables for the current team
        individual_team_player_tables, player_team_name = get_player_tables(team_link, player_tooltip_info)
        combined_individual_team_player_table = join_player_tables(individual_team_player_tables, player_team_name)
        # Add the player data for this team to the list
        player_tables_list.append(combined_individual_team_player_table)
    
    # Concatenate all player tables
    combined_player_table = pd.concat(player_tables_list, ignore_index=True)

    return combined_team_table, combined_player_table

if __name__ == '__main__':
    team, player = fbref_main()

    # export to fbref_player_cols and fbref_team_cols in templates/fbref/HERE
    team.to_csv('templates/fbref/fbref_team_cols.csv', index=False)
    player.to_csv('templates/fbref/fbref_player_cols.csv', index=False)