import sys

sys.path.insert(0, "src")
from finfluencer_alpha.db import connect

with connect() as conn:
    sql = """SELECT run_id, command_name, started_at, ended_at, attempted_count, available_count, no_transcript_count FROM transcript_collection_runs ORDER BY started_at DESC LIMIT 5"""
    for row in conn.execute(sql).fetchall():
        print(f"{row[0]}: {row[1]} | started={row[2]} ended={row[3]} attempted={row[4]} available={row[5]} no_transcript={row[6]}")
