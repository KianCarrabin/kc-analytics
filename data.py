import pandas as pd
import re
import os
import requests
import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson as poisson_dist

def load_data(filepath='ssfa_full.csv'):
    df = pd.read_csv(filepath)
    df.columns = ['Round', 'Date', 'Time', 'League', 'Home', 'HG', 'AG', 'Away', 'Status', 'Venue']

    df['Status'] = df['Status'].apply(lambda x: re.sub(r'<[^>]+>', '', str(x)).strip())
    df['Date'] = pd.to_datetime(df['Date'], dayfirst=True)

    df['HomeClub'] = df['Home'].apply(lambda x: x.split()[0] if pd.notna(x) else None)
    df['AwayClub'] = df['Away'].apply(lambda x: x.split()[0] if pd.notna(x) else None)

    return df

def get_leagues(df):
    def is_valid_league(league):
        # only filter age-based leagues starting with U or W
        match = re.match(r'^[UW](\d+)', league)
        if match:
            age = int(match.group(1))
            return age >= 12
        return True  # keep AM, AW, O35, O45, PLW, PLM etc as-is

    all_leagues = sorted(df['League'].unique())
    return [l for l in all_leagues if is_valid_league(l)]


def filter_league(df, league):
    df_league = df[df['League'] == league].copy()

    league_name = df_league['League'].iloc[0]
    def shorten_name(name):
        return name.replace(' ' + league_name, '').strip()

    df_league['Home'] = df_league['Home'].apply(shorten_name)
    df_league['Away'] = df_league['Away'].apply(shorten_name)

    df_played = df_league[df_league['Status'].isin(['PLAYED', 'FORFEITED'])].copy()

    # separate byes from real fixtures
    bye_mask = (df_played['Home'] == 'BYE') | (df_played['Away'] == 'BYE')
    df_byes = df_played[bye_mask].copy()
    df_played = df_played[~bye_mask].copy()

    # exclude regraded-out teams only for leagues with formal regrading tracked in REGRADE_ADJUSTMENTS
    # leagues without adjustments may have cross-division filler teams in early rounds whose games still count
    has_regrading = bool(REGRADE_ADJUSTMENTS.get(CURRENT_SEASON, {}).get(league))
    max_round = df_played['Round'].max()
    if has_regrading and max_round >= 5:
        all_teams = pd.concat([
            df_played[['Round', 'Home']].rename(columns={'Home': 'Team'}),
            df_played[['Round', 'Away']].rename(columns={'Away': 'Team'})
        ])
        last_round_per_team = all_teams.groupby('Team')['Round'].max()
        regraded_out = last_round_per_team[last_round_per_team <= 4].index.tolist()
        df_played = df_played[
            ~df_played['Home'].isin(regraded_out) &
            ~df_played['Away'].isin(regraded_out)
        ]

    df_played['HG'] = pd.to_numeric(df_played['HG'], errors='coerce').fillna(0).astype(int)
    df_played['AG'] = pd.to_numeric(df_played['AG'], errors='coerce').fillna(0).astype(int)
    df_played['Result'] = df_played.apply(
        lambda row: 'W' if row['HG'] > row['AG'] else ('L' if row['HG'] < row['AG'] else 'D'), axis=1
    )
    df_played['GD'] = df_played['HG'] - df_played['AG']

    # TITANS always forfeit — non-TITANS opponent wins regardless of recorded score
    titans_home = df_played['Home'].str.contains('TITANS', na=False)
    titans_away = df_played['Away'].str.contains('TITANS', na=False)
    df_played.loc[titans_home, 'Result'] = 'L'
    df_played.loc[titans_away, 'Result'] = 'W'

    return df_played, df_league, df_byes


def get_clubs(df):
    clubs = set(df['HomeClub'].dropna()) | set(df['AwayClub'].dropna())
    return sorted(clubs - {'BYE'})


