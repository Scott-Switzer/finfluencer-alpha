# Unpushed Commit Recovery Instructions (dd76c8a contingency)

This note records the safe recovery path for the known RunPod case where local commit `dd76c8a` exists on branch `x-youtube-full-research-expansion` but HTTPS push fails with:

`fatal: could not read Username for 'https://github.com': No such device or address`

## Current controller observations in this workspace

- Active branch: `x-youtube-full-research-expansion`
- Local HEAD during this run: `a2b3e14`
- `origin/x-youtube-full-research-expansion` during this run: `a2b3e14`
- Push status here: already synced (`Everything up-to-date`)

## If RunPod still has local `dd76c8a` unpushed

Create a bundle on RunPod:

```bash
git bundle create /workspace/fin496_dd76c8a_push_recovery.bundle origin/x-youtube-full-research-expansion..HEAD
git bundle verify /workspace/fin496_dd76c8a_push_recovery.bundle
```

Bundle path:

- `/workspace/fin496_dd76c8a_push_recovery.bundle`

## Fetch bundle into local Mac repo

From local repo root:

```bash
git fetch /path/to/fin496_dd76c8a_push_recovery.bundle x-youtube-full-research-expansion
git log --oneline --decorate -5 FETCH_HEAD
git checkout x-youtube-full-research-expansion
git merge --ff-only FETCH_HEAD
git push origin x-youtube-full-research-expansion
```

If the bundle contains only commit `dd76c8a`, `git merge --ff-only FETCH_HEAD` will advance the branch without rewriting history.
