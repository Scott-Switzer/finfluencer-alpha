import sqlite3
from pathlib import Path

db = Path("data/finfluencer_alpha.db")
con = sqlite3.connect(db)
cur = con.cursor()

print("DB:", db)

print("\n=== TABLES ===")
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")]
for t in tables:
    print(t)

print("\n=== ROW COUNTS ===")
for t in tables:
    try:
        c = cur.execute(f"SELECT count(1) FROM [{t}]").fetchone()[0]
        print(f"{t}: {c}")
    except Exception as e:
        print(f"{t}: ERROR {e}")

print("\n=== SCHEMAS FOR KEY TABLES ===")
for t in tables:
    if any(k in t.lower() for k in ["event", "validation", "transcript", "ticker", "market", "candidate", "recommendation", "clean"]):
        print(f"\n--- {t} ---")
        for row in cur.execute(f"PRAGMA table_info([{t}])"):
            print(f"  {row[1]} ({row[2]})")

print("\n=== KEY COUNTS BY SEGMENT ===")
for row in cur.execute("""
    SELECT creator_category, COUNT(1) FROM raw_youtube_videos
    WHERE excluded_flag = 0 OR excluded_flag IS NULL
    GROUP BY creator_category
    ORDER BY COUNT(1) DESC
""").fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== TICKER MENTION STATS ===")
c = cur.execute("SELECT COUNT(1) FROM ticker_mentions").fetchone()[0]
print(f"Total ticker mentions: {c}")
c2 = cur.execute("SELECT COUNT(DISTINCT ticker) FROM ticker_mentions").fetchone()[0]
print(f"Unique tickers mentioned: {c2}")
c3 = cur.execute("SELECT COUNT(DISTINCT source_id) FROM ticker_mentions WHERE platform = 'youtube'").fetchone()[0]
print(f"Videos with ticker mentions: {c3}")

print("\n=== RECOMMENDATION CANDIDATES ===")
c = cur.execute("SELECT COUNT(1) FROM recommendation_candidates").fetchone()[0]
print(f"Total recommendation candidates: {c}")
for row in cur.execute("SELECT platform, COUNT(1) FROM recommendation_candidates GROUP BY platform").fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== TRANSCRIPT RECOMMENDATION EVENTS ===")
c = cur.execute("SELECT COUNT(1) FROM transcript_recommendation_events").fetchone()[0]
print(f"Total transcript recommendation events: {c}")

print("\n=== EVENT VALIDATION SAMPLE ===")
c = cur.execute("SELECT COUNT(1) FROM event_validation_sample").fetchone()[0]
print(f"Total validation sample rows: {c}")
for row in cur.execute("SELECT auto_label, COUNT(1) FROM event_validation_sample GROUP BY auto_label").fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== CLEAN AUTO LABELED EVENTS ===")
c = cur.execute("SELECT COUNT(1) FROM clean_auto_labeled_events").fetchone()[0]
print(f"Total clean auto labeled events: {c}")
for row in cur.execute("SELECT include, COUNT(1) FROM clean_auto_labeled_events GROUP BY include").fetchall():
    print(f"  include={row[0]}: {row[1]}")

print("\n=== EVENT STUDY RESULTS ===")
c = cur.execute("SELECT COUNT(1) FROM event_study_results").fetchone()[0]
print(f"Total event study results: {c}")
c2 = cur.execute("SELECT COUNT(1) FROM event_study_results WHERE matched = 1").fetchone()[0]
print(f"Matched events: {c2}")

print("\n=== FULL FUNNEL ===")
print("Videos: 11883")
print("Transcripts: 7087")
print(f"Videos with ticker mentions: {c3}")
print(f"Recommendation candidates: {cur.execute('SELECT COUNT(1) FROM recommendation_candidates').fetchone()[0]}")
print(f"Transcript recommendation events: {cur.execute('SELECT COUNT(1) FROM transcript_recommendation_events').fetchone()[0]}")
print(f"Validation sample: {cur.execute('SELECT COUNT(1) FROM event_validation_sample').fetchone()[0]}")
print(f"Clean included events: {cur.execute('SELECT COUNT(1) FROM clean_auto_labeled_events WHERE include = 1').fetchone()[0]}")
print(f"Matched market-data events: {cur.execute('SELECT COUNT(1) FROM event_study_results WHERE matched = 1').fetchone()[0]}")

con.close()