def make_long(df, df_byes=None):
    home = df[['Round', 'Date', 'Home', 'HG', 'AG', 'Away', 'Result']].copy()
    home.columns = ['Round', 'Date', 'Team', 'GF', 'GA', 'Opponent', 'Result']
    home['Home'] = True

    away = df[['Round', 'Date', 'Away', 'AG', 'HG', 'Home', 'Result']].copy()
    away.columns = ['Round', 'Date', 'Team', 'GF', 'GA', 'Opponent', 'Result']
    away['Home'] = False
    away['Result'] = away['Result'].map({'W': 'L', 'L': 'W', 'D': 'D'})

    long = pd.concat([home, away], ignore_index=True)
    long['Pts'] = long['Result'].map({'W': 3, 'D': 1, 'L': 0})

    # add bye rows — 3 pts, no goals
    if df_byes is not None and len(df_byes) > 0:
        bye_rows = []
        for _, row in df_byes.iterrows():
            if 'TITANS' in str(row['Home']) or row['Home'] == 'BYE':
                team = row['Away']
            else:
                team = row['Home']
            # skip if team also contains TITANS
            if 'TITANS' in str(team):
                continue
            bye_rows.append({
                'Round': row['Round'],
                'Date': row['Date'],
                'Team': team,
                'GF': 0,
                'GA': 0,
                'Opponent': 'BYE',
                'Home': False,
                'Result': 'BYE',
                'Pts': 3
            })
        long = pd.concat([long, pd.DataFrame(bye_rows)], ignore_index=True)

    long['IsBye'] = long['Opponent'] == 'BYE'

    return long

REGRADE_ADJUSTMENTS = {
    '2026_winter': {
        'AW03': {'GEOR-1': {'PAJ': 4, 'GAJ': 1}},
        'AW04': {'LIPI': {'PAJ': 4, 'GAJ': 4}},
        'AW05': {'GWAB': {'PAJ': 4, 'GAJ': 10}},
        'AW06': {'GYME': {'PAJ': 4, 'GAJ': 5}},
        'AW07': {'BANG': {'PAJ': 4, 'GAJ': 2}},
        'AW08': {'CSEA': {'PAJ': 4, 'GAJ': 2}},
        'U12B': {'EEAG-1': {'PAJ': 4, 'GAJ': 2}},
        'U12C': {'NSUT-2': {'PAJ': 8, 'GAJ': 10}},
        'U12D': {'EEAG': {'PAJ': 4, 'GAJ': 5}},
        'U13B': {'LIPI-1': {'PAJ': 4, 'GAJ': 4}},
        'U15B': {'BARD': {'PAJ': 8, 'GAJ': 19}},
        'U15C': {'CRSL': {'PAJ': 4, 'GAJ': 10}},
        'U16B': {'LIPI': {'PAJ': 8, 'GAJ': 15}},
        'U16C': {'BANG': {'PAJ': 4, 'GAJ': 7}},
        'U18C': {'GPOI': {'PAJ': 4, 'GAJ': 3}},
        'W15B': {'CSEA': {'PAJ': 8, 'GAJ': 8}},
        'W15C': {'COMO': {'PAJ': 4, 'GAJ': 4}},
    }
}

# GA corrections for teams whose goals-against were inflated by a filler team
# that played in rounds 1-4 before being removed. Values applied from GW4 onwards.
GOAL_CORRECTIONS = {
    '2026_winter': {
        'U12A': {
            'LIPI-1': {'GF': -6},
            'MENA':   {'GF': -3},
            'GEOR':   {'GF': -4},
            'COMO':   {'GF': -3},
        },
        'U13A': {
            'LIPI': {'GF': -9},
            'SYLV': {'GF': -13},
            'GYME': {'GF': -11},
            'GPOI': {'GF': -2},
        },
        'AW02': {
            'MART-2': {'GF': -1},
            'GYME-1': {'GF': -7},
            'CSEA':   {'GF': -3},
            'BOSC':   {'GF': -4},
        },
    }
}

CURRENT_SEASON = '2026_winter'

def get_carry_over_stats(df_raw, league):
    try:
        adjustments = REGRADE_ADJUSTMENTS.get(CURRENT_SEASON, {}).get(league, {})
        corrections = GOAL_CORRECTIONS.get(CURRENT_SEASON, {}).get(league, {})

        carry_over = {}
        for team, adj in adjustments.items():
            carry_over[team] = {
                'W': 0, 'D': 0, 'L': 0,
                'GF': adj.get('GAJ', 0), 'GA': 0,
                'Pts': adj.get('PAJ', 0),
                'P': 0, 'BYE': 0
            }

        for team, corr in corrections.items():
            if team in carry_over:
                for stat, val in corr.items():
                    carry_over[team][stat] = carry_over[team].get(stat, 0) + val
            else:
                entry = {'W': 0, 'D': 0, 'L': 0, 'GF': 0, 'GA': 0, 'Pts': 0, 'P': 0, 'BYE': 0}
                for stat, val in corr.items():
                    entry[stat] = val
                carry_over[team] = entry

        return carry_over

    except Exception as e:
        print(f"carry_over error: {e}")
        return {}

