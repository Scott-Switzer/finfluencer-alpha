# RunPod Sync Status

## Repository Alignment
| Context | HEAD | Status |
| --- | --- | --- |
| **Local (Mac)** | `788a519b31e49b614f7fcd79112e7e991da7b049` | Synced with origin |
| **Origin (GitHub)** | `788a519b31e49b614f7fcd79112e7e991da7b049` | Up to date |
| **RunPod** | `a2214fe` (last known) | **STALE** |

## RunPod Warning
The RunPod instance is currently behind the main research branch. No further collection should be run on RunPod without first syncing the repository.

### Recommended Sync Commands (Safe)
To bring RunPod up to speed without losing local uncommitted work:
```bash
git fetch origin
git stash
git merge origin/x-youtube-full-research-expansion
git stash pop
```

> [!CAUTION]
> Do not run `git reset --hard` on RunPod unless you are certain all raw data/backups have been scp'd to the local Mac as per the shutdown plan.
