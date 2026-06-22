## not accounting for comps with grading, idk about titans yet either
import pandas as pd
import os
import base64
import shutil
import streamlit as st
import plotly.express as px
from data import load_data, get_leagues, filter_league, make_long, make_summary, make_full_schedule, make_fixture_tracker, make_form, make_auto_predictions, predict_score, fit_poisson_model, predict_score_poisson, get_age_groups, get_grades, make_movement, get_team_color, get_carry_over_stats, get_weather

@st.cache_data
def load_cached_data():
    return load_data()

df_raw = load_cached_data()

_logo_cache = {}

def get_logo_base64(team):
    club = team.split('-')[0].strip()
    if club in _logo_cache:
        return _logo_cache[club]
    path = os.path.join(os.path.dirname(__file__), 'assets', 'logos', f'{club}.png')
    result = None
    if os.path.exists(path):
        with open(path, 'rb') as f:
            png_b64 = base64.b64encode(f.read()).decode()
        png_uri = f'data:image/png;base64,{png_b64}'
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
            ' viewBox="0 0 100 100">'
            '<defs><clipPath id="c"><circle cx="50" cy="50" r="50"/></clipPath></defs>'
            f'<image href="{png_uri}" x="0" y="0" width="100" height="100" clip-path="url(#c)"/>'
            '</svg>'
        )
        result = f'data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}'
    _logo_cache[club] = result
    return result

static_dir = os.path.join(os.path.dirname(__file__), 'static')
logos_src = os.path.join(os.path.dirname(__file__), 'assets', 'logos')
if os.path.exists(logos_src):
    os.makedirs(static_dir, exist_ok=True)
    for f in os.listdir(logos_src):
        shutil.copy(os.path.join(logos_src, f), os.path.join(static_dir, f))

st.set_page_config(page_title='League View', layout='wide')

df_raw = load_cached_data()
leagues = get_leagues(df_raw)

st.sidebar.title('League view')
age_groups = get_age_groups(df_raw)
selected_age_group = st.sidebar.selectbox('Age group', age_groups)

grades = get_grades(df_raw, selected_age_group)
selected_league = st.sidebar.selectbox('Grade', grades)

df, df_league, df_byes = filter_league(df_raw, selected_league)
long = make_long(df, df_byes)
carry_over = get_carry_over_stats(df_raw, selected_league)
summary = make_summary(long, carry_over)
color_map = {team: get_team_color(team) for team in summary['Team'].tolist()}
schedule, total_rounds = make_full_schedule(df, df_league, df_byes, summary, df_raw=df_raw, league=selected_league)
tracker = make_fixture_tracker(schedule, df, df_byes, summary, total_rounds)
form_summary = make_form(long)
poisson_model = fit_poisson_model(df)
auto_predictions = make_auto_predictions(schedule, df, df_byes, summary, form_summary, poisson_model)
movement = make_movement(long, summary, carry_over)

chart = None

with st.sidebar.expander('Team overview', expanded=True):
    if st.button('Standings'): st.session_state.chart = 'Standings'
    if st.button('Recent results'): st.session_state.chart = 'Recent results'
    if st.button('Attack vs defence'): st.session_state.chart = 'Attack vs defence'
    if st.button('Points per game'): st.session_state.chart = 'Points per game'
    if st.button('Win / draw / loss'): st.session_state.chart = 'Win / draw / loss'
    if st.button('Goal difference'): st.session_state.chart = 'Goal difference'
    if st.button('Form tracker'): st.session_state.chart = 'Form tracker'

with st.sidebar.expander('Advanced', expanded=False):
    if st.button('Style of Play'): st.session_state.chart = 'Style of Play'
    if st.button('Head-to-head matrix'): st.session_state.chart = 'Head-to-head matrix'
    if st.button('Home vs away'): st.session_state.chart = 'Home vs away'
    if st.button('Winning / losing margins'): st.session_state.chart = 'Winning / losing margins'
    if st.button('Form vs position'): st.session_state.chart = 'Form vs position'

with st.sidebar.expander('Season progression', expanded=False):
    if st.button('Round by round points'): st.session_state.chart = 'Round by round points'
    if st.button('Round by round position'): st.session_state.chart = 'Round by round position'

with st.sidebar.expander('Fixtures', expanded=False):
    if st.button('Fixture tracker'): st.session_state.chart = 'Fixture tracker'

with st.sidebar.expander('Predictions', expanded=False):
    if st.button('Manual predictor'): st.session_state.chart = 'Manual predictor'
    if st.button('Auto predictor'): st.session_state.chart = 'Auto predictor'

if 'chart' not in st.session_state:
    st.session_state.chart = 'Standings'

chart = st.session_state.chart

st.title(st.session_state.chart)


def get_logo(team):
    club = team.split('-')[0].strip()
    path = os.path.join(os.path.dirname(__file__), 'assets', 'logos', f'{club}.png')
    if os.path.exists(path):
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('utf-8')
        return f'data:image/png;base64,{data}'
    return None