EXCLUDED_TEAMS = ['TITANS']

def make_summary(long, carry_over=None):
    long = long[~long['Team'].str.contains('TITANS', na=False)].copy()

    # Exclude cross-division filler teams that only appear in rounds 1-4
    max_round = long['Round'].max()
    if pd.notna(max_round) and max_round >= 5:
        active_teams = set(long[long['Round'] >= 5]['Team'].unique())
        if carry_over:
            active_teams |= set(carry_over.keys())
        long = long[long['Team'].isin(active_teams)].copy()
    summary = long.groupby('Team').agg(
        P=('IsBye', lambda x: (~x).sum()),
        W=('Result', lambda x: (x == 'W').sum()),
        D=('Result', lambda x: (x == 'D').sum()),
        L=('Result', lambda x: (x == 'L').sum()),
        BYE=('IsBye', lambda x: x.sum()),
        GF=('GF', 'sum'),
        GA=('GA', 'sum'),
        Pts=('Pts', 'sum')
    ).reset_index()

    if carry_over:
        for team, stats in carry_over.items():
            mask = summary['Team'] == team
            if mask.any():
                for col in ['W', 'D', 'L', 'GF', 'GA', 'Pts', 'P', 'BYE']:
                    summary.loc[mask, col] += stats.get(col, 0)

    summary['GD'] = summary['GF'] - summary['GA']
    summary = summary.sort_values(['Pts', 'GD', 'GF'], ascending=False).reset_index(drop=True)

    rounds_played = summary['P'] + summary['BYE']
    summary['GF_per_game'] = summary['GF'] / rounds_played
    summary['GA_per_game'] = summary['GA'] / rounds_played
    summary['PPG'] = summary['Pts'] / rounds_played

    n = len(summary)
    def get_color(pos):
        if pos == 0: return '#FFD700'
        if pos == 1: return '#C0C0C0'
        if pos == 2: return '#CD7F32'
        if pos < n // 2: return '#E24B4A'
        return '#378ADD'

    summary['Color'] = [get_color(i) for i in range(n)]

    return summary

def make_form(long, n=5):
    form = long.sort_values('Round').groupby('Team').tail(n).copy()
    form_summary = form.groupby('Team').agg(
        FormPts=('Pts', 'sum'),
        FormGF=('GF', 'sum'),
        FormGA=('GA', 'sum'),
        FormGames=('Round', 'count')
    ).reset_index()
    form_summary['FormGF_per_game'] = form_summary['FormGF'] / form_summary['FormGames']
    form_summary['FormGA_per_game'] = form_summary['FormGA'] / form_summary['FormGames']
    return form_summary

def predict_score(home, away, summary, form_summary, df):
    # safety check — if either team not in summary or form_summary, return default
    if (home not in summary['Team'].values or 
        away not in summary['Team'].values or
        home not in form_summary['Team'].values or
        away not in form_summary['Team'].values):
        return 1, 1

    
    def get_stats(team, opponent):
        s = summary[summary['Team'] == team].iloc[0]
        f = form_summary[form_summary['Team'] == team].iloc[0]

        h2h = df[
            ((df['Home'] == team) & (df['Away'] == opponent)) |
            ((df['Away'] == team) & (df['Home'] == opponent))
        ]

        if len(h2h) > 0:
            h2h_gf = h2h.apply(lambda r: r['HG'] if r['Home'] == team else r['AG'], axis=1).mean()
            h2h_ga = h2h.apply(lambda r: r['AG'] if r['Home'] == team else r['HG'], axis=1).mean()
        else:
            h2h_gf = s['GF_per_game']
            h2h_ga = s['GA_per_game']

        gf = (s['GF_per_game'] * 0.3) + (f['FormGF_per_game'] * 0.3) + (h2h_gf * 0.4)
        ga = (s['GA_per_game'] * 0.3) + (f['FormGA_per_game'] * 0.3) + (h2h_ga * 0.4)

        return gf, ga

    h_gf, h_ga = get_stats(home, away)
    a_gf, a_ga = get_stats(away, home)

    home_bonus = 0.2
    hg = round((h_gf + a_ga) / 2 + home_bonus)
    ag = round((a_gf + h_ga) / 2)

    return max(0, int(hg)), max(0, int(ag))


