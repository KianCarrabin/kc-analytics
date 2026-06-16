import streamlit as st
import pandas as pd
import plotly.express as px
import os
import base64
import re
from data import load_data, get_clubs, filter_league, get_leagues, make_long, make_summary, get_carry_over_stats, get_club_logo_path

st.set_page_config(page_title='Club View', layout='wide')

@st.cache_data
def load_cached_data():
    return load_data()

df_raw = load_cached_data()

clubs = get_clubs(df_raw)
leagues = get_leagues(df_raw)

def get_logo(club):
    path = get_club_logo_path(club)
    if path:
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('utf-8')
        return f'data:image/png;base64,{data}'
    return None

# build club summary across all divisions
@st.cache_data
def build_club_leaderboard(df_raw):
    rows = []
    for league in get_leagues(df_raw):
        try:
            df, df_league, df_byes = filter_league(df_raw, league)
            long = make_long(df, df_byes)
            carry = get_carry_over_stats(df_raw, league)
            summary = make_summary(long, carry)
            for _, row in summary.iterrows():
                # extract club code — first word only
                club = row['Team'].split()[0].split('-')[0]
                rows.append({
                    'Club': club,
                    'Team': row['Team'],
                    'Division': league,
                    'PPG': row['PPG'],
                    'W': int(row['W']),
                    'GF': int(row['GF']),
                    'Pts': int(row['Pts']),
                    'P': int(row['P']),
                })
        except:
            pass
    return pd.DataFrame(rows)
all_teams_df = build_club_leaderboard(df_raw)

club_agg = all_teams_df.groupby('Club').agg(
    Teams=('Division', 'count'),
    AvgPPG=('PPG', 'mean'),
    TotalWins=('W', 'sum'),
    TotalGF=('GF', 'sum'),
    TotalPts=('Pts', 'sum'),
).reset_index().sort_values('AvgPPG', ascending=False).reset_index(drop=True)

club_agg['AvgPPG'] = club_agg['AvgPPG'].round(2)
club_agg.index += 1

view = st.sidebar.radio('View', ['Leaderboard', 'Club drill-down'])

