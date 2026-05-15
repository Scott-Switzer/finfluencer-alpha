import sqlite3
from pathlib import Path

db = Path("data/finfluencer_alpha.db")
con = sqlite3.connect(db)
cur = con.cursor()

print("=== DUPLICATE CHECK ===")
c1 = cur.execute("SELECT COUNT(1) FROM transcript_candidate_windows").fetchone()[0]
c2 = cur.execute("SELECT COUNT(DISTINCT video_id || '-' || ticker || '-' || evidence_start_seconds) FROM transcript_candidate_windows").fetchone()[0]
print(f"Total windows: {c1}")
print(f"Distinct windows (by video+ticker+start): {c2}")
print(f"Duplicates: {c1 - c2}")

c3 = cur.execute("SELECT COUNT(1) FROM transcript_recommendation_events").fetchone()[0]
c4 = cur.execute("SELECT COUNT(DISTINCT video_id || '-' || ticker || '-' || evidence_start_seconds) FROM transcript_recommendation_events").fetchone()[0]
print(f"\nTotal events: {c3}")
print(f"Distinct events (by video+ticker+start): {c4}")
print(f"Duplicates: {c3 - c4}")

print("\n=== WINDOWS/EVENTS PER VIDEO (top 10) ===")
for row in cur.execute("""
    SELECT video_id, COUNT(1) as cnt 
    FROM transcript_candidate_windows 
    GROUP BY video_id 
    ORDER BY cnt DESC 
    LIMIT 10
""").fetchall():
    print(f"  {row[0]}: {row[1]} windows")

con.close()