def fit_poisson_model(df, decay=0.0):
    """
    Fit a Dixon-Coles style Poisson regression model.
    Each team gets an attack and defence strength parameter.
    Expected goals: exp(intercept + attack_home - defence_away + home_adv)

    decay: exponential time-decay rate per round (0 = no decay).
           Each game is weighted exp(-decay * rounds_ago) so recent
           games matter more. Typical useful range: 0.0–0.3.

    Returns a params dict, or None if too few games/teams.
    """
    teams = sorted(
        t for t in set(df['Home'].unique()) | set(df['Away'].unique())
        if 'TITANS' not in str(t) and t != 'BYE'
    )
    n = len(teams)
    if n < 2:
        return None

    games = df[
        ~df['Home'].str.contains('TITANS', na=False) &
        ~df['Away'].str.contains('TITANS', na=False) &
        (df['Home'] != 'BYE') & (df['Away'] != 'BYE')
    ].copy()

    if len(games) < n:
        return None

    idx = {t: i for i, t in enumerate(teams)}

    max_round = games['Round'].max()
    weights = np.exp(-decay * (max_round - games['Round'].values))

    home_arr = games['Home'].values
    away_arr = games['Away'].values
    hg_arr   = games['HG'].values.astype(int)
    ag_arr   = games['AG'].values.astype(int)
    hi_arr   = np.array([idx.get(h, -1) for h in home_arr])
    ai_arr   = np.array([idx.get(a, -1) for a in away_arr])
    valid    = (hi_arr >= 0) & (ai_arr >= 0)

    # params layout: [home_adv, intercept, attack_1..n-1, defence_0..n-1]
    # attack[0] fixed at 0 for identifiability
    def neg_ll(params):
        home_adv = params[0]
        intercept = params[1]
        attack = np.concatenate([[0.0], params[2:n + 1]])
        defence = params[n + 1:]
        lh = np.exp(intercept + attack[hi_arr[valid]] - defence[ai_arr[valid]] + home_adv)
        la = np.exp(intercept + attack[ai_arr[valid]] - defence[hi_arr[valid]])
        ll = weights[valid] * (
            poisson_dist.logpmf(hg_arr[valid], lh) +
            poisson_dist.logpmf(ag_arr[valid], la)
        )
        return -ll.sum()

    x0 = np.zeros(1 + 1 + (n - 1) + n)
    x0[0] = 0.1
    x0[1] = np.log(max(games['HG'].mean(), 0.5))

    result = minimize(neg_ll, x0, method='L-BFGS-B', options={'maxiter': 2000, 'ftol': 1e-12})

    p = result.x
    return {
        'teams': teams,
        'idx': idx,
        'home_adv': p[0],
        'intercept': p[1],
        'attack': np.concatenate([[0.0], p[2:n + 1]]),
        'defence': p[n + 1:],
        'decay': decay,
    }


def predict_score_poisson(home, away, model):
    """Predict a scoreline using a fitted Poisson model."""
    if model is None:
        return 1, 1
    hi = model['idx'].get(home)
    ai = model['idx'].get(away)
    if hi is None or ai is None:
        return 1, 1
    lh = np.exp(model['intercept'] + model['attack'][hi] - model['defence'][ai] + model['home_adv'])
    la = np.exp(model['intercept'] + model['attack'][ai] - model['defence'][hi])
    return max(0, round(lh)), max(0, round(la))


def make_auto_predictions(schedule, df, df_byes, summary, form_summary, poisson_model=None):
    played_rounds = set(df['Round'].unique())
    remaining = schedule[~schedule['Round'].isin(played_rounds)].copy()

    # filter out all TITANS variants
    remaining = remaining[
        (~remaining['Home'].str.contains('TITANS', na=False)) &
        (~remaining['Away'].str.contains('TITANS', na=False))
    ].copy()

    predictions = []
    for _, row in remaining.iterrows():
        h, a = row['Home'], row['Away']
        if h == 'BYE' or a == 'BYE':
            predictions.append({
                'Round': row['Round'],
                'Home': h,
                'Away': a,
                'HG': 0 if h == 'BYE' else 3,
                'AG': 0 if a == 'BYE' else 3,
            })
        else:
            if poisson_model is not None:
                hg, ag = predict_score_poisson(h, a, poisson_model)
            else:
                hg, ag = predict_score(h, a, summary, form_summary, df)
            predictions.append({
                'Round': row['Round'],
                'Home': h,
                'Away': a,
                'HG': hg,
                'AG': ag,
            })

    return pd.DataFrame(predictions).sort_values('Round')


