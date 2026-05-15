import sys

sys.path.insert(0, "src")
from finfluencer_alpha.db import connect

with connect() as conn:
    clean = conn.execute("SELECT COUNT(1) FROM clean_auto_labeled_events WHERE include = 1").fetchone()[0]
    matched = conn.execute("SELECT COUNT(1) FROM event_study_results WHERE matched = 1").fetchone()[0]
    print(f"Clean included events: {clean}")
    print(f"Matched market-data events: {matched}")
