# RunPod shutdown and local sync plan

## 1) Commit and push safe source/report files

```bash
git status --short
git add scripts/*.py tests/*.py docs/*.md data/exports/overnight_collection/*.md data/exports/overnight_collection/*.csv
git commit -m "Update YouTube Apify canary/overnight safety and shutdown backup plan"
git push origin x-youtube-full-research-expansion
```

Do **not** add `.env`, DB files, raw transcript dumps, raw provider payloads, caches, or backup archives.

## 2) Create local shutdown backup bundle on RunPod

```bash
python scripts/prepare_runpod_shutdown_backup.py
```

Optional size cap per file:

```bash
RUNPOD_BACKUP_MAX_FILE_MB=100 python scripts/prepare_runpod_shutdown_backup.py
```

## 3) Pull backup to Mac (template)

Use either `rsync` or `scp` from your Mac terminal:

```bash
rsync -avz -e "ssh -p <RUNPOD_PORT> -i ~/.ssh/id_ed25519" root@<RUNPOD_HOST>:/workspace/FIN496CAPSTONE/data/backups/runpod_shutdown_<timestamp>* /Users/<you>/Desktop/FIN496CAPSTONE/runpod_backups/
```

```bash
scp -P <RUNPOD_PORT> -i ~/.ssh/id_ed25519 root@<RUNPOD_HOST>:/workspace/FIN496CAPSTONE/data/backups/runpod_shutdown_<timestamp>.tar.gz /Users/<you>/Desktop/FIN496CAPSTONE/runpod_backups/
```

## 4) Verify files exist locally before terminating RunPod

- `runpod_shutdown_<timestamp>.tar.gz`
- extracted `MANIFEST.md`
- extracted `RESTORE_NOTES.md`
- copied `data/exports/overnight_collection/*` status/report files
- copied SQLite DB backup if present

## 5) Safety warnings

- Do **not** terminate RunPod until local backup integrity is verified.
- Do **not** push raw DB/transcript content to GitHub.
- Keep transcript full-text local/ignored only.

## 6) Post-restore resume command

After restoring files locally or on a new RunPod:

```bash
python scripts/summarize_youtube_transcript_expansion.py
```

Then resume canary/overnight from current branch tip and latest status/checkpoint files.