if chart == 'Standings':
    form_data = long.sort_values('Round').groupby('Team').tail(5)
    
    def form_squares(team):
        games = form_data[form_data['Team'] == team].sort_values('Round')
        squares = ''
        for _, g in games.iterrows():
            if 'TITANS' in str(g.get('Opponent', '')): squares += '⬜'
            elif g['Result'] == 'W': squares += '🟢'
            elif g['Result'] == 'D': squares += '🟡'
            elif g['Result'] == 'L': squares += '🔴'
            elif g['Result'] == 'BYE': squares += '⬜'
        return squares

    def movement_arrow(team):
        m = movement.get(team, 0)
        if m > 0:
            return f'<span style="color:#639922;font-weight:500;">▲ +{m}</span>'
        if m < 0:
            return f'<span style="color:#E24B4A;font-weight:500;">▼ {m}</span>'
        return '<span style="color:#888780;">➡ 0</span>'

    rows_html = ''
    for i, row in summary.iterrows():
        team = row['Team']
        logo = get_logo(team)
        logo_html = f'<img src="{logo}" style="width:28px;height:28px;border-radius:50%;object-fit:cover;margin-right:6px;vertical-align:middle;">' if logo else ''
        rows_html += f"""
        <tr>
            <td style="padding:8px 6px;color:#888">{i+1}</td>
            <td style="padding:8px 6px;white-space:nowrap;">{logo_html}{team}</td>
            <td style="padding:8px 6px;text-align:center;">{movement_arrow(team)}</td>
            <td style="padding:8px 6px;text-align:center;">{form_squares(team)}</td>
            <td style="padding:8px 6px;text-align:center;">{int(row['P'])}</td>
            <td style="padding:8px 6px;text-align:center;">{int(row['W'])}</td>
            <td style="padding:8px 6px;text-align:center;">{int(row['D'])}</td>
            <td style="padding:8px 6px;text-align:center;">{int(row['L'])}</td>
            <td style="padding:8px 6px;text-align:center;">{int(row['BYE'])}</td>
            <td style="padding:8px 6px;text-align:center;">{int(row['GF'])}</td>
            <td style="padding:8px 6px;text-align:center;">{int(row['GA'])}</td>
            <td style="padding:8px 6px;text-align:center;">{int(row['GD'])}</td>
            <td style="padding:8px 6px;text-align:center;font-weight:500;">{int(row['Pts'])}</td>
        </tr>
        """

    table_html = f"""
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
            <tr style="border-bottom:1px solid #333;color:#888;font-size:11px;text-transform:uppercase;">
                <th style="padding:8px 6px;text-align:left;"></th>
                <th style="padding:8px 6px;text-align:left;">Team</th>
                <th style="padding:8px 6px;">Move</th>
                <th style="padding:8px 6px;">Form</th>
                <th style="padding:8px 6px;">P</th>
                <th style="padding:8px 6px;">W</th>
                <th style="padding:8px 6px;">D</th>
                <th style="padding:8px 6px;">L</th>
                <th style="padding:8px 6px;">BYE</th>
                <th style="padding:8px 6px;">GF</th>
                <th style="padding:8px 6px;">GA</th>
                <th style="padding:8px 6px;">GD</th>
                <th style="padding:8px 6px;">Pts</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
    """

    height = 80 + len(summary) * 68

    st.iframe(f"""
    <html>
    <body style="background:transparent;margin:0;padding:0;font-family:sans-serif;color:#e0e0e0;">
    {table_html}
    </body>
    </html>
    """, height=height)

elif chart == 'Recent results':
    played_rounds = sorted(df['Round'].unique(), reverse=True)
    selected_round = st.selectbox('Select round', played_rounds, format_func=lambda x: f'Round {x}')
    round_games = df[df['Round'] == selected_round].copy()

    if round_games.empty:
        st.info('No completed results found.')
    else:
        round_date = round_games['Date'].iloc[0]
        st.subheader(f'Round {selected_round} — {round_date.strftime("%A %-d %B %Y")}')

        for _, game in round_games.sort_values('Time').iterrows():
            home, away = game['Home'], game['Away']
            hg, ag = int(game['HG']), int(game['AG'])
            venue = str(game['Venue']) if pd.notna(game['Venue']) else ''
            time_str = str(game['Time']) if pd.notna(game['Time']) else ''

            if hg > ag:
                home_style = 'font-weight:700;color:#639922;font-size:19px'
                away_style = 'color:#aaa;font-size:19px'
            elif ag > hg:
                home_style = 'color:#aaa;font-size:19px'
                away_style = 'font-weight:700;color:#639922;font-size:19px'
            else:
                home_style = 'font-weight:700;color:#e0e0e0;font-size:19px'
                away_style = 'font-weight:700;color:#e0e0e0;font-size:19px'

            weather = get_weather(venue, game['Date'], time_str)
            if weather:
                weather_html = f'{weather["emoji"]} {weather["temp"]:.1f}°C &nbsp;·&nbsp; {weather["condition"]}'
            elif venue:
                weather_html = '—'
            else:
                weather_html = ''

            venue_line = f'{time_str} &nbsp;·&nbsp; {venue}' if venue else time_str
            if weather_html:
                venue_line += f' &nbsp;·&nbsp; {weather_html}'

            st.markdown(f"""
<div style="border:1px solid #2a2a2a;border-radius:10px;padding:22px 24px;margin-bottom:14px;background:#1a1a1a;">
  <div style="display:flex;align-items:center;gap:16px;">
    <span style="{home_style};flex:1;text-align:right;">{home}</span>
    <span style="font-size:34px;font-weight:700;min-width:80px;text-align:center;line-height:1;">{hg} – {ag}</span>
    <span style="{away_style};flex:1;">{away}</span>
  </div>
  <div style="margin-top:10px;font-size:14px;color:#999;text-align:center;">{venue_line}</div>
</div>
""", unsafe_allow_html=True)

elif chart == 'Attack vs defence':
    fig = px.bar(
        summary,
        x='Team',
        y=['GF', 'GA'],
        barmode='group',
        labels={'value': 'Goals', 'variable': 'Metric'},
        color_discrete_map={'GF': '#378ADD', 'GA': '#E24B4A'}
    )
    avg_goals = summary['GF'].mean()

    fig.add_hline(y=avg_goals, line_dash='dash', line_color='white', opacity=0.5,
                  annotation_text='League avg', annotation_position='top right')

    st.plotly_chart(fig, width='stretch')

