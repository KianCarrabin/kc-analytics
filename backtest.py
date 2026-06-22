"""
Backtest: compare Poisson model vs old weighted model.
For each played round, fits on all prior rounds, predicts current round, scores vs actuals.
Run with: python3 backtest.py
"""
import pandas as pd
import numpy as np
from data import (
    load_data, get_leagues, filter_league, make_long, make_summary,
    make_form, get_carry_over_stats, fit_poisson_model,
    predict_score_poisson, predict_score,
)

def result_label(hg, ag):
    if hg > ag: return 'H'
    if ag > hg: return 'A'
    return 'D'

DECAY_VALUES = [0.0, 0.05, 0.1, 0.15, 0.2, 0.3]

def run_backtest(df_raw, min_prior_rounds=4):
    records = []

    for league in get_leagues(df_raw):
        try:
            df, df_league, df_byes = filter_league(df_raw, league)
        except Exception:
            continue

        if df.empty:
            continue

        played_rounds = sorted(df['Round'].unique())
        if len(played_rounds) < min_prior_rounds + 1:
            continue

        for i, test_round in enumerate(played_rounds):
            prior_rounds = played_rounds[:i]
            if len(prior_rounds) < min_prior_rounds:
                continue

            df_prior = df[df['Round'].isin(prior_rounds)].copy()
            df_byes_prior = df_byes[df_byes['Round'].isin(prior_rounds)].copy()

            try:
                long_prior = make_long(df_prior, df_byes_prior)
                carry = get_carry_over_stats(df_raw, league)
                summary_prior = make_summary(long_prior, carry)
                form_prior = make_form(long_prior)
                poisson_models = {d: fit_poisson_model(df_prior, decay=d) for d in DECAY_VALUES}
            except Exception:
                continue

            test_games = df[df['Round'] == test_round]

            for _, row in test_games.iterrows():
                home, away = row['Home'], row['Away']
                if 'TITANS' in str(home) or 'TITANS' in str(away):
                    continue
                if home == 'BYE' or away == 'BYE':
                    continue

                actual_hg, actual_ag = int(row['HG']), int(row['AG'])
                actual_result = result_label(actual_hg, actual_ag)

                rec = {
                    'league': league,
                    'round': test_round,
                    'home': home,
                    'away': away,
                    'actual_hg': actual_hg,
                    'actual_ag': actual_ag,
                    'actual_result': actual_result,
                }

                # Poisson predictions at each decay value
                for d in DECAY_VALUES:
                    m = poisson_models[d]
                    if m and home in m['idx'] and away in m['idx']:
                        hg, ag = predict_score_poisson(home, away, m)
                        rec[f'p{d}_hg'] = hg
                        rec[f'p{d}_ag'] = ag
                        rec[f'p{d}_result'] = result_label(hg, ag)
                    else:
                        rec[f'p{d}_hg'] = None
                        rec[f'p{d}_ag'] = None
                        rec[f'p{d}_result'] = None

                # Old model
                try:
                    o_hg, o_ag = predict_score(home, away, summary_prior, form_prior, df_prior)
                    rec['old_hg'] = o_hg
                    rec['old_ag'] = o_ag
                    rec['old_result'] = result_label(o_hg, o_ag)
                except Exception:
                    rec['old_hg'] = rec['old_ag'] = rec['old_result'] = None

                records.append(rec)

    return pd.DataFrame(records)


def score_model(df, hg_col, ag_col, result_col):
    valid = df.dropna(subset=[hg_col, ag_col, result_col])
    if valid.empty:
        return {}
    correct = (valid[result_col] == valid['actual_result']).mean()
    mae_hg  = (valid[hg_col] - valid['actual_hg']).abs().mean()
    mae_ag  = (valid[ag_col] - valid['actual_ag']).abs().mean()
    mae_gd  = ((valid[hg_col] - valid[ag_col]) - (valid['actual_hg'] - valid['actual_ag'])).abs().mean()
    return {
        'n': len(valid),
        'result_accuracy': round(correct * 100, 1),
        'mae_home_goals':  round(mae_hg, 3),
        'mae_away_goals':  round(mae_ag, 3),
        'mae_goal_diff':   round(mae_gd, 3),
    }


if __name__ == '__main__':
    print('Loading data...')
    df_raw = load_data()

    print('Running backtest (this may take ~30s)...\n')
    results = run_backtest(df_raw)

    if results.empty:
        print('No results — not enough rounds played yet.')
    else:
        print(f'Games evaluated: {len(results)}\n')

        # decay sweep summary
        print(f"{'Model':<18} {'n':>6} {'Result acc':>12} {'MAE home':>10} {'MAE away':>10} {'MAE GD':>10}")
        print('-' * 70)

        all_scores = {}
        for d in DECAY_VALUES:
            s = score_model(results, f'p{d}_hg', f'p{d}_ag', f'p{d}_result')
            all_scores[f'Poisson d={d}'] = s
            label = f'Poisson d={d}'
            print(f"{label:<18} {s['n']:>6} {str(s['result_accuracy'])+'%':>12} {s['mae_home_goals']:>10} {s['mae_away_goals']:>10} {s['mae_goal_diff']:>10}")

        old_s = score_model(results, 'old_hg', 'old_ag', 'old_result')
        print(f"{'Old model':<18} {old_s['n']:>6} {str(old_s['result_accuracy'])+'%':>12} {old_s['mae_home_goals']:>10} {old_s['mae_away_goals']:>10} {old_s['mae_goal_diff']:>10}")

        best_decay = max(DECAY_VALUES, key=lambda d: all_scores[f'Poisson d={d}'].get('result_accuracy', 0))
        print(f"\nBest decay value by result accuracy: {best_decay}")
        print(f"(Use fit_poisson_model(df, decay={best_decay}) in production)\n")