if view == 'Leaderboard':
    st.title('Club leaderboard')
    
    show_all = st.toggle('Show all clubs', value=False)
    display_df = club_agg if show_all else club_agg.head(10)
    
    import base64

    def get_logo_html(club):
        path = get_club_logo_path(club)
        if path:
            with open(path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')
            return f'<img src="data:image/png;base64,{data}" style="width:28px;height:28px;border-radius:50%;object-fit:cover;margin-right:6px;vertical-align:middle;">'
        return ''

    rows_html = ''
    for i, row in display_df.iterrows():
        logo = get_logo_html(row['Club'])
        rows_html += f"""
        <tr>
            <td style="padding:8px 6px;color:#888">{i}</td>
            <td style="padding:8px 6px;white-space:nowrap;">{logo}{row['Club']}</td>
            <td style="padding:8px 6px;text-align:center;">{row['Teams']}</td>
            <td style="padding:8px 6px;text-align:center;">{row['AvgPPG']}</td>
            <td style="padding:8px 6px;text-align:center;">{int(row['TotalWins'])}</td>
            <td style="padding:8px 6px;text-align:center;">{int(row['TotalGF'])}</td>
            <td style="padding:8px 6px;text-align:center;">{int(row['TotalPts'])}</td>
        </tr>
        """

    table_html = f"""
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
            <tr style="border-bottom:1px solid #333;color:#888;font-size:11px;text-transform:uppercase;">
                <th style="padding:8px 6px;text-align:left;"></th>
                <th style="padding:8px 6px;text-align:left;">Club</th>
                <th style="padding:8px 6px;">Teams</th>
                <th style="padding:8px 6px;">Avg PPG</th>
                <th style="padding:8px 6px;">Total wins</th>
                <th style="padding:8px 6px;">Total goals</th>
                <th style="padding:8px 6px;">Total pts</th>
            </tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
    """

    height = 80 + len(display_df) * 68
    st.iframe(f"""
    <html>
    <body style="background:transparent;margin:0;padding:0;font-family:sans-serif;color:#e0e0e0;">
    {table_html}
    </body>
    </html>
    """, height=height)

elif view == 'Club drill-down':
    selected_club = st.sidebar.selectbox('Select club', clubs)

    logo = get_logo(selected_club)
    col1, col2 = st.columns([1, 8])
    with col1:
        if logo:
            st.markdown(f'<img src="{logo}" style="width:64px;height:64px;border-radius:50%;object-fit:cover;">', unsafe_allow_html=True)
    with col2:
        st.title(selected_club)

    club_teams = all_teams_df[all_teams_df['Club'] == selected_club].copy()

    if club_teams.empty:
        st.info(f'No results found for {selected_club}.')
        st.stop()

    # get full stats for each team — use exact team name to avoid double-counting
    # when a club has multiple teams in the same division
    rows = []
    seen = set()
    for _, team_row in club_teams.iterrows():
        league = team_row['Division']
        t = team_row['Team']
        if (league, t) in seen:
            continue
        seen.add((league, t))
        try:
            df, df_league, df_byes = filter_league(df_raw, league)
            long = make_long(df, df_byes)
            carry = get_carry_over_stats(df_raw, league)
            summary = make_summary(long, carry)
            if t not in summary['Team'].values:
                continue
            row = summary[summary['Team'] == t].iloc[0]
            pos = summary[summary['Team'] == t].index[0] + 1
            n_teams = len(summary)

            # form
            form_data = long.sort_values('Round').groupby('Team').tail(5)
            team_form = form_data[form_data['Team'] == t].sort_values('Round')
            squares = ''
            for _, g in team_form.iterrows():
                if g['Result'] == 'W': squares += '🟢'
                elif g['Result'] == 'D': squares += '🟡'
                elif g['Result'] == 'L': squares += '🔴'
                elif g['Result'] == 'BYE': squares += '⬜'

            rows.append({
                'Team': t,
                'Division': league,
                'Pos': f'{pos}/{n_teams}',
                'P': int(row['P']),
                'W': int(row['W']),
                'D': int(row['D']),
                'L': int(row['L']),
                'GF': int(row['GF']),
                'GA': int(row['GA']),
                'GD': int(row['GD']),
                'Pts': int(row['Pts']),
                'PPG': round(row['PPG'], 2),
                'Form': squares,
            })
        except:
            pass

    if not rows:
        st.info(f'No results found for {selected_club}.')
        st.stop()

    club_df = pd.DataFrame(rows).sort_values(['Division', 'Team']).reset_index(drop=True)

    # unambiguous label for every row — always Team (Division)
    club_df['Label'] = club_df.apply(
        lambda row: f"{row['Team']} ({row['Division']})", axis=1
    )

    # exclude combined divisions (e.g. W21AB, W40AB) whose team names embed a
    # division token, making labels like "EEAG W21A (W21AB)" misleading
    club_df_clean = club_df[
        ~club_df['Division'].str.match(r'.*[A-Z]{2}$', na=False)
    ].copy()

    # metrics
    best_df = club_df_clean if not club_df_clean.empty else club_df
    best_team_row = best_df.loc[best_df['PPG'].idxmax()]
    best_team_label = f"{best_team_row['Team']} ({best_team_row['Division']})"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric('Teams', len(club_df))
    col2.metric('Total wins', club_df['W'].sum())
    col3.metric('Total goals', club_df['GF'].sum())
    col4.metric('Best team', best_team_label)

    st.markdown('---')

    # table
    st.subheader('Performance by team')
    st.dataframe(
        club_df[['Label', 'Pos', 'P', 'W', 'D', 'L', 'GF', 'GA', 'GD', 'Pts', 'PPG', 'Form']],
        hide_index=True,
        width='stretch'
    )

    # PPG chart — Label is always unique so every team gets its own bar
    st.subheader('Points per game by team')
    if not club_df_clean.empty:
        fig = px.bar(
            club_df_clean.sort_values('PPG', ascending=True),
            x='PPG',
            y='Label',
            orientation='h',
            color='PPG',
            color_continuous_scale=['#E24B4A', '#EF9F27', '#639922'],
            labels={'PPG': 'Points per game', 'Label': ''},
        )
        fig.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig, width='stretch')
    else:
        st.info('No chart data available.')