elif chart == 'Points per game':
    fig = px.bar(
        summary.sort_values('PPG'),
        x='PPG',
        y='Team',
        orientation='h',
        color='Color',
        color_discrete_map={c: c for c in summary['Color'].unique()},
        labels={'PPG': 'Points per game', 'Team': ''}
    )
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, width='stretch')

elif chart == 'Win / draw / loss':
    fig = px.bar(
        summary,
        x='Team',
        y=['W', 'D', 'L'],
        barmode='stack',
        color_discrete_map={'W': '#639922', 'D': '#EF9F27', 'L': '#E24B4A'},
        labels={'value': 'Games', 'variable': 'Result'}
    )
    fig.update_layout(showlegend=True)
    st.plotly_chart(fig, width='stretch')

elif chart == 'Goal difference':
    summary_sorted = summary.sort_values('GD', ascending=False)
    
    max_gd = summary_sorted['GD'].abs().max()
    
    fig = px.bar(
        summary_sorted,
        x='Team',
        y='GD',
        labels={'GD': 'Goal difference'},
        color='GD',
        color_continuous_scale=[[0, '#E24B4A'], [0.5, '#E24B4A'], [0.5, '#639922'], [1, '#639922']],
        range_color=[-max_gd, max_gd],
    )
    fig.update_layout(coloraxis_showscale=False)
    fig.add_hline(y=0, line_color='grey', line_width=1)
    st.plotly_chart(fig, width='stretch')

elif chart == 'Style of Play':
    avg_gf = summary['GF_per_game'].mean()
    avg_ga = summary['GA_per_game'].mean()

    fig = px.scatter(
        summary,
        x='GF_per_game',
        y='GA_per_game',
        size='PPG',
        color='Color',
        text='Team',
        size_max=60,
        color_discrete_map={c: c for c in summary['Color'].unique()},
        labels={
            'GF_per_game': 'Goals scored per game',
            'GA_per_game': 'Goals conceded per game',
            'PPG': 'Points per game',
        }
    )

    fig.add_vline(x=avg_gf, line_dash='dash', line_color='grey', opacity=0.5)
    fig.add_hline(y=avg_ga, line_dash='dash', line_color='grey', opacity=0.5)

    fig.add_annotation(x=0.02, y=0.98, xref='paper', yref='paper',
        text='Leaky', showarrow=False,
        font=dict(size=11, color='grey'), xanchor='left', yanchor='top')
    fig.add_annotation(x=0.98, y=0.98, xref='paper', yref='paper',
        text='Kamikaze', showarrow=False,
        font=dict(size=11, color='grey'), xanchor='right', yanchor='top')
    fig.add_annotation(x=0.02, y=0.02, xref='paper', yref='paper',
        text='Stubborn', showarrow=False,
        font=dict(size=11, color='grey'), xanchor='left', yanchor='bottom')
    fig.add_annotation(x=0.98, y=0.02, xref='paper', yref='paper',
        text='Clinical', showarrow=False,
        font=dict(size=11, color='grey'), xanchor='right', yanchor='bottom')

    fig.update_traces(textposition='top center')
    fig.update_layout(showlegend=False)
    st.plotly_chart(fig, width='stretch')

## when 3rd fixtures start getting played work around 
## add interpretation, "any win in the bottom diagonal/ loss in the top diagonal can be considered an 'upset' based on position."
elif chart == 'Head-to-head matrix':
    teams = summary['Team'].tolist()

    matrix = {h: {a: [] for a in teams} for h in teams}

    for _, row in df.iterrows():
        h, a = row['Home'], row['Away']
        matrix[h][a].append(f"{int(row['HG'])}–{int(row['AG'])}")

    numeric = pd.DataFrame(index=teams, columns=teams, dtype=float)
    for h in teams:
        for a in teams:
            if h == a:
                numeric.loc[h, a] = 0
            elif len(matrix[h][a]) == 0:
                numeric.loc[h, a] = None
            else:
                margins = []
                for score in matrix[h][a]:
                    hg, ag = map(int, score.split('–'))
                    margins.append(hg - ag)
                avg_margin = sum(margins) / len(margins)
                # normalise to -1 to 1 scale, capping at 5 goal difference
                numeric.loc[h, a] = max(-1, min(1, avg_margin / 5))

    fig = px.imshow(
        numeric.astype(float),
        color_continuous_scale=[
            [0.0, '#8B0000'],    # heavy loss — dark red
            [0.4, '#E24B4A'],    # loss — red
            [0.5, '#EF9F27'],    # draw — amber
            [0.6, '#639922'],    # win — green
            [1.0, '#1a4d00'],    # heavy win — dark green
        ],

        range_color=[-1, 1],
        text_auto=False,
        labels={'color': 'Result'}
    )

    for i, team in enumerate(teams):
        fig.add_shape(
            type='rect',
            x0=i-0.5, x1=i+0.5,
            y0=i-0.5, y1=i+0.5,
            fillcolor='white',
            line_color='white'
        )

    for i, h in enumerate(teams):
        for j, a in enumerate(teams):
            if h != a and len(matrix[h][a]) > 0:
                text = '<br>'.join(matrix[h][a])
                fig.add_annotation(
                    x=j, y=i, text=text, showarrow=False,
                    font=dict(size=11, color='white')
                )

    fig.update_layout(
        coloraxis_showscale=False,
        xaxis_title='Away team',
        yaxis_title='Home team'
    )
    st.plotly_chart(fig, width='stretch')

