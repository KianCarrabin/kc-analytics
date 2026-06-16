from data import load_data, filter_league, make_long, make_summary, make_full_schedule, get_carry_over_stats

df_raw = load_data()
df, df_league, df_byes = filter_league(df_raw, 'U18C')
long = make_long(df, df_byes)
carry_over = get_carry_over_stats(df_raw, 'U18C')
summary = make_summary(long, carry_over)
schedule, total_rounds = make_full_schedule(df, df_league, df_byes, summary, df_raw=df_raw, league='U18C')


print(f"Teams in summary: {len(summary)}")
print(f"Total rounds: {total_rounds}")
print(f"Cycle length used: {len(summary) - 1}")
print(schedule[schedule['Home'] == 'GPOI'].to_string())

print(schedule[schedule['Away'] == 'GPOI'].to_string())
print("\nAll GPOI fixtures:")
gpoi = schedule[(schedule['Home'] == 'GPOI') | (schedule['Away'] == 'GPOI')]
print(gpoi.sort_values('Round').to_string())

