import pandas as pd

df = pd.read_csv('data/exports/validation/clean_auto_labeled_events.csv')
print(f"Clean included events: {len(df)}")
df2 = pd.read_csv('data/exports/validation/clean_auto_labeled_events_exclusions.csv')
print(f"Excluded events: {len(df2)}")
df3 = pd.read_csv('data/exports/event_study/event_study_results.csv')
print(f"Event study results: {len(df3)}")
print(f"Matched events: {df3['matched'].sum()}")