elif chart == 'Round by round points':
    teams = summary['Team'].tolist()
    rounds = sorted(long['Round'].unique())

    if 'pts_round_idx' not in st.session_state:
        st.session_state.pts_round_idx = len(rounds) - 1

    def _pts_prev():
        idx = max(0, st.session_state.pts_round_idx - 1)
        st.session_state.pts_round_idx = idx
        st.session_state.pts_slider = rounds[idx]

    def _pts_next():
        idx = min(len(rounds) - 1, st.session_state.pts_round_idx + 1)
        st.session_state.pts_round_idx = idx
        st.session_state.pts_slider = rounds[idx]

    col1, col2, col3 = st.columns([1, 8, 1])
    with col1:
        st.button('◀', key='pts_prev', on_click=_pts_prev)
    with col2:
        selected_round = st.select_slider(
            'Round',
            options=rounds,
            key='pts_slider'
        )
        st.session_state.pts_round_idx = rounds.index(selected_round)
    with col3:
        st.button('▶', key='pts_next', on_click=_pts_next)

    filtered_rounds = [r for r in rounds if r <= selected_round]
    round_labels = [str(r) for r in filtered_rounds]

    rows = []
    for team in teams:
        first_round = long[long['Team'] == team]['Round'].min()
        cumulative = 0
        for r in filtered_rounds:
            if r < first_round:
                continue
            if r == first_round and team in carry_over:
                cumulative += carry_over[team].get('Pts', 0)
            game = long[(long['Team'] == team) & (long['Round'] == r)]
            if len(game) > 0:
                cumulative += game['Pts'].values[0]
            rows.append({'Team': team, 'Round': str(r), 'CumulativePts': cumulative})

    progression = pd.DataFrame(rows)
    fig = px.line(
        progression,
        x='Round',
        y='CumulativePts',
        color='Team',
        markers=True,
        color_discrete_map=color_map,
        labels={'CumulativePts': 'Points', 'Round': 'Round'}
    )
    fig.update_layout(xaxis=dict(type='category', categoryorder='array', categoryarray=round_labels))

    scale = len(filtered_rounds) / max(len(rounds), 1)
    logo_sizex = 0.6 * scale
    logo_sizey = 2.5 * scale

    logo_images = []
    for trace in fig.data:
        n = len(trace.x)
        if n == 0:
            continue
        logo = get_logo_base64(trace.name)
        if logo:
            sizes = [6] * n
            sizes[-1] = 0
            trace.update(marker=dict(size=sizes))
            last_x_idx = round_labels.index(trace.x[-1]) if trace.x[-1] in round_labels else len(round_labels) - 1
            logo_images.append(dict(
                source=logo, xref='x', yref='y',
                x=last_x_idx, y=trace.y[-1],
                sizex=logo_sizex, sizey=logo_sizey,
                xanchor='center', yanchor='middle',
                layer='above'
            ))
    if logo_images:
        fig.update_layout(images=logo_images)
    st.plotly_chart(fig, width='stretch')

elif chart == 'Round by round position':
    teams = summary['Team'].tolist()
    rounds = sorted(long['Round'].unique())

    if 'pos_round_idx' not in st.session_state:
        st.session_state.pos_round_idx = len(rounds) - 1

    def _pos_prev():
        idx = max(0, st.session_state.pos_round_idx - 1)
        st.session_state.pos_round_idx = idx
        st.session_state.pos_slider = rounds[idx]

    def _pos_next():
        idx = min(len(rounds) - 1, st.session_state.pos_round_idx + 1)
        st.session_state.pos_round_idx = idx
        st.session_state.pos_slider = rounds[idx]

    col1, col2, col3 = st.columns([1, 8, 1])
    with col1:
        st.button('◀', key='pos_prev', on_click=_pos_prev)
    with col2:
        selected_round = st.select_slider(
            'Round',
            options=rounds,
            key='pos_slider'
        )
        st.session_state.pos_round_idx = rounds.index(selected_round)
    with col3:
        st.button('▶', key='pos_next', on_click=_pos_next)

    filtered_rounds = [r for r in rounds if r <= selected_round]
    round_labels = [str(r) for r in filtered_rounds]

    rows = []
    cumulative = {team: 0 for team in teams}
    gd_cumulative = {team: 0 for team in teams}
    gf_cumulative = {team: 0 for team in teams}
    first_rounds = {team: long[long['Team'] == team]['Round'].min() for team in teams}

    for r in filtered_rounds:
        for team in teams:
            if r < first_rounds[team]:
                continue
            if r == first_rounds[team] and team in carry_over:
                cumulative[team] += carry_over[team].get('Pts', 0)
                gf_cumulative[team] += carry_over[team].get('GF', 0)
                gd_cumulative[team] += carry_over[team].get('GF', 0) - carry_over[team].get('GA', 0)

            game = long[(long['Team'] == team) & (long['Round'] == r)]
            if len(game) > 0:
                cumulative[team] += game['Pts'].values[0]
                gd_cumulative[team] += (game['GF'].values[0] - game['GA'].values[0])
                gf_cumulative[team] += game['GF'].values[0]

        active_teams = {t: cumulative[t] for t in teams if r >= first_rounds[t]}
        standings_this_round = pd.DataFrame({
            'Team': list(active_teams.keys()),
            'Pts': list(active_teams.values()),
            'GD': [gd_cumulative[t] for t in active_teams.keys()],
            'GF': [gf_cumulative[t] for t in active_teams.keys()],
        }).sort_values(['Pts', 'GD', 'GF'], ascending=False)

        for pos, team in enumerate(standings_this_round['Team'], start=1):
            rows.append({'Team': team, 'Round': str(r), 'Position': pos})

    progression = pd.DataFrame(rows)
    fig = px.line(
        progression,
        x='Round',
        y='Position',
        color='Team',
        markers=True,
        color_discrete_map=color_map,
        labels={'Position': 'Position', 'Round': 'Round'}
    )
    fig.update_layout(
        yaxis=dict(autorange='reversed', tickmode='linear', dtick=1),
        xaxis=dict(type='category', categoryorder='array', categoryarray=round_labels)
    )

    scale = len(filtered_rounds) / max(len(rounds), 1)
    logo_sizex = 0.6 * scale

    logo_images = []
    for trace in fig.data:
        n = len(trace.x)
        if n == 0:
            continue
        logo = get_logo_base64(trace.name)
        if logo:
            sizes = [6] * n
            sizes[-1] = 0
            trace.update(marker=dict(size=sizes))
            last_x_idx = round_labels.index(trace.x[-1]) if trace.x[-1] in round_labels else len(round_labels) - 1
            logo_images.append(dict(
                source=logo, xref='x', yref='y',
                x=last_x_idx, y=trace.y[-1],
                sizex=logo_sizex, sizey=0.8,
                xanchor='center', yanchor='middle',
                layer='above'
            ))
    if logo_images:
        fig.update_layout(images=logo_images)
    st.plotly_chart(fig, width='stretch')

