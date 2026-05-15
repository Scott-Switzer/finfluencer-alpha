import sqlite3
from pathlib import Path

import pandas as pd

db = Path("data/finfluencer_alpha.db")
con = sqlite3.connect(db)
cur = con.cursor()

print("=== TRANSCRIPT EVENT EXTRACTION STATUS ===")
c = cur.execute("SELECT COUNT(1) FROM transcript_event_extraction_status").fetchone()[0]
print(f"Videos processed for events: {c}")

print("\n=== ACCEPTED VS REJECTED CANDIDATE WINDOWS ===")
for row in cur.execute("SELECT accepted, COUNT(1) FROM transcript_candidate_windows GROUP BY accepted").fetchall():
    print(f"  accepted={row[0]}: {row[1]}")

print("\n=== ACCEPTED EVENT FLAG ===")
for row in cur.execute("SELECT accepted_event_flag, COUNT(1) FROM transcript_candidate_windows GROUP BY accepted_event_flag").fetchall():
    print(f"  accepted_event_flag={row[0]}: {row[1]}")

print("\n=== TRANSCRIPT EVENT EXCLUSIONS ===")
c = cur.execute("SELECT COUNT(1) FROM transcript_event_exclusions").fetchone()[0]
print(f"Total exclusions: {c}")

print("\n=== EVENTS WITH/WITHOUT EXCLUSION REASON ===")
c = cur.execute("SELECT COUNT(1) FROM transcript_recommendation_events WHERE exclusion_reason IS NULL OR exclusion_reason = ''").fetchone()[0]
print(f"Events with no exclusion reason: {c}")
c2 = cur.execute("SELECT COUNT(1) FROM transcript_recommendation_events WHERE exclusion_reason IS NOT NULL AND exclusion_reason != ''").fetchone()[0]
print(f"Events with exclusion reason: {c2}")

print("\n=== EVENTS BY STANCE ===")
for row in cur.execute("SELECT stance, COUNT(1) FROM transcript_recommendation_events GROUP BY stance").fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== EVENTS BY ACTIONABILITY SCORE ===")
for row in cur.execute("SELECT actionability_score, COUNT(1) FROM transcript_recommendation_events GROUP BY actionability_score ORDER BY actionability_score DESC").fetchall():
    print(f"  score={row[0]}: {row[1]}")

print("\n=== CANDIDATE WINDOWS BY CONFIDENCE LABEL ===")
for row in cur.execute("SELECT confidence_label, COUNT(1) FROM transcript_candidate_windows GROUP BY confidence_label").fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== CANDIDATE WINDOWS BY EXCLUSION REASON ===")
for row in cur.execute("SELECT COALESCE(exclusion_reason, 'NULL'), COUNT(1) FROM transcript_candidate_windows GROUP BY exclusion_reason").fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== RECOMMENDATION CANDIDATES BY PLATFORM ===")
for row in cur.execute("SELECT platform, COUNT(1) FROM recommendation_candidates GROUP BY platform").fetchall():
    print(f"  {row[0]}: {row[1]}")

print("\n=== TRANSCRIPTS WITHOUT EVENT EXTRACTION ===")
c = cur.execute("""
    SELECT COUNT(1) FROM youtube_transcripts yt
    WHERE yt.status = 'available'
    AND yt.video_id NOT IN (SELECT video_id FROM transcript_event_extraction_status)
""").fetchone()[0]
print(f"Transcripts not yet processed for events: {c}")

con.close()

print("\n=== CHECK CSV EXPORT FILES ===")
val_dir = Path("data/exports/validation")
if val_dir.exists():
    for f in sorted(val_dir.glob("*.csv")):
        try:
            df = pd.read_csv(f)
            print(f"\n{f.name}: {len(df)} rows, columns: {list(df.columns)}")
            if "auto_label" in df.columns:
                print(f"  auto_label: {df['auto_label'].value_counts().to_dict()}")
            if "include" in df.columns:
                print(f"  include: {df['include'].value_counts().to_dict()}")
        except Exception as e:
            print(f"\n{f.name}: ERROR {e}")
else:
    print("No validation dir")
