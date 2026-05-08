# RunPod Setup for FIN 496 Transcript Collection

## Why RunPod

| Concern              | Local Mac (226 MB free) | RunPod with Network Volume |
|----------------------|------------------------|---------------------------|
| Free disk space      | ~226 MB                | 20–50 GB                 |
| Up-time overnight    | Mac may sleep          | Pod runs uninterrupted    |
| Persistent storage   | Internal SSD           | Network Volume survives pod restarts |
| Single-process       | Yes                    | Yes (one pod = one process) |

## Why RunPod May Not Help

- **Cloud IP blocks:** Data-center IP ranges are more likely to be rate-limited or
  blocked by YouTube's transcript API than residential IPs. This is why the
  overnight scripts use conservative settings (longer sleeps, smaller batches).
- **No proxy/rotation:** Rotating IPs and proxies are explicitly prohibited by
  this project's constraints. Accept that some batches may be blocked and the
  supervisor will stop cleanly.
- **$25 credit limit:** The free credits cover a basic CPU pod for multiple
  overnight runs if you stop the pod when not in use.

## Important RunPod Facts

- **Network Volumes** provide persistent storage independent from Pods.
- Network Volumes typically mount at `/workspace` and replace the default volume disk.
- Network Volumes must be attached during Pod deployment and **cannot** be attached/detached later without deleting/redeploying the Pod.
- **Container disk** is temporary and should **not** store the active DB.
- RunPod is **not** meant as permanent archival storage; make backups to local/GDrive/cloud after runs.
- **Flash CLI** is mainly for RunPod apps/serverless workflows; for this project, the safer workflow is a normal Pod + Network Volume.

---

## A. Local Flash Login (Mac)

If you have not completed `flash login` yet:

```bash
python3 -m pip install --upgrade pip
python3 -m pip install runpod-flash
flash login
```

**You must open the printed URL in a browser and authorize.** Flash prints a
URL like:

```
https://www.runpod.io/console/user/authorize?code=...
```

Open that URL in any browser, log in to RunPod, and authorize the CLI.

After authorization, verify:

```bash
flash --version
flash --help
flash list
```

If `flash list` shows pods and `flash create` / `flash ssh` / `flash stop`
commands are available, you may use Flash to manage pods. If Flash pod commands
are not available in your installed version, use the **Web Console Fallback**
section below.

---

## B. Web Console Fallback

If Flash pod commands are unavailable, use the RunPod web console at
https://www.runpod.io/console.

### 1. Create a Network Volume

1. Go to RunPod → Storage → Network Volumes
2. Click "Create Network Volume"
3. Choose a data center (pick one close to you)
4. **Recommended size:** 20 GB minimum, 50 GB if you want more room
5. Note the volume ID (e.g., `vol_xxxxx`)

### 2. Deploy a Pod with the Network Volume Attached

1. Go to RunPod → Pods → "Deploy On-Demand"
2. Under "Network Volume", select the volume you created
3. Set mount point to `/workspace`
4. Choose the cheapest CPU pod available (no GPU needed)
5. Set container image to `runpod/pytorch:latest` or any basic Python template
6. Set container disk size to 10 GB
7. Deploy

### 3. Confirm Mount

Once the pod is running, open the RunPod Web Terminal and run:

```bash
df -h /workspace
ls -lah /workspace
```

You should see the Network Volume mounted with 20–50 GB available.

### Cost Estimate

~$0.20–$0.40/hr for a cheap CPU pod; $25 = 60–120 hours of runtime.

---

## C. Data Storage Location (Where Everything Lives)

### On RunPod (persistent Network Volume)

| What                 | Path                                                      |
|----------------------|-----------------------------------------------------------|
| Active repo          | `/workspace/FIN496CAPSTONE`                               |
| Active DB            | `/workspace/FIN496CAPSTONE/data/finfluencer_alpha.db`     |
| Logs                 | `/workspace/FIN496CAPSTONE/data/logs/`                    |
| Exports              | `/workspace/FIN496CAPSTONE/data/exports/`                 |
| Backups              | `/workspace/FIN496CAPSTONE/data/backups/`                 |

### On Your Mac

- Source code (the git repo) — no active DB needed.
- Optional: backup `.tar.gz` archives downloaded from RunPod.

### Google Drive

- **Backup/transfer only.** Upload `.tar.gz` archives here after runs.
- **Never** run the live SQLite DB from Google Drive, Dropbox, or any
  live-synced folder. Live sync will corrupt SQLite.

---

## D. Transfer Your Existing DB to RunPod

Your local DB (`data/finfluencer_alpha.db`, ~84 MB) needs to be uploaded to
`/workspace/FIN496CAPSTONE/data/finfluencer_alpha.db` on the Network Volume.

### Option 1: RunPod File Browser Upload

1. In the RunPod web console, open your pod and click the "File Browser" tab.
2. Navigate to `/workspace/FIN496CAPSTONE/data/`.
3. Upload `data/finfluencer_alpha.db` from your Mac.

### Option 2: scp Upload

If you have the pod's SSH command from the console:

```bash
# On your Mac:
scp data/finfluencer_alpha.db user@pod-ip:/workspace/FIN496CAPSTONE/data/finfluencer_alpha.db
```

### Option 3: Temporary Google Drive Upload/Download