def make_full_schedule(df, df_league, df_byes, summary, df_raw=None, league=None):
    n_teams = len(summary)
    cycle_length = n_teams - 1

    day = df_league['Date'].dt.day_name().iloc[0]
    total_rounds = 17 if day == 'Sunday' else 18

    current_teams = set(summary['Team'].tolist())

    # Use all available fixtures from df_league (played, published, forfeited)
    avail = df_league[df_league['Status'].isin(['PLAYED', 'FORFEITED', 'PUBLISHED'])][['Round', 'Home', 'Away']].copy()

    # Add played bye rows (df_byes may include TITANS fixtures not in PUBLISHED)
    if df_byes is not None and len(df_byes) > 0:
        avail = pd.concat([avail, df_byes[['Round', 'Home', 'Away']]], ignore_index=True)
        avail = avail.drop_duplicates(subset=['Round', 'Home', 'Away'])

    fixture_teams = (set(avail['Home'].unique()) | set(avail['Away'].unique())) - {'BYE'}

    # Detect regraded-out teams (in fixtures but not in current standings, excluding TITANS)
    titans_in_data = {t for t in fixture_teams if 'TITANS' in str(t)}
    regraded_out = fixture_teams - current_teams - titans_in_data

    # Detect regraded-in teams (in current standings but absent from rounds 1-4)
    teams_in_early = (
        set(avail[avail['Round'] <= 4]['Home'].unique()) |
        set(avail[avail['Round'] <= 4]['Away'].unique())
    ) - {'BYE'}
    regraded_in = current_teams - teams_in_early

    # Build substitution map
    team_sub = {}

    # TITANS → carry-over team
    if titans_in_data and league:
        adjustments = REGRADE_ADJUSTMENTS.get(CURRENT_SEASON, {}).get(league, {})
        if adjustments:
            for carry_team in adjustments.keys():
                if carry_team in current_teams:
                    for t in titans_in_data:
                        team_sub[t] = carry_team
                    break

    # Regraded-out → regraded-in substitution
    if regraded_out and regraded_in:
        for i, old in enumerate(sorted(regraded_out)):
            ri_list = sorted(regraded_in)
            if i < len(ri_list):
                team_sub[old] = ri_list[i]

    def sub(name):
        return team_sub.get(name, name)

    # If regraded-in teams exist, use post-regrade rounds (5+) for cycle1 to avoid
    # BYE/team-count mismatch from the pre-regrade rounds 1-4
    cycle_start = 5 if regraded_in else 1
    cycle_end = cycle_start + cycle_length - 1

    cycle_source = avail[(avail['Round'] >= cycle_start) & (avail['Round'] <= cycle_end)].copy()
    cycle_source['Home'] = cycle_source['Home'].apply(sub)
    cycle_source['Away'] = cycle_source['Away'].apply(sub)
    cycle_source = cycle_source[cycle_source['Home'] != cycle_source['Away']].copy()
    cycle_source['Round'] = cycle_source['Round'] - cycle_start + 1
    cycle1 = cycle_source[['Round', 'Home', 'Away']].drop_duplicates().copy()

    # Only substitute BYEs in the generated schedule when TITANS were the replaced team
    # (natural BYEs from odd-team-count comps must remain as BYEs)
    regraded_in_for_bye = {team_sub[t] for t in titans_in_data if t in team_sub} & current_teams

    all_fixtures = []
    for r in range(1, total_rounds + 1):
        cycle_pos = (r - 1) % (cycle_length * 2)

        if cycle_pos < cycle_length:
            source_round = cycle_pos + 1
            home_away = False
        else:
            source_round = cycle_pos - cycle_length + 1
            home_away = True

        round_fixtures = cycle1[cycle1['Round'] == source_round]
        for _, row in round_fixtures.iterrows():
            home = row['Away'] if home_away else row['Home']
            away = row['Home'] if home_away else row['Away']

            # BYE → regraded-in team (handles TITANS-era BYE slots)
            if regraded_in_for_bye:
                replacement = list(regraded_in_for_bye)[0]
                if home == 'BYE':
                    home = replacement
                elif away == 'BYE':
                    away = replacement

            all_fixtures.append({'Round': r, 'Home': home, 'Away': away})

    return pd.DataFrame(all_fixtures), total_rounds


