import pandas as pd
import json
import glob
import os
import plotly.graph_objects as go
import streamlit as st
import requests
import zipfile
import io
import tempfile

# Download and extract JSON files
url = "https://cricsheet.org/downloads/ipl_json.zip"
response = requests.get(url)
# Create a temporary directory
temp_dir = tempfile.mkdtemp()
with zipfile.ZipFile(io.BytesIO(response.content)) as z:
    z.extractall(temp_dir)

# Path to your JSON files
json_path = f"{temp_dir}/*.json"
json_files = glob.glob(json_path)

# Lists to store all ball-by-ball data
all_balls = []

for file_path in json_files:
    try:
        with open(file_path, 'r') as f:
            match_data = json.load(f)
    except json.JSONDecodeError:
        print(f"Error reading {file_path}")
        continue  # Skip this file if there's an error

    # Extract match info
    match_info = match_data.get('info', {})
    
    if not match_info:
        print(f"Warning: 'info' key is missing in match data from {file_path}")
        continue

    # Extract date, season, venue, teams, and toss information
    match_date = match_info.get('dates', [''])[0]  # Access the first date
    season = str(match_info.get('season', ''))
    venue = match_info.get('venue', 'Unknown Venue')
    teams = match_info.get('teams', [])
    if len(teams) < 2:
        print(f"Warning: Not enough teams found in match data from {file_path}")
        continue
    toss_winner = match_info.get('toss', {}).get('decision', '')

    # Extract innings data
    for innings in match_data.get('innings', []):
        batting_team = innings.get('team', '')
        bowling_team = teams[0] if teams[1] == batting_team else teams[1]
        
        for over in innings.get('overs', []):
            over_num = over.get('over', 0)
            
            for delivery in over.get('deliveries', []):
                ball_data = {
                    'match_id': os.path.basename(file_path).split('.')[0],
                    'date': match_date,
                    'season': season,
                    'venue': venue,
                    'batting_team': batting_team,
                    'bowling_team': bowling_team,
                    'over': over_num,
                    'batter': delivery.get('batter', ''),
                    'bowler': delivery.get('bowler', ''),
                    'non_striker': delivery.get('non_striker', ''),
                    'runs_batter': delivery.get('runs', {}).get('batter', 0),
                    'extras': delivery.get('runs', {}).get('extras', 0),
                    'total_runs': delivery.get('runs', {}).get('total', 0),
                }
                
                # Add extras details if present
                if 'extras' in delivery:
                    for extra_type in ['wides', 'noballs', 'legbyes', 'byes']:
                        ball_data[extra_type] = delivery['extras'].get(extra_type, 0)
                else:
                    ball_data.update({'wides': 0, 'noballs': 0, 'legbyes': 0, 'byes': 0})
                
                # Wicket handling logic
                if 'wickets' in delivery:
                    ball_data['wicket'] = len(delivery['wickets'])
                    wicket = delivery['wickets'][0]
                    ball_data['wicket_type'] = wicket.get('kind', '')
                    ball_data['player_out'] = wicket.get('player_out', '')
                    if 'fielders' in wicket:
                        ball_data['fielder'] = wicket['fielders'][0].get('name', '') if wicket['fielders'] else ''
                    else:
                        ball_data['fielder'] = ''
                else:
                    ball_data['wicket'] = 0
                    ball_data['wicket_type'] = ''
                    ball_data['player_out'] = ''
                    ball_data['fielder'] = ''
                
                all_balls.append(ball_data)

# Create DataFrame
df = pd.DataFrame(all_balls)

# Convert date to datetime
if 'date' in df.columns:
    df['date'] = pd.to_datetime(df['date'])

# Extract unique years from the date column
available_years = sorted(df['date'].dt.year.unique(), reverse=True)

# Streamlit app
st.title("IPL Player Performance")

# Add year selection dropdown
selected_year = st.selectbox("Select Year", options=available_years)

# Filter data for selected year
year_data = df[df['date'].dt.year == selected_year].copy()