1. Upload `data/finfluencer_alpha.db` to Google Drive from your Mac.
2. On the RunPod terminal, download it from Google Drive (e.g., using `gdown`
   with a shareable link, or the Google Drive web UI from the pod's file browser).

### Verify the Transfer

Before proceeding, confirm the DB is correct on RunPod:

```bash
ls -lh data/finfluencer_alpha.db
python3 -m finfluencer_alpha transcript-collection-status
```

Expected output (approximate):

- **~164 transcripts** collected
- **~97 accepted events**
- **~6305 queue eligible**

If the output says **0 transcripts**, the DB was not transferred correctly or
`DATABASE_URL` points to the wrong path. Check your `.env` file and the actual
DB file location.

---

## E. Environment Setup (.env)

Create the `.env` file **only** on RunPod. Never commit it to git.

```bash
nano .env
```

Minimum contents:

```
DATABASE_URL=sqlite:///data/finfluencer_alpha.db
YOUTUBE_API_KEY=your_key_here
TRANSCRIPTAPI_KEY=your_key_here
YOUTUBETRANSCRIPT_DEV_API_KEY=your_key_here
```

- `DATABASE_URL` is critical — it tells the app where the SQLite DB lives.
- The API keys are optional for native-only transcript collection but useful
  for consistency and optional fallback providers.

---

## F. Smoke Test (Before Overnight Run)

After the DB is verified, run a small smoke test to confirm everything works
on the RunPod cloud IP:

```bash
python3 -m finfluencer_alpha run-overnight-transcript-collection \
  --batches 1 \
  --batch-limit 2 \
  --between-batch-sleep-seconds 30 \
  --sleep-seconds 45 \
  --jitter-seconds 20 \
  --max-per-creator 1 \
  --min-disk-mb 1000 \
  --cooldown-hours 24 \
  --max-daily-attempts 10
```

Then review results:

```bash
python3 -m finfluencer_alpha transcript-collection-status
cat data/exports/report_ready/overnight_transcript_collection_summary.txt
tail -100 data/logs/overnight_transcripts.log
```

If the smoke test succeeds with at least a few transcripts collected and no
`ip_blocked` / `request_blocked` errors, proceed to the overnight run.

---

## G. Overnight Run

If the smoke test passes:

```bash
bash scripts/runpod_overnight_safe.sh
```

This runs the full overnight collection with conservative settings: 6 batches,
4 transcripts per batch, 1-hour sleep between batches, with long per-request
sleeps and jitter. The pod will run unattended. You do **not** need to keep
your Mac on — once the pod is started, it runs independently on RunPod
infrastructure.

---

## H. Morning Review

When you wake up (or after the overnight script finishes):

```bash
bash scripts/runpod_morning_review.sh
```

This will:

- Print transcript collection status
- Show the overnight summary
- Show the last 200 log lines
- Rebuild transcript events
- Export transcript events
- Create a backup `.tar.gz` in `data/backups/`

Review the backup:

```bash
ls -lh data/backups/
```

**Download the backup** to your Mac or Google Drive for safekeeping.

---

## I. Stop the Pod

When you are done:

### If Flash pod commands are available:

```bash
flash list
flash stop <pod-id>
```

### Otherwise (Web Console):

1. Go to RunPod → Pods
2. Click the three-dot menu on your pod
3. Click "Stop Pod"

**Important:** Stopping the pod stops compute billing (the hourly rate), but
the Network Volume storage continues billing at a much lower rate (~$0.07/GB/month).
Your DB and all files persist on the Network Volume.

To restart, deploy a new pod with the same Network Volume attached.

---

## J. Failure Decision Table

| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| `transcript-collection-status` shows 0 transcripts | DB not transferred or wrong `DATABASE_URL` | Fix transfer path or `.env`; re-verify |
| `ip_blocked` / `request_blocked` immediately in smoke test | RunPod cloud IP is blocked by YouTube | **Stop.** RunPod is not viable for native transcript collection from this data center. Fall back to local Mac or try a different data center. |
| No transcripts collected but no block error | Rate-limiting or quota exhaustion | Run one more small smoke test; if still 0, wait and retry or fall back to local |
| DB shows correct count, smoke test succeeds | Everything is working | Proceed to overnight safe run |
| Disk space error (`min-disk-mb` check fails) | Using container disk instead of Network Volume | Ensure `/workspace` is a Network Volume; run `df -h /workspace` to verify |
| Permission errors | Scripts not executable or wrong working directory | Run `chmod +x scripts/*.sh` and verify you are in `/workspace/FIN496CAPSTONE` |
| Pod stops mid-run | Pod crashed or was preempted | Check RunPod logs; redeploy with same Network Volume; data is safe |

---

## Quick-Start Cheat Sheet

```
# Local Mac:
1. Complete flash login (see Section A)
2. bash scripts/local_prepare_runpod_upload.sh
3. Upload data/finfluencer_alpha.db to /workspace/FIN496CAPSTONE/data/

# RunPod terminal:
1. cd /workspace
2. git clone https://github.com/Scott-Switzer/finfluencer-alpha.git FIN496CAPSTONE
3. cd FIN496CAPSTONE
4. bash scripts/runpod_bootstrap.sh
5. bash scripts/runpod_verify_data.sh
6. [Smoke test — see Section F]
7. bash scripts/runpod_overnight_safe.sh
8. [Morning — Section H]
9. bash scripts/runpod_morning_review.sh
10. [Download backup]
11. [Stop pod — Section I]
```