def make_fixture_tracker(schedule, df, df_byes, summary, total_rounds):
    played_rounds = set(df['Round'].unique())
    bye_rounds = set(df_byes['Round'].unique()) if df_byes is not None else set()

    positions = {row['Team']: i + 1 for i, row in summary.iterrows()}

    def strength(pos):
        if pos <= 2: return 5
        if pos <= 4: return 4
        if pos <= 6: return 3
        return 2

    remaining = schedule[~schedule['Round'].isin(played_rounds)].copy()
    remaining['HomeStrength'] = remaining['Home'].map(
        lambda x: 0 if x in ('BYE', 'TITANS') else strength(positions.get(x, 4))
    )
    remaining['AwayStrength'] = remaining['Away'].map(
        lambda x: 0 if x in ('BYE', 'TITANS') else strength(positions.get(x, 4))
    )

    # add upcoming byes
    if df_byes is not None and len(df_byes) > 0:
        upcoming_byes = df_byes[~df_byes['Round'].isin(played_rounds | bye_rounds)].copy()
        for _, row in upcoming_byes.iterrows():
            team = row['Away'] if row['Home'] == 'BYE' else row['Home']
            remaining = pd.concat([remaining, pd.DataFrame([{
                'Round': row['Round'],
                'Home': team,
                'Away': 'BYE',
                'HomeStrength': 0,
                'AwayStrength': 0,
            }])], ignore_index=True)

    return remaining.sort_values('Round')


def get_age_groups(df):
    leagues = get_leagues(df)
    
    def extract_age_group(league):
        # for leagues like AM03, AW02 — strip the number suffix
        match = re.match(r'^([A-Z]+)\d+([A-Z]*)$', league)
        if match:
            prefix = match.group(1)
            suffix = match.group(2)
            # AM and AW are adult comps — group by prefix only
            if prefix in ('AM', 'AW'):
                return prefix
        # for U21B, U18A etc — extract U21, U18 etc
        match = re.match(r'^([UW]\d+)', league)
        if match:
            return match.group(1)
        # for O35A, O45B etc — extract O35, O45
        match = re.match(r'^(O\d+)', league)
        if match:
            return match.group(1)
        # for PLW, PLM, PLR — group as PL
        if league.startswith('PL'):
            return 'PL'
        return league

    age_groups = sorted(set([extract_age_group(l) for l in leagues]))
    return age_groups


def get_grades(df, age_group):
    leagues = get_leagues(df)
    if age_group in ('AM', 'AW'):
        return sorted([l for l in leagues if l.startswith(age_group)])
    if age_group == 'PL':
        return sorted([l for l in leagues if l.startswith('PL')])
    return sorted([l for l in leagues if l.startswith(age_group)])

def make_movement(long, summary, carry_over=None):
    teams = summary['Team'].tolist()
    rounds = sorted(long['Round'].unique())
    
    if len(rounds) < 2:
        return {team: 0 for team in teams}
    
    prev_rounds = rounds[:-1]
    prev_long = long[long['Round'].isin(prev_rounds)]
    
    prev_summary = prev_long.groupby('Team').agg(
        Pts=('Pts', 'sum'),
        GF=('GF', 'sum'),
        GA=('GA', 'sum')
    ).reset_index()
    prev_summary['GD'] = prev_summary['GF'] - prev_summary['GA']

    # apply carry over to previous summary too
    if carry_over:
        for team, stats in carry_over.items():
            mask = prev_summary['Team'] == team
            if mask.any():
                prev_summary.loc[mask, 'Pts'] += stats.get('Pts', 0)
                prev_summary.loc[mask, 'GF'] += stats.get('GF', 0)
                prev_summary.loc[mask, 'GD'] += stats.get('GF', 0) - stats.get('GA', 0)

    prev_summary = prev_summary.sort_values(['Pts', 'GD', 'GF'], ascending=False).reset_index(drop=True)
    prev_positions = {row['Team']: i + 1 for i, row in prev_summary.iterrows()}
    curr_positions = {row['Team']: i + 1 for i, row in summary.iterrows()}
    
    movement = {}
    for team in teams:
        if team in prev_positions:
            movement[team] = prev_positions[team] - curr_positions[team]
        else:
            movement[team] = 0
    
    return movement

