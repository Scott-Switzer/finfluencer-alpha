# RunPod Sync Status

## Repository Alignment
| Context | HEAD | Status |
| --- | --- | --- |
| **Local (Mac)** | `205bf3c675eed03b13db9d523d2caeb8d8543357` | Synced with origin |
| **Origin (GitHub)** | `205bf3c675eed03b13db9d523d2caeb8d8543357` | Up to date |
| **RunPod** | `a2214fe` (last known) | **STALE** |

## RunPod Warning
The RunPod instance is currently behind the main research branch. No further collection or analysis should be run on RunPod without first syncing the repository to ensure consistency with the locked sample.

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