# Calculate required statistics
year_data['valid_ball'] = year_data['wides'] == 0
year_data['balls_faced'] = year_data.groupby(['match_id', 'batter'])['valid_ball'].cumsum()
year_data['total_runs_scored'] = year_data.groupby(['match_id', 'batter'])['runs_batter'].transform('sum')

# Create a list of players for the selected year
year_players = sorted(year_data['batter'].unique().tolist())
year_players = [player for player in year_players if isinstance(player, str)]

selected_player = st.selectbox("Select a player", options=year_players)

# Keep your original create_player_performance_chart function
def create_player_performance_chart(data, player_name):
    if player_name is None or player_name == '':
        return go.Figure(), (0, 0)

    player_data = data[data['batter'].str.contains(player_name, case=False, na=False)].sort_values('date')

    if player_data.empty:
        return go.Figure(), (0, 0)

    player_performances = player_data.groupby(['match_id', 'bowling_team', 'date', 'venue']).agg({
        'total_runs_scored': 'first',
        'balls_faced': 'max'
    }).reset_index()

    # Remove any duplicate rows based on match_id
    player_performances = player_performances.drop_duplicates(subset=['match_id'])

    # Calculate total runs and overall strike rate for the season
    total_runs = player_performances['total_runs_scored'].sum()
    total_balls = player_performances['balls_faced'].sum()
    overall_strike_rate = (total_runs / total_balls * 100).round(2) if total_balls > 0 else 0

    player_performances['strike_rate'] = (player_performances['total_runs_scored'] / player_performances['balls_faced'] * 100).round(2)

    # Define team acronyms
    team_acronyms = {
        'Kolkata Knight Riders': 'KKR',
        'Royal Challengers Bengaluru': 'RCB',
        'Chennai Super Kings': 'CSK',
        'Delhi Capitals': 'DC',
        'Mumbai Indians': 'MI',
        'Punjab Kings': 'PBKS',
        'Rajasthan Royals': 'RR',
        'Sunrisers Hyderabad': 'SRH',
        'Lucknow Super Giants': 'LSG',
        'Gujarat Titans': 'GT'
    }

    # Update bowling_team to use acronyms
    player_performances['bowling_team'] = player_performances['bowling_team'].replace(team_acronyms)

    traces = []
    for match in player_performances['match_id'].unique():
        match_data = player_performances[player_performances['match_id'] == match]
        traces.append(go.Bar(
            name='',
            x=match_data['bowling_team'],
            y=match_data['total_runs_scored'],
            hovertemplate='<b>Opposition Team:</b> %{x}<br>' +
                          '<b>Runs:</b> %{y}<br>' +
                          '<b>Balls Faced:</b> %{customdata}<br>' +
                          '<b>Date:</b> %{meta}<br>',
            customdata=match_data['balls_faced'],
            meta=match_data['date'].dt.strftime('%Y-%m-%d'),
        ))

    fig = go.Figure(data=traces)

    fig.update_layout(
        title=f'{player_name}\'s Performances in IPL {selected_year}',
        xaxis_title='Opposition Team',
        yaxis_title='Runs Scored',
        barmode='stack',
        showlegend=False,
        plot_bgcolor='rgba(255, 255, 255, 1)',
        xaxis=dict(ticklen=4, zeroline=False, gridcolor='rgb(204, 204, 204)'),
        yaxis=dict(ticklen=4, gridcolor='rgb(204, 204, 204)'),
        bargap=0.2,
        bargroupgap=0.1
    )

    return fig, (total_runs, overall_strike_rate)

if selected_player:
    fig, (total_runs, overall_strike_rate) = create_player_performance_chart(year_data, selected_player)
    
    # Display summary statistics
    st.write(f"**{selected_year} Season Summary for {selected_player}:**")
    st.write(f"Total Runs: {total_runs}")
    st.write(f"Overall Strike Rate: {overall_strike_rate}")
    
    # Display the plot
    st.plotly_chart(fig)
else:
    st.write("Please select a player to view their performance.")