_LOGOS_DIR = os.path.join(os.path.dirname(__file__), 'assets', 'logos')

def get_club_logo_path(club):
    path = os.path.join(_LOGOS_DIR, f'{club}.png')
    return path if os.path.exists(path) else None

CLUB_COLORS = {
    'BANG': '#E24B4A',
    'BARD': '#1a4d8f',
    'BBAY': '#00BCD4',
    'BOSC': '#1565C0',
    'BUND': '#8D6E63',
    'COMO': '#FFC107',
    'CRSL': '#FFD700',
    'CSEA': '#2E7D32',
    'ECRU': '#FF7043',
    'EEAG': '#F57C00',
    'GEOR': '#FF8F00',
    'GPOI': '#9C27B0',
    'GWAB': '#4A148C',
    'GYME': '#00695C',
    'HEAT': '#B71C1C',
    'KIRR': '#D32F2F',
    'LIPI': '#1B5E20',
    'LOFT': '#004D40',
    'MART': '#880E4F',
    'MENA': '#4A235A',
    'MIRA': '#01579B',
    'NCAR': '#006064',
    'NSUT': '#37474F',
    'STPA': '#1A237E',
    'SYLV': '#33691E',
    'TITANS': '#BF360C',
}

def get_team_color(team):
    club = team.split('-')[0].strip()
    base = CLUB_COLORS.get(club, '#888780')

    if '-' in team:
        suffix = team.split('-')[-1].strip()
        if suffix == '1':
            return base
        elif suffix == '2':
            # lighten by blending with white
            r = int(base[1:3], 16)
            g = int(base[3:5], 16)
            b = int(base[5:7], 16)
            r = min(255, int(r + (255 - r) * 0.4))
            g = min(255, int(g + (255 - g) * 0.4))
            b = min(255, int(b + (255 - b) * 0.4))
            return f'#{r:02x}{g:02x}{b:02x}'

    return base


VENUE_COORDS = {
    '5 Sports Caringbah': (-34.03119, 151.11692),
    'Anzac 1': (-34.05785, 151.00651),
    'Anzac 2': (-34.05785, 151.00651),
    'Anzac 3': (-34.05785, 151.00651),
    'Box Road 1': (-34.02203, 151.09233),
    'Box Road 2': (-34.02203, 151.09233),
    'Box Road 3': (-34.02203, 151.09233),
    'Boystown Oval 1': (-34.0714035, 151.0090088),
    'Boystown Oval 2': (-34.0714035, 151.0090088),
    'Buckle 1': (-34.01251, 151.00285),
    'Buckle 2': (-34.01251, 151.00285),
    'Coachwood Oval': (-34.02512, 151.1848),
    'Forest Road': (-34.0397734, 151.0663362),
    'Grays Point Oval 1': (-34.02512, 151.1848),
    'Grays Point Oval 2': (-34.02512, 151.1848),
    'Greenhills 1': (-34.02512, 151.1848),
    'Greenhills 2': (-34.02512, 151.1848),
    'Harrie Dening 1': (-34.02512, 151.1848),
    'Harrie Dening 2': (-34.02512, 151.1848),
    'Jannali 1': (-34.02051, 151.06273),
    'Jannali 2': (-34.02051, 151.06273),
    'Kareela 2': (-34.02504, 151.08594),
    'Kareela 3': (-34.02495, 151.08595),
    'Kareela 4': (-34.02618, 151.08463),
    'Kingswood Road 1': (-34.0464348, 151.0267361),
    'Kingswood Road 2': (-34.0464348, 151.0267361),
    'Lakewood 1': (-34.0082604, 151.048246),
    'Lakewood 2': (-34.0082604, 151.048246),
    'Lilli Pilli Oval': (-34.02512, 151.1848),
    'North Caringbah Oval': (-34.037673, 151.12279),
    'Oyster Bay 1': (-34.0055567, 151.0831649),
    'Oyster Bay 2': (-34.0055567, 151.0831649),
    'Preston Park': (-34.06928, 151.01248),
    'Ridge 1': (-34.027496, 150.995008),
    'Ridge 2': (-34.027496, 150.995008),
    'Ridge 3': (-34.0374819, 151.0005707),
    'Ridge 4': (-34.0374819, 151.0005707),
    'Ridge 5': (-34.0374819, 151.0005707),
    'Ridge 6': (-34.0374819, 151.0005707),
    'Seymour Shaw 1': (-34.03085, 151.10132),
    'Seymour Shaw 2': (-34.03085, 151.10132),
    'Seymour Shaw Stadium': (-34.03085, 151.10132),
    'Solander 1': (-34.03774, 151.13667),
    'Solander 2': (-34.03774, 151.13667),
    'Sutherland Oval 1': (-34.02863, 151.05382),
    'Sutherland Oval 2': (-34.02863, 151.05382),
    'Woolooware 1': (-34.0490086, 151.1420135),
    'Woolooware 2': (-34.0490086, 151.1420135),
    'Woronora Heights 1': (-34.02512, 151.1848),
}

