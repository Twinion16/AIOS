# GitHub Workflow

This repository keeps private development history and the public snapshot
strictly separate.

## Branches

| Branch | Role | Visibility |
|--------|------|------------|
| `master` | private development history | **local only — never pushed** |
| `publish` | clean public snapshot | mirrors GitHub `main` |

The public GitHub repository's `main` branch is fed **only** from the local
`publish` branch. `master` is never published.

## Publishing an update

```bash
# 1. switch to the public branch
git checkout publish

# 2. make and commit public-safe changes only
git add <files>
git commit -m "Describe the change"

# 3. push the public branch to GitHub main
git push origin publish:main
```

## Never do this

```bash
git push --all           # would publish master (private history)
git push --mirror        # would publish every ref
git push origin master   # publishes private development history
git push --force         # rewrites public history
```

## Private development

Private work happens on `master`, which stays local. To move a public-safe
change onto the public branch, **copy the files or cherry-pick**, then commit
them on `publish`. Never merge `master` into `publish`: that would drag
private history into the public branch.

Always confirm the branch before pushing:

```bash
git branch --show-current   # must be: publish
aios security-audit         # must be: PASS
```

## First-time setup (already done)

```bash
gh repo create AIOS --public --source=.
git push -u origin publish:main
```
