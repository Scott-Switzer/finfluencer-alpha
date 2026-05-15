import sqlite3
from pathlib import Path

db = Path("data/finfluencer_alpha.db")
con = sqlite3.connect(db)
cur = con.cursor()

print("=== INDEXES ON TRANSCRIPT TABLES ===")
for row in cur.execute("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name IN ('transcript_candidate_windows', 'transcript_recommendation_events', 'transcript_event_extraction_status')"):
    print(f"  {row[0]}: {row[1]}")

print("\n=== UNIQUE CONSTRAINTS ===")
for row in cur.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name IN ('transcript_candidate_windows', 'transcript_recommendation_events', 'transcript_event_extraction_status')"):
    print(row[0][:500])

print("\n=== DISTINCT VIDEOS IN EVENT TABLES ===")
c1 = cur.execute("SELECT COUNT(DISTINCT video_id) FROM transcript_candidate_windows").fetchone()[0]
print(f"Distinct videos in candidate_windows: {c1}")
c2 = cur.execute("SELECT COUNT(DISTINCT video_id) FROM transcript_recommendation_events").fetchone()[0]
print(f"Distinct videos in recommendation_events: {c2}")
c3 = cur.execute("SELECT COUNT(DISTINCT video_id) FROM transcript_event_extraction_status").fetchone()[0]
print(f"Distinct videos in extraction_status: {c3}")

print("\n=== HOW MANY CANDIDATE WINDOWS PER VIDEO (avg) ===")
for row in cur.execute("SELECT COUNT(DISTINCT video_id), COUNT(1) FROM transcript_candidate_windows").fetchall():
    print(f"  {row[1]} windows across {row[0]} videos = {row[1]/max(row[0],1):.1f} avg")

con.close()