WEATHER_DESCRIPTIONS = {
    0: ('Clear', '☀️'),
    1: ('Mainly clear', '🌤️'),
    2: ('Partly cloudy', '⛅'),
    3: ('Overcast', '☁️'),
    45: ('Fog', '🌫️'),
    48: ('Icy fog', '🌫️'),
    51: ('Light drizzle', '🌦️'),
    53: ('Drizzle', '🌦️'),
    55: ('Heavy drizzle', '🌦️'),
    56: ('Freezing drizzle', '🌨️'),
    57: ('Heavy freezing drizzle', '🌨️'),
    61: ('Light rain', '🌧️'),
    63: ('Rain', '🌧️'),
    65: ('Heavy rain', '🌧️'),
    66: ('Freezing rain', '🌨️'),
    67: ('Heavy freezing rain', '🌨️'),
    71: ('Light snow', '❄️'),
    73: ('Snow', '❄️'),
    75: ('Heavy snow', '❄️'),
    77: ('Snow grains', '🌨️'),
    80: ('Light showers', '🌧️'),
    81: ('Showers', '🌧️'),
    82: ('Heavy showers', '🌧️'),
    85: ('Snow showers', '🌨️'),
    86: ('Heavy snow showers', '🌨️'),
    95: ('Thunderstorm', '⛈️'),
    96: ('Thunderstorm with hail', '⛈️'),
    99: ('Thunderstorm with hail', '⛈️'),
}

_weather_cache = {}

def get_weather(venue, date, time_str):
    coords = VENUE_COORDS.get(str(venue))
    if not coords:
        return None

    lat, lon = coords
    date_str = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else str(date)[:10]
    cache_key = (lat, lon, date_str, time_str)

    if cache_key not in _weather_cache:
        url = (
            f'https://archive-api.open-meteo.com/v1/archive'
            f'?latitude={lat}&longitude={lon}'
            f'&start_date={date_str}&end_date={date_str}'
            f'&hourly=temperature_2m,precipitation,weathercode'
            f'&timezone=Australia%2FSydney'
        )
        result = None
        try:
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if 'hourly' in data:
                    result = data
        except Exception:
            pass
        _weather_cache[cache_key] = result

    data = _weather_cache[cache_key]
    if not data or 'hourly' not in data:
        return None

    try:
        match = re.search(r'(\d{1,2}):(\d{2})', str(time_str))
        if not match:
            return None
        kickoff_hour = int(match.group(1))
        kickoff_min = int(match.group(2))
        kickoff_mins = kickoff_hour * 60 + kickoff_min

        times = data['hourly']['time']
        temps = data['hourly']['temperature_2m']
        codes = data['hourly']['weathercode']

        def hour_mins(t):
            return int(t[11:13]) * 60

        best_idx = min(range(len(times)), key=lambda i: abs(hour_mins(times[i]) - kickoff_mins))

        temp = temps[best_idx]
        code = int(codes[best_idx]) if codes[best_idx] is not None else None
        desc, emoji = WEATHER_DESCRIPTIONS.get(code, (f'Code {code}', '🌡️'))

        return {'temp': temp, 'condition': desc, 'emoji': emoji}
    except Exception:
        return None
