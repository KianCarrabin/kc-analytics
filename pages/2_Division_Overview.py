import streamlit as st
import pandas as pd
import plotly.express as px
import os
import base64
import itertools
from data import load_data, get_leagues, get_clubs, filter_league, make_long, make_summary, get_carry_over_stats, get_club_logo_path

st.set_page_config(page_title='Division Overview', layout='wide')

@st.cache_data
def load_cached_data():
    return load_data()

@st.cache_data
def build_all(df_raw):
    valid_leagues = get_leagues(df_raw)
    valid_set = set(valid_leagues)

    valid_played = df_raw[
        df_raw['Status'].isin(['PLAYED', 'FORFEITED']) &
        df_raw['League'].isin(valid_set)
    ]
    global_latest_date = valid_played['Date'].max() if not valid_played.empty else None

    overview_rows = []
    all_games = []
    this_week = []
    position_changes = []
    all_team_stats = []
    streaks = []
    home_wins = away_wins = draws = 0

    def run_streak(results, cond):
        return sum(1 for _ in itertools.takewhile(cond, reversed(results)))

    for league in valid_leagues:
        try:
            df, df_league, df_byes = filter_league(df_raw, league)
            if df.empty:
                continue
            long = make_long(df, df_byes)
            carry = get_carry_over_stats(df_raw, league)
            summary = make_summary(long, carry)
            if summary.empty:
                continue

            league_latest_date = df['Date'].max()

            # Overview rows (existing charts)
            for _, row in summary.iterrows():
                club = row['Team'].split()[0].split('-')[0]
                overview_rows.append({
                    'Club': club, 'Team': row['Team'], 'Division': league,
                    'PPG': row['PPG'], 'W': int(row['W']), 'D': int(row['D']), 'L': int(row['L']),
                    'GF': int(row['GF']), 'GA': int(row['GA']), 'GD': int(row['GD']),
                    'Pts': int(row['Pts']), 'P': int(row['P']),
                })

            # Season games (skip TITANS)
            for _, row in df.iterrows():
                h, a = str(row['Home']), str(row['Away'])
                if 'TITANS' in h or 'TITANS' in a:
                    continue
                hg, ag = int(row['HG']), int(row['AG'])
                all_games.append({
                    'league': league, 'round': int(row['Round']), 'date': row['Date'],
                    'home': h, 'hg': hg, 'ag': ag, 'away': a,
                    'margin': abs(hg - ag), 'total_goals': hg + ag, 'max_score': max(hg, ag),
                })
                if hg > ag: home_wins += 1
                elif ag > hg: away_wins += 1
                else: draws += 1

            # Team stats
            curr_pos = {str(r['Team']): i + 1 for i, (_, r) in enumerate(summary.iterrows())}
            for pos, (_, row) in enumerate(summary.iterrows(), 1):
                team = str(row['Team'])
                rounds = max(int(row['P']) + int(row['BYE']), 1)
                all_team_stats.append({
                    'league': league, 'team': team, 'pos': pos,
                    'P': int(row['P']), 'W': int(row['W']), 'D': int(row['D']), 'L': int(row['L']),
                    'GF': int(row['GF']), 'GA': int(row['GA']), 'Pts': int(row['Pts']),
                    'PPG': float(row['PPG']),
                    'GF_pg': int(row['GF']) / rounds, 'GA_pg': int(row['GA']) / rounds,
                })

            # Streaks
            tl = long[~long['Team'].str.contains('TITANS', na=False)].sort_values('Round')
            for team in curr_pos:
                results = tl[tl['Team'] == team]['Result'].tolist()
                ws = run_streak(results, lambda r: r == 'W')
                ub = run_streak(results, lambda r: r in ('W', 'D', 'BYE'))
                streaks.append({'team': team, 'league': league, 'win_streak': ws, 'unbeaten': ub})

            # This week
            if global_latest_date is None or league_latest_date != global_latest_date:
                continue
            week_df = df[df['Date'] == global_latest_date]
            if week_df.empty:
                continue
            latest_round = int(week_df['Round'].max())
            week_games = week_df[week_df['Round'] == latest_round]

            prev_long = long[long['Round'] < latest_round]
            pre_pos = {}
            if not prev_long.empty:
                try:
                    ps = make_summary(prev_long, carry)
                    pre_pos = {str(r['Team']): i + 1 for i, (_, r) in enumerate(ps.iterrows())}
                except Exception:
                    pass

            for _, row in week_games.iterrows():
                h, a = str(row['Home']), str(row['Away'])
                if 'TITANS' in h or 'TITANS' in a:
                    continue
                hg, ag = int(row['HG']), int(row['AG'])
                this_week.append({
                    'league': league, 'round': latest_round,
                    'home': h, 'hg': hg, 'ag': ag, 'away': a,
                    'margin': abs(hg - ag), 'total_goals': hg + ag, 'max_score': max(hg, ag),
                    'home_pre_pos': pre_pos.get(h), 'away_pre_pos': pre_pos.get(a),
                })

            for team, cp in curr_pos.items():
                pp = pre_pos.get(team)
                if pp:
                    position_changes.append({
                        'team': team, 'league': league,
                        'change': pp - cp, 'prev': pp, 'curr': cp,
                    })

        except Exception:
            continue

    climbers = sorted([x for x in position_changes if x['change'] > 0], key=lambda x: -x['change'])[:5]
    fallers  = sorted([x for x in position_changes if x['change'] < 0], key=lambda x:  x['change'])[:5]

    return {
        'overview': pd.DataFrame(overview_rows),
        'global_latest_date': global_latest_date,
        'this_week': this_week,
        'climbers': climbers,
        'fallers': fallers,
        'all_games': all_games,
        'all_team_stats': all_team_stats,
        'streaks': streaks,
        'home_wins': home_wins, 'away_wins': away_wins, 'draws': draws,
    }