elif chart == 'Home vs away':
    home_away = long.groupby(['Team', 'Home', 'Result']).size().reset_index(name='Count')
    home_away['Venue'] = home_away['Home'].map({True: 'Home', False: 'Away'})
    home_away['Result'] = pd.Categorical(home_away['Result'], categories=['W', 'D', 'L'], ordered=True)
    home_away['Venue'] = pd.Categorical(home_away['Venue'], categories=['Home', 'Away'], ordered=True)
    home_away = home_away.sort_values(['Team', 'Venue', 'Result'])

    fig = px.bar(
        home_away,
        x='Venue',
        y='Count',
        color='Result',
        barmode='stack',
        facet_col='Team',
        facet_col_wrap=4,
        facet_row_spacing=0.15,
        color_discrete_map={'W': '#639922', 'D': '#EF9F27', 'L': '#E24B4A'},
        labels={'Count': 'Games', 'Venue': ''}
    )
    fig.update_layout(
        showlegend=True,
        legend=dict(traceorder='normal'),
        yaxis=dict(range=[0, 7])
    )
    fig.for_each_annotation(lambda a: a.update(text=a.text.split('=')[-1]))
    st.plotly_chart(fig, width='stretch')

elif chart == 'Fixture tracker':
    teams = summary['Team'].tolist()
    selected_team = st.selectbox('Select team', teams)

    team_fixtures = tracker[
        (tracker['Home'] == selected_team) | (tracker['Away'] == selected_team)
    ].copy()

    team_fixtures['Opponent'] = team_fixtures.apply(
        lambda row: row['Away'] if row['Home'] == selected_team else row['Home'], axis=1
    )
    team_fixtures['Venue'] = team_fixtures.apply(
        lambda row: 'Home' if row['Home'] == selected_team else 'Away', axis=1
    )
    team_fixtures['OpponentStrength'] = team_fixtures.apply(
        lambda row: row['AwayStrength'] if row['Home'] == selected_team else row['HomeStrength'], axis=1
    )

    difficulty_colors = {
        1: ('#1a7a1a', '#ffffff'),
        2: ('#7fc97f', '#1a1a1a'),
        3: ('#f5f5f5', '#1a1a1a'),
        4: ('#f4a582', '#1a1a1a'),
        5: ('#d32f2f', '#ffffff'),
    }

    cols = st.columns(len(team_fixtures))
    for col, (_, row) in zip(cols, team_fixtures.iterrows()):
        if row['Opponent'] in ('BYE', 'TITANS'):
            label = row['Opponent']
            col.markdown(f"""
                <div style="
                    background-color: #555555;
                    color: white;
                    border-radius: 8px;
                    padding: 12px 8px;
                    text-align: center;
                    font-family: sans-serif;
                ">
                    <div style="font-size: 11px; margin-bottom: 4px;">Rd {int(row['Round'])}</div>
                    <div style="font-size: 15px; font-weight: 500; margin-bottom: 4px;">{label}</div>
                    <div style="font-size: 11px;">+3 pts</div>
                </div>
            """, unsafe_allow_html=True)
        else:
            bg, text = difficulty_colors[row['OpponentStrength']]
            col.markdown(f"""
                <div style="
                    background-color: {bg};
                    color: {text};
                    border-radius: 8px;
                    padding: 12px 8px;
                    text-align: center;
                    font-family: sans-serif;
                ">
                    <div style="font-size: 11px; margin-bottom: 4px;">Rd {int(row['Round'])}</div>
                    <div style="font-size: 15px; font-weight: 500; margin-bottom: 4px;">{row['Opponent']}</div>
                    <div style="font-size: 11px;">{row['Venue'] if 'Venue' in row else row['Home'] if row['Away'] == 'BYE' else 'Away'}</div>
                </div>
            """, unsafe_allow_html=True)

