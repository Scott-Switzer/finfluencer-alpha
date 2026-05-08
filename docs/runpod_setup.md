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

## Recommended Pod Configuration

- **Pod type:** Cheapest available CPU pod (no GPU needed — transcript fetching
  uses only HTTP requests and SQLite)
- **Template:** `runpod/pytorch` or any basic Python template works
- **Network Volume:** 20–50 GB persistent volume mounted at `/workspace`
- **Container disk:** 10 GB is sufficient (just the OS + Python deps)
- **Cost estimate:** ~$0.20–$0.40/hr for a cheap CPU pod; $25 = 60–120 hours

## Setup Steps (on RunPod console)

### 1. Create a Network Volume

1. Go to RunPod → Storage → Network Volumes
2. Click "Create Network Volume"
3. Choose a data center (pick one close to you)
4. Set size to 20 GB (or 50 GB if you want room for many runs)
5. Note the volume ID (e.g., `vol_xxxxx`)

### 2. Create the Pod

1. Go to RunPod → Pods → "Deploy On-Demand"
2. Under "Network Volume", select the volume you created
3. Set mount point to `/workspace`
4. Choose the cheapest CPU pod available
5. Set container image to `runpod/pytorch:latest` or similar
6. Set disk size to 10 GB
7. Deploy

### 3. SSH into the Pod

Wait for the pod to be ready, then connect via the RunPod Web Terminal or
copy the SSH command and connect.

### 4. Upload your `.env` file

Securely copy your `.env` file to `/workspace/FIN496CAPSTONE/.env`:

```bash
# In the RunPod terminal, create your .env file:
cat > /workspace/FIN496CAPSTONE/.env << 'ENVEOF'
YOUTUBE_API_KEY=...
# Add any other keys you have
ENVEOF
```

**Never** commit `.env` or API keys to git.

### 5. Bootstrap the repo

Run the bootstrap script from inside the repo once cloned:

```bash
cd /workspace
git clone https://github.com/Scott-Switzer/finfluencer-alpha.git FIN496CAPSTONE
cd FIN496CAPSTONE
bash scripts/runpod_bootstrap.sh
```

Or use the one-line bootstrap on a fresh pod:

```bash
cd /workspace && git clone https://github.com/Scott-Switzer/finfluencer-alpha.git FIN496CAPSTONE && cd FIN496CAPSTONE && bash scripts/runpod_bootstrap.sh
```

## Important Rules

1. **Active DB stays on persistent disk**: SQLite DB at
   `/workspace/FIN496CAPSTONE/data/finfluencer_alpha.db`. Do NOT symlink or
   mount this from Google Drive, Dropbox, or any live-synced folder. Live sync
   will corrupt SQLite.

2. **Google Drive is backup only**: After each overnight run, use
   `scripts/backup_outputs.sh` to create a `.tar.gz`. You can upload that
   archive to Google Drive or any cloud storage. Never run the live DB from a
   synced folder.

3. **One pod at a time**: Never run multiple RunPod instances with the same
   Network Volume attached. SQLite is single-writer.

4. **Stop pods when done**: Pods charge per second while running, even if
   idle. Stop the pod after the morning review to preserve credits.

5. **No parallel collectors**: The overnight supervisor is single-process
   by design. Do not run multiple collection commands simultaneously.

## Workflow Summary

```
Bootstrap → Overnight run → Morning review → Backup → Stop pod
```

Each overnight run:
- Starts with readiness check (disk, cooldown, daily cap)
- Runs mini-batches with long sleeps between
- Stops cleanly on block/rate-limit/low-disk
- Writes full log and summary

The DB persists on the Network Volume between pod stops. You can stop the
pod after the morning review, and the DB will still be there when you start
a new pod with the same Network Volume.
