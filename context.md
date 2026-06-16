# SSFA Analytics App

## Stack
- Python/Streamlit multipage app
- data.py — all data processing functions
- League_View.py — main team/competition view
- pages/1_Club_View.py — club leaderboard and drill-down
- pages/2_Division_Overview.py — cross-division stats

## Current issues to fix
1. project_table in manual and auto predictor showing incorrect games played
2. Regraded-out teams still appearing in standings (need to exclude)
3. Combined comps (W21AB, W40AB) need special handling
4. Synthetic vs grass analysis not yet built
5. Weather stats not yet built

## Key data notes
- TITANS are a disabled team, all their fixtures treated as byes
- Regrading happens after round 4, REGRADE_ADJUSTMENTS in data.py has PAJ/GAJ values
- Byes give 3 points, no goals
- Full season CSV at ssfa_full.csv