elif chart == 'Auto predictor':
    def project_table(played_df, predictions_df, df_byes):
        stats = {t: {'P':0,'W':0,'D':0,'L':0,'GF':0,'GA':0,'Pts':0,'BYE':0} for t in summary['Team']}

        # apply carry-over as starting offset
        for team, co in carry_over.items():
            if team in stats:
                stats[team]['Pts'] += co.get('Pts', 0)
                stats[team]['GF'] += co.get('GF', 0)
                stats[team]['GA'] += co.get('GA', 0)

        for _, row in played_df.iterrows():
            h, a = row['Home'], row['Away']
            h_in, a_in = h in stats, a in stats
            if not h_in and not a_in:
                continue
            if not h_in or not a_in:
                # One team not in standings (e.g., TITANS) — real team gets forfeit win
                winner = h if h_in else a
                stats[winner]['P'] += 1
                stats[winner]['W'] += 1
                stats[winner]['Pts'] += 3
                continue
            hg, ag = int(row['HG']), int(row['AG'])
            stats[h]['P'] += 1; stats[a]['P'] += 1
            stats[h]['GF'] += hg; stats[h]['GA'] += ag
            stats[a]['GF'] += ag; stats[a]['GA'] += hg
            if hg > ag:
                stats[h]['W'] += 1; stats[h]['Pts'] += 3; stats[a]['L'] += 1
            elif hg < ag:
                stats[a]['W'] += 1; stats[a]['Pts'] += 3; stats[h]['L'] += 1
            else:
                stats[h]['D'] += 1; stats[a]['D'] += 1
                stats[h]['Pts'] += 1; stats[a]['Pts'] += 1

        for _, row in df_byes.iterrows():
            team = row['Away'] if row['Home'] == 'BYE' else row['Home']
            if team in stats:
                stats[team]['Pts'] += 3
                stats[team]['BYE'] += 1

        for _, row in predictions_df.iterrows():
            h, a = row['Home'], row['Away']
            if h not in stats and a not in stats:
                continue
            hg, ag = int(row['HG']), int(row['AG'])
            # handle bye — only award points to the real team
            if h == 'BYE':
                stats[a]['Pts'] += 3
                stats[a]['BYE'] += 1
                continue
            if a == 'BYE':
                stats[h]['Pts'] += 3
                stats[h]['BYE'] += 1
                continue
        
            stats[h]['P'] += 1; stats[a]['P'] += 1
            stats[h]['GF'] += hg; stats[h]['GA'] += ag
            stats[a]['GF'] += ag; stats[a]['GA'] += hg
            if hg > ag:
                stats[h]['W'] += 1; stats[h]['Pts'] += 3; stats[a]['L'] += 1
            elif hg < ag:
                stats[a]['W'] += 1; stats[a]['Pts'] += 3; stats[h]['L'] += 1
            else:
                stats[h]['D'] += 1; stats[a]['D'] += 1
                stats[h]['Pts'] += 1; stats[a]['Pts'] += 1

        proj = pd.DataFrame(stats).T.reset_index()
        proj.columns = ['Team','P','W','D','L','GF','GA','Pts','BYE']
        proj['GD'] = proj['GF'] - proj['GA']
        proj = proj.sort_values(['Pts','GD','GF'], ascending=False).reset_index(drop=True)
        return proj

    remaining_rounds = sorted(auto_predictions['Round'].unique())
    selected_round = st.selectbox('Select round', remaining_rounds, format_func=lambda x: f'Round {x}')

    st.subheader(f'Round {selected_round} fixtures')
    round_fixtures = auto_predictions[auto_predictions['Round'] == selected_round][['Home', 'HG', 'AG', 'Away']]
    st.dataframe(round_fixtures, hide_index=True, width='stretch')

    st.subheader('Projected final table (including all predicted results)')
    st.dataframe(
        project_table(df, auto_predictions, df_byes)[['Team','P','W','D','L','BYE','GF','GA','GD','Pts']],
        hide_index=True,
        width='stretch'
    )