# Overrides for weeks that span non-contiguous dates or need custom labels.
# Keys are the display label; values are the exact dates to include.
GAMEWEEK_DATE_RANGES = {
    'Week 0 — 22 March 2026':           ['2026-03-22'],
    'Week 1 — 27 March–2 April 2026':   ['2026-03-27', '2026-03-28', '2026-03-29', '2026-04-02'],
    'Week 9 (Washout) — 28–31 May 2026':['2026-05-28', '2026-05-29', '2026-05-30', '2026-05-31'],
}

@st.cache_data
def get_this_week_data(df_raw, dates_key):
    selected_dates = pd.to_datetime(dates_key.split('|'))
    min_date = selected_dates.min()
    max_date = selected_dates.max()
    valid_leagues = get_leagues(df_raw)

    this_week = []
    position_changes = []

    for league in valid_leagues:
        try:
            df, df_league, df_byes = filter_league(df_raw, league)
            if df.empty:
                continue

            week_df = df[df['Date'].isin(selected_dates)]
            if week_df.empty:
                continue

            carry = get_carry_over_stats(df_raw, league)

            # pre-gameweek: all results strictly before the earliest date in this week
            df_pre = df[df['Date'] < min_date]
            df_byes_pre = df_byes[df_byes['Date'] < min_date]
            pre_pos = {}
            if not df_pre.empty:
                long_pre = make_long(df_pre, df_byes_pre)
                if not long_pre.empty:
                    ps = make_summary(long_pre, carry)
                    pre_pos = {str(r['Team']): i + 1 for i, (_, r) in enumerate(ps.iterrows())}

            # post-gameweek: all results up to and including the latest date in this week
            df_post = df[df['Date'] <= max_date]
            df_byes_post = df_byes[df_byes['Date'] <= max_date]
            long_post = make_long(df_post, df_byes_post)
            summary_post = make_summary(long_post, carry)
            curr_pos = {str(r['Team']): i + 1 for i, (_, r) in enumerate(summary_post.iterrows())}

            for _, row in week_df.iterrows():
                h, a = str(row['Home']), str(row['Away'])
                if 'TITANS' in h or 'TITANS' in a:
                    continue
                hg, ag = int(row['HG']), int(row['AG'])
                this_week.append({
                    'league': league, 'round': int(row['Round']),
                    'home': h, 'hg': hg, 'ag': ag, 'away': a,
                    'margin': abs(hg - ag), 'total_goals': hg + ag, 'max_score': max(hg, ag),
                    'home_pre_pos': pre_pos.get(h), 'away_pre_pos': pre_pos.get(a),
                    'forfeit': str(row.get('Status', '')) == 'FORFEITED',
                })

            for team, cp in curr_pos.items():
                pp = pre_pos.get(team)
                if pp:
                    position_changes.append({
                        'team': team, 'league': league,
                        'change': pp - cp, 'prev': pp, 'curr': cp,
                    })

        except Exception:
            continue

    climbers = sorted([x for x in position_changes if x['change'] > 0], key=lambda x: -x['change'])[:5]
    fallers  = sorted([x for x in position_changes if x['change'] < 0], key=lambda x:  x['change'])[:5]

    return {'this_week': this_week, 'climbers': climbers, 'fallers': fallers}