elif chart == 'Manual predictor':
    def project_table_manual(played_df, manual_scores, df_byes):
        stats = {t: {'P':0,'W':0,'D':0,'L':0,'GF':0,'GA':0,'Pts':0,'BYE':0} for t in summary['Team']}

        # apply carry-over as starting offset
        for team, co in carry_over.items():
            if team in stats:
                stats[team]['Pts'] += co.get('Pts', 0)
                stats[team]['GF'] += co.get('GF', 0)
                stats[team]['GA'] += co.get('GA', 0)

        for _, row in played_df.iterrows():
            h, a = row['Home'], row['Away']
            h_in, a_in = h in stats, a in stats
            if not h_in and not a_in:
                continue
            if not h_in or not a_in:
                winner = h if h_in else a
                stats[winner]['P'] += 1
                stats[winner]['W'] += 1
                stats[winner]['Pts'] += 3
                continue
            hg, ag = int(row['HG']), int(row['AG'])
            stats[h]['P'] += 1; stats[a]['P'] += 1
            stats[h]['GF'] += hg; stats[h]['GA'] += ag
            stats[a]['GF'] += ag; stats[a]['GA'] += hg
            if hg > ag:
                stats[h]['W'] += 1; stats[h]['Pts'] += 3; stats[a]['L'] += 1
            elif hg < ag:
                stats[a]['W'] += 1; stats[a]['Pts'] += 3; stats[h]['L'] += 1
            else:
                stats[h]['D'] += 1; stats[a]['D'] += 1
                stats[h]['Pts'] += 1; stats[a]['Pts'] += 1

        for _, row in df_byes.iterrows():
            team = row['Away'] if row['Home'] == 'BYE' else row['Home']
            if team in stats:
                stats[team]['Pts'] += 3
                stats[team]['BYE'] += 1

        for key, scores in manual_scores.items():
            hg, ag = scores
            h, a = key.split('_vs_')
            if h == 'BYE':
                if a in stats:
                    stats[a]['Pts'] += 3
                    stats[a]['BYE'] += 1
                continue
            if a == 'BYE':
                if h in stats:
                    stats[h]['Pts'] += 3
                    stats[h]['BYE'] += 1
                continue
            if h not in stats or a not in stats:
                continue
            stats[h]['P'] += 1; stats[a]['P'] += 1
            stats[h]['GF'] += hg; stats[h]['GA'] += ag
            stats[a]['GF'] += ag; stats[a]['GA'] += hg
            if hg > ag:
                stats[h]['W'] += 1; stats[h]['Pts'] += 3; stats[a]['L'] += 1
            elif hg < ag:
                stats[a]['W'] += 1; stats[a]['Pts'] += 3; stats[h]['L'] += 1
            else:
                stats[h]['D'] += 1; stats[a]['D'] += 1
                stats[h]['Pts'] += 1; stats[a]['Pts'] += 1

        proj = pd.DataFrame(stats).T.reset_index()
        proj.columns = ['Team','P','W','D','L','GF','GA','Pts','BYE']
        proj['GD'] = proj['GF'] - proj['GA']
        proj = proj.sort_values(['Pts','GD','GF'], ascending=False).reset_index(drop=True)
        return proj

    remaining_rounds = sorted(schedule[~schedule['Round'].isin(set(df['Round'].unique()))]['Round'].unique())
    selected_round = st.selectbox('Select round', remaining_rounds, format_func=lambda x: f'Round {x}')

    round_fixtures = schedule[schedule['Round'] == selected_round]

    if 'manual_scores' not in st.session_state:
        st.session_state.manual_scores = {}

    st.subheader(f'Round {selected_round} fixtures')

    for _, row in round_fixtures.iterrows():
        key = f"{row['Home']}_vs_{row['Away']}"
        
        if row['Home'] == 'BYE' or row['Away'] == 'BYE':
            team = row['Away'] if row['Home'] == 'BYE' else row['Home']
            st.markdown(f"**{team}** — BYE (+3 pts)")
            st.session_state.manual_scores[key] = (
                (0, 3) if row['Home'] == 'BYE' else (3, 0)
            )
            continue

        col1, col2, col3, col4, col5 = st.columns([2, 1, 0.5, 1, 2])

        with col1:
            st.markdown(f"<div style='text-align:right;padding-top:8px'>{row['Home']}</div>", unsafe_allow_html=True)
        with col2:
            hg = st.number_input(f'Home goals {key}', min_value=0, max_value=20, value=0, key=f'hg_{key}', label_visibility='hidden')
        with col3:
            st.markdown("<div style='text-align:center;padding-top:8px'>–</div>", unsafe_allow_html=True)
        with col4:
            ag = st.number_input(f'Away goals {key}', min_value=0, max_value=20, value=0, key=f'ag_{key}', label_visibility='hidden')
        with col5:
            st.markdown(f"<div style='padding-top:8px'>{row['Away']}</div>", unsafe_allow_html=True)

        st.session_state.manual_scores[key] = (hg, ag)

    st.subheader('Projected final table')
    st.dataframe(
        project_table_manual(df, st.session_state.manual_scores, df_byes)[['Team','P','W','D','L','BYE','GF','GA','GD','Pts']],
        hide_index=True,
        width='stretch'
    )

elif chart == 'Form tracker':
    n_games = st.radio('Games', [3, 5], horizontal=True)
    
    form_data = long.sort_values('Round').groupby('Team').tail(n_games).copy()
    
    result_colors = {'W': '#639922', 'D': '#EF9F27', 'L': '#E24B4A', 'BYE': '#555555'}
    result_text = {'W': 'white', 'D': '#1a1a1a', 'L': 'white', 'BYE': 'white'}
    
    teams_by_position = summary['Team'].tolist()

    form_results = []
    for pos, team in enumerate(teams_by_position, start=1):
        team_form = form_data[form_data['Team'] == team].sort_values('Round')
        form_pts = int(team_form['Pts'].sum())
        form_results.append({
            'team': team,
            'league_pos': pos,
            'form_pts': form_pts,
            'max_pts': n_games * 3,
            'form': team_form
        })

    form_results.sort(key=lambda x: x['form_pts'], reverse=True)
    for form_pos, result in enumerate(form_results, start=1):
        result['form_pos'] = form_pos
        result['pos_diff'] = result['league_pos'] - form_pos

    form_results.sort(key=lambda x: x['league_pos'])

    st.markdown("---")

    header_cols = st.columns([1, 2, 3, 1, 1, 1])
    with header_cols[0]:
        st.markdown("**Pos**")
    with header_cols[1]:
        st.markdown("**Team**")
    with header_cols[2]:
        st.markdown("**Form**")
    with header_cols[3]:
        st.markdown("**Pts**")
    with header_cols[4]:
        st.markdown("**Form Pos**")
    with header_cols[5]:
        st.markdown("**vs League**")

    st.markdown("---")

    for result in form_results:
        team = result['team']
        pos = result['league_pos']
        form_pts = result['form_pts']
        max_pts = result['max_pts']
        team_form = result['form']
        form_pos = result['form_pos']
        pos_diff = result['pos_diff']

        circles_html = "<div style='white-space:nowrap;padding-top:4px;'>"
        for _, game in team_form.iterrows():
            is_titans = 'TITANS' in str(game.get('Opponent', ''))
            if is_titans:
                circles_html += """<span style="
                        display:inline-flex;
                        align-items:center;
                        justify-content:center;
                        width:28px;height:28px;
                        border-radius:4px;
                        background:#ffffff;
                        color:#333;
                        font-size:10px;
                        font-weight:500;
                        margin-right:4px;
                    ">W</span>"""
            else:
                r = game['Result']
                bg = result_colors[r]
                tc = result_text[r]
                circles_html += f"""<span style="
                        display:inline-flex;
                        align-items:center;
                        justify-content:center;
                        width:28px;height:28px;
                        border-radius:50%;
                        background:{bg};
                        color:{tc};
                        font-size:11px;
                        font-weight:500;
                        margin-right:4px;
                    ">{r}</span>"""
        circles_html += "</div>"

        if pos_diff > 0:
            delta_html = f"<div style='padding-top:6px;color:#639922;font-weight:600'>▲ +{pos_diff}</div>"
        elif pos_diff < 0:
            delta_html = f"<div style='padding-top:6px;color:#E24B4A;font-weight:600'>▼ {pos_diff}</div>"
        else:
            delta_html = "<div style='padding-top:6px;color:#888'>➡ 0</div>"

        row_cols = st.columns([1, 2, 3, 1, 1, 1])
        with row_cols[0]:
            st.markdown(f"<div style='padding-top:6px'>{pos}</div>", unsafe_allow_html=True)
        with row_cols[1]:
            st.markdown(f"<div style='padding-top:6px'>{team}</div>", unsafe_allow_html=True)
        with row_cols[2]:
            st.markdown(circles_html, unsafe_allow_html=True)
        with row_cols[3]:
            st.markdown(f"<div style='padding-top:6px'>{form_pts}/{max_pts}</div>", unsafe_allow_html=True)
        with row_cols[4]:
            st.markdown(f"<div style='padding-top:6px'>{form_pos}</div>", unsafe_allow_html=True)
        with row_cols[5]:
            st.markdown(delta_html, unsafe_allow_html=True)

        st.markdown("---")

elif chart == 'Winning / losing margins':
    teams = summary['Team'].tolist()
    selected_team = st.selectbox('Select team', teams)

    team_games = long[long['Team'] == selected_team].copy()
    team_games['Margin'] = team_games['GF'] - team_games['GA']
    team_games['ResultLabel'] = team_games['Result'].map({'W': 'Win', 'D': 'Draw', 'L': 'Loss'})
    team_games['Color'] = team_games['Result'].map({'W': '#639922', 'D': '#EF9F27', 'L': '#E24B4A'})
    team_games['DisplayMargin'] = team_games.apply(
        lambda row: 0.3 if row['Result'] == 'D' else row['Margin'], axis=1
    )

    fig = px.bar(
        team_games.sort_values('Round'),
        x='Round',
        y='DisplayMargin',
        color='Result',
        color_discrete_map={'W': '#639922', 'D': '#EF9F27', 'L': '#E24B4A'},
        labels={'DisplayMargin': 'Goal margin', 'Round': 'Round'},
        hover_data={'Opponent': True, 'GF': True, 'GA': True, 'Result': False, 'Margin': True, 'DisplayMargin': False}
    )

    fig.add_hline(y=0, line_color='grey', line_width=1)
    fig.update_layout(
        xaxis=dict(tickmode='linear', dtick=1),
        showlegend=True
    )
    st.plotly_chart(fig, width='stretch')

    col1, col2, col3 = st.columns(3)
    wins = team_games[team_games['Result'] == 'W']
    losses = team_games[team_games['Result'] == 'L']

    with col1:
        avg_win = wins['Margin'].mean() if len(wins) > 0 else 0
        st.metric('Avg winning margin', f'+{avg_win:.1f}' if len(wins) > 0 else 'N/A')
    with col2:
        avg_loss = losses['Margin'].mean() if len(losses) > 0 else 0
        st.metric('Avg losing margin', f'{avg_loss:.1f}' if len(losses) > 0 else 'N/A')
    with col3:
        biggest_win = wins['Margin'].max() if len(wins) > 0 else 0
        st.metric('Biggest win', f'+{int(biggest_win)}' if len(wins) > 0 else 'N/A')

## fails to account for equal points
elif chart == 'Form vs position':
    n_games = st.radio('Form games', [3, 5], horizontal=True)

    form_data = long.sort_values('Round').groupby('Team').tail(n_games)
    form_pts = form_data.groupby('Team')['Pts'].sum().reset_index()
    form_pts.columns = ['Team', 'FormPts']

    combined = summary[['Team', 'Pts']].merge(form_pts, on='Team')
    combined['Position'] = combined['Pts'].rank(ascending=False, method='min').astype(int)
    combined['MaxFormPts'] = n_games * 3
    combined['FormPct'] = combined['FormPts'] / combined['MaxFormPts'] * 100

    fig = px.scatter(
        combined,
        x='Position',
        y='FormPts',
        text='Team',
        color='FormPts',
        color_continuous_scale=['#E24B4A', '#EF9F27', '#639922'],
        range_color=[0, n_games * 3],
        size_max=40,
        labels={
            'Position': 'Current league position',
            'FormPts': f'Points from last {n_games} games',
        }
    )

    avg_form = combined['FormPts'].mean()
    fig.add_hline(y=avg_form, line_dash='dash', line_color='grey', opacity=0.5,
                  annotation_text='Avg form', annotation_position='top right')

    fig.update_traces(textposition='top center')
    fig.update_layout(
        xaxis=dict(tickmode='linear', dtick=1, autorange='reversed'),
        yaxis=dict(tickmode='linear', dtick=1),
        coloraxis_showscale=False
    )
    st.plotly_chart(fig, width='stretch')

    st.subheader('Form table')
    form_table = combined.sort_values('FormPts', ascending=False).reset_index(drop=True)
    form_table.index += 1
    st.dataframe(
        form_table[['Team', 'Position', 'FormPts']].rename(columns={
            'Position': 'League pos',
            'FormPts': f'Last {n_games} pts'
        }),
        width='stretch'
    )