df_raw = load_cached_data()

with st.spinner('Loading division data...'):
    data = build_all(df_raw)

df_all = data['overview']
all_games = data['all_games']
all_team_stats = data['all_team_stats']
qualified = [t for t in all_team_stats if t['P'] >= 5]

# ─────────────────────────────────────────────────────────────
# Title and top-level metrics
# ─────────────────────────────────────────────────────────────

st.title('Division overview')

c1, c2, c3, c4 = st.columns(4)
c1.metric('Total divisions', df_all['Division'].nunique())
c2.metric('Total teams', len(df_all))
c3.metric('Total goals', int(df_all['GF'].sum()))
c4.metric('Total games played', int(df_all['P'].sum() // 2))

# ─────────────────────────────────────────────────────────────
# Section 1 — This week
# ─────────────────────────────────────────────────────────────

st.markdown('---')

played_df = df_raw[df_raw['Status'] == 'PLAYED'].copy()
played_df['Date'] = pd.to_datetime(played_df['Date'], dayfirst=True)
played_df['week_start'] = played_df['Date'] - pd.to_timedelta(played_df['Date'].dt.weekday, unit='D')

# dates claimed by manual overrides — auto-detected weeks that contain these are suppressed
_override_date_strs = {d for dates in GAMEWEEK_DATE_RANGES.values() for d in dates}
_override_dates_ts  = pd.to_datetime(list(_override_date_strs))

# auto-detect weeks and collect their actual played dates as the cache key
_week_date_map = (
    played_df.groupby('week_start')['Date']
    .apply(lambda x: sorted(x.dt.strftime('%Y-%m-%d').unique()))
    .to_dict()
)

entries = []
for week_start, date_strs in _week_date_map.items():
    if any(d in _override_date_strs for d in date_strs):
        continue  # suppressed by an override
    parsed = pd.to_datetime(date_strs)
    rnd = int(played_df[played_df['Date'].isin(parsed)]['Round'].mode()[0])
    lo, hi = parsed.min(), parsed.max()
    date_part = (
        f"{lo.strftime('%-d %b')}–{hi.strftime('%-d %b %Y')}"
        if lo.month != hi.month
        else f"{lo.strftime('%-d')}–{hi.strftime('%-d %B %Y')}"
    )
    entries.append({'label': f"Week {rnd} — {date_part}", 'min_date': lo, 'dates_key': '|'.join(date_strs)})

for label, date_strs in GAMEWEEK_DATE_RANGES.items():
    parsed = pd.to_datetime(date_strs)
    entries.append({'label': label, 'min_date': parsed.min(), 'dates_key': '|'.join(sorted(date_strs))})

entries.sort(key=lambda e: e['min_date'], reverse=True)
label_to_key = {e['label']: e['dates_key'] for e in entries}

selected_label = st.selectbox('Select gameweek', [e['label'] for e in entries])
dates_key = label_to_key[selected_label]

with st.spinner('Loading gameweek data...'):
    week_data = get_this_week_data(df_raw, dates_key)

this_week = week_data['this_week']

st.subheader(selected_label.replace(' — ', ' · '))

def stat_card(value, label, sub=''):
    sub_html = f'<div style="font-size:12px;color:#666;margin-top:4px;">{sub}</div>' if sub else ''
    return f"""
<div style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;padding:18px 16px;height:100%;">
  <div style="font-size:28px;font-weight:700;line-height:1.1;">{value}</div>
  <div style="font-size:13px;color:#aaa;margin-top:6px;">{label}</div>
  {sub_html}
</div>"""

if not this_week:
    st.info('No results for this gameweek.')
else:
    # ── Row 1: game highlights ──
    g_margin  = max(this_week, key=lambda x: x['margin'])
    g_scoring = max(this_week, key=lambda x: x['total_goals'])
    g_score   = max(this_week, key=lambda x: x['max_score'])

    upsets = []
    for g in this_week:
        hp, ap = g['home_pre_pos'], g['away_pre_pos']
        if hp is None or ap is None:
            continue
        if g['hg'] > g['ag'] and hp > ap:
            upsets.append({**g, 'winner': g['home'], 'loser': g['away'],
                           'winner_rank': hp, 'loser_rank': ap, 'size': hp - ap})
        elif g['ag'] > g['hg'] and ap > hp:
            upsets.append({**g, 'winner': g['away'], 'loser': g['home'],
                           'winner_rank': ap, 'loser_rank': hp, 'size': ap - hp})

    top_scorer_game = g_score
    top_scorer_team = top_scorer_game['home'] if top_scorer_game['hg'] == top_scorer_game['max_score'] else top_scorer_game['away']

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(stat_card(
            f"{g_margin['hg']}–{g_margin['ag']}",
            f"Largest winning margin · {g_margin['league']}",
            f"{g_margin['home']} vs {g_margin['away']} · {g_margin['margin']} goal margin",
        ), unsafe_allow_html=True)
    with col2:
        st.markdown(stat_card(
            f"{g_scoring['hg']}–{g_scoring['ag']}",
            f"Highest scoring game · {g_scoring['league']}",
            f"{g_scoring['home']} vs {g_scoring['away']} · {g_scoring['total_goals']} goals",
        ), unsafe_allow_html=True)
    with col3:
        if upsets:
            u = max(upsets, key=lambda x: x['size'])
            st.markdown(stat_card(
                f"{u['hg']}–{u['ag']}",
                f"Biggest upset · {u['league']}",
                f"{u['winner']} beat {u['loser']} · Rank {u['winner_rank']} beat Rank {u['loser_rank']}",
            ), unsafe_allow_html=True)
        else:
            st.markdown(stat_card('—', 'Biggest upset', 'No upsets this round'), unsafe_allow_html=True)

    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    col4, col5, col6 = st.columns(3)

    # Most goals by one team
    with col4:
        st.markdown(stat_card(
            str(top_scorer_game['max_score']),
            f"Most goals by one team · {top_scorer_game['league']}",
            f"{top_scorer_team} — {top_scorer_game['home']} {top_scorer_game['hg']}–{top_scorer_game['ag']} {top_scorer_game['away']}",
        ), unsafe_allow_html=True)

    # Climbers
    with col5:
        if week_data['climbers']:
            items = ''.join(
                f'<div style="padding:4px 0;font-size:13px;">'
                f'<span style="color:#639922;font-weight:600;">▲ {c["change"]}</span>'
                f'&nbsp;&nbsp;<strong>{c["team"]}</strong>'
                f'<span style="color:#666;font-size:11px;"> ({c["league"]}) #{c["prev"]}→#{c["curr"]}</span>'
                f'</div>'
                for c in week_data['climbers']
            )
            st.markdown(f"""
<div style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;padding:18px 16px;">
  <div style="font-size:13px;color:#aaa;margin-bottom:8px;">Table climbers</div>
  {items}
</div>""", unsafe_allow_html=True)
        else:
            st.markdown(stat_card('—', 'Table climbers', 'No changes this round'), unsafe_allow_html=True)

    # Fallers
    with col6:
        if week_data['fallers']:
            items = ''.join(
                f'<div style="padding:4px 0;font-size:13px;">'
                f'<span style="color:#E24B4A;font-weight:600;">▼ {abs(f["change"])}</span>'
                f'&nbsp;&nbsp;<strong>{f["team"]}</strong>'
                f'<span style="color:#666;font-size:11px;"> ({f["league"]}) #{f["prev"]}→#{f["curr"]}</span>'
                f'</div>'
                for f in week_data['fallers']
            )
            st.markdown(f"""
<div style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;padding:18px 16px;">
  <div style="font-size:13px;color:#aaa;margin-bottom:8px;">Table fallers</div>
  {items}
</div>""", unsafe_allow_html=True)
        else:
            st.markdown(stat_card('—', 'Table fallers', 'No changes this round'), unsafe_allow_html=True)

    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # Clean sheets
    clean_sheets = []
    for g in this_week:
        if g.get('forfeit', False):
            continue
        if g['ag'] == 0:
            clean_sheets.append({'Team': g['home'], 'Division': g['league'],
                                  'Opponent': g['away'], 'Score': f"{g['hg']}–{g['ag']}"})
        if g['hg'] == 0:
            clean_sheets.append({'Team': g['away'], 'Division': g['league'],
                                  'Opponent': g['home'], 'Score': f"{g['ag']}–{g['hg']}"})

    if not clean_sheets:
        st.info('No clean sheets this week.')
    else:
        clean_df = pd.DataFrame(clean_sheets)
        total = len(clean_df)
        st.metric('Clean sheets this week', total)

        grouped = (
            clean_df.groupby('Division')
            .agg(Teams=('Team', lambda x: ', '.join(sorted(x))), Count=('Team', 'count'))
            .reset_index()
            .sort_values('Division')
        )
        st.dataframe(grouped[['Division', 'Teams', 'Count']], hide_index=True, width='stretch')

        with st.expander(f'See all {total} clean sheets with detail'):
            for division in sorted(clean_df['Division'].unique()):
                div_clean = clean_df[clean_df['Division'] == division]
                st.caption(f"**{division}**")
                for _, row in div_clean.iterrows():
                    st.markdown(f"**{row['Team']}** {row['Score']} {row['Opponent']}")

# ─────────────────────────────────────────────────────────────
# Section 2 — Season records
# ─────────────────────────────────────────────────────────────

st.markdown('---')
st.subheader('Season records')

def record_card(value, label, subtitle, color='#378ADD', **_):
    return f"""
    <div style="
        background:#1e1e1e;
        border:1px solid #333;
        border-left:4px solid {color};
        border-radius:8px;
        padding:16px;
        height:100%;
        margin-bottom:4px;
    ">
        <div style="font-size:26px;font-weight:700;color:white;line-height:1.1;">{value}</div>
        <div style="font-size:13px;color:#aaa;margin-top:6px;">{label}</div>
        <div style="font-size:11px;color:#666;margin-top:4px;">{subtitle}</div>
    </div>"""

def _tied_subtitle(items, team_key, league_key):
    pairs = [f"{s[team_key]} ({s[league_key]})" for s in items]
    if len(pairs) <= 2:
        return ' · '.join(pairs)
    return ' · '.join(pairs[:2]) + f' +{len(pairs) - 2} more'

if all_games:
    g  = max(all_games, key=lambda x: x['total_goals'])
    g2 = max(all_games, key=lambda x: x['margin'])
    g3 = max(all_games, key=lambda x: x['max_score'])
    scorer3 = g3['home'] if g3['hg'] == g3['max_score'] else g3['away']

    att  = max(qualified, key=lambda x: x['GF_pg']) if qualified else None
    def_ = min(qualified, key=lambda x: x['GA_pg']) if qualified else None
    ppg  = max(qualified, key=lambda x: x['PPG'])   if qualified else None

    max_ws_val = max((s['win_streak'] for s in data['streaks']), default=0)
    max_ub_val = max((s['unbeaten']   for s in data['streaks']), default=0)
    ws_tied = [s for s in data['streaks'] if s['win_streak'] == max_ws_val]
    ub_tied = [s for s in data['streaks'] if s['unbeaten']   == max_ub_val]

    ppg_tied = []
    max_ppg_val = 0.0
    if ppg:
        max_ppg_val = ppg['PPG']
        ppg_tied = [q for q in qualified if q['PPG'] >= max_ppg_val - 0.001]

    total = data['home_wins'] + data['away_wins'] + data['draws']
    hw = data['home_wins'] / total * 100 if total else 0
    aw = data['away_wins'] / total * 100 if total else 0
    dw = data['draws']     / total * 100 if total else 0

    records = [
        dict(icon='', color='#378ADD',
             value=f"{g['hg']}–{g['ag']}",
             label='Highest scoring game',
             subtitle=f"{g['home']} vs {g['away']} · {g['league']} · Rd {g['round']}"),
        dict(icon='', color='#E24B4A',
             value=f"{g2['hg']}–{g2['ag']}",
             label='Largest winning margin',
             subtitle=f"{g2['home']} vs {g2['away']} · {g2['league']} · Rd {g2['round']}"),
        dict(icon='', color='#639922',
             value=str(g3['max_score']),
             label='Most goals by one team',
             subtitle=f"{scorer3} · {g3['league']} · Rd {g3['round']}"),
        dict(icon='', color='#1a4d8f',
             value=f"{def_['GA_pg']:.2f} GA/game" if def_ else '—',
             label='Best defensive record',
             subtitle=f"{def_['team']} · {def_['league']}" if def_ else ''),
        dict(icon='', color='#EF9F27',
             value=f"{att['GF_pg']:.2f} GF/game" if att else '—',
             label='Best attacking record',
             subtitle=f"{att['team']} · {att['league']}" if att else ''),
        dict(icon='', color='#FFD700',
             value=f"{max_ppg_val:.2f} PPG",
             label='Highest points per game',
             subtitle=_tied_subtitle(ppg_tied, 'team', 'league') if ppg_tied else ''),
        dict(icon='', color='#639922',
             value=f"{max_ws_val} games",
             label='Longest win streak',
             subtitle=_tied_subtitle(ws_tied, 'team', 'league') if max_ws_val > 0 else 'No win streaks'),
        dict(icon='', color='#7F77DD',
             value=f"{max_ub_val} games",
             label='Longest unbeaten run',
             subtitle=_tied_subtitle(ub_tied, 'team', 'league') if max_ub_val > 0 else 'No unbeaten runs'),
        dict(icon='', color='#888780',
             value=f"{hw:.0f}% / {aw:.0f}% / {dw:.0f}%",
             label='Home / Away / Draw %',
             subtitle='Across all divisions this season'),
    ]

    cols = st.columns(3)
    for i, rec in enumerate(records):
        with cols[i % 3]:
            st.markdown(record_card(**rec), unsafe_allow_html=True)
            st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Existing charts
# ─────────────────────────────────────────────────────────────

st.markdown('---')
st.subheader('Top 10 highest scoring teams')
top_scorers = df_all.nlargest(10, 'GF')[['Team', 'Division', 'GF', 'GA', 'GD', 'P']]
top_scorers['GF/game'] = (top_scorers['GF'] / top_scorers['P']).round(2)
st.dataframe(top_scorers, hide_index=True, width='stretch')

st.subheader('Top 10 best defensive records')
best_defence = df_all.nsmallest(10, 'GA')[['Team', 'Division', 'GA', 'GF', 'P']]
best_defence['GA/game'] = (best_defence['GA'] / best_defence['P']).round(2)
st.dataframe(best_defence, hide_index=True, width='stretch')

st.subheader('Top 10 teams by points per game')
top_ppg = df_all.nlargest(10, 'PPG')[['Team', 'Division', 'PPG', 'W', 'D', 'L', 'Pts', 'P']]
st.dataframe(top_ppg, hide_index=True, width='stretch')

st.subheader('Average goals per game by division')
df_all['GoalsPerGame'] = df_all['GF'] / df_all['P']
div_goals = df_all.groupby('Division')['GoalsPerGame'].mean().reset_index()
div_goals.columns = ['Division', 'Avg goals per game']
div_goals = div_goals.sort_values('Avg goals per game', ascending=False)

fig = px.bar(
    div_goals,
    x='Division',
    y='Avg goals per game',
    color='Avg goals per game',
    color_continuous_scale=['#378ADD', '#639922'],
    labels={'Division': '', 'Avg goals per game': 'Avg goals per game'},
)
fig.update_layout(coloraxis_showscale=False, xaxis_tickangle=-45)
st.plotly_chart(fig, width='stretch')
