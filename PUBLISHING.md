# Publish to GitHub

This repo is ready to push. From a machine where you are logged into GitHub:

## Option A — GitHub CLI (`gh`)

```bash
cd deal-desk-flask   # this directory
gh repo create deal-desk-flask --public --source=. --remote=origin --push
```

Use `--private` instead of `--public` if you want a private repo.

## Option B — Web UI + git

1. On GitHub: **New repository** → name `deal-desk-flask` → leave empty (no README/license) → Create.
2. Then:

```bash
cd deal-desk-flask
git remote add origin https://github.com/YOUR_USER/deal-desk-flask.git
git branch -M main
git push -u origin main
```

Replace `YOUR_USER` with your GitHub username. Use a [Personal Access Token](https://github.com/settings/tokens) as the password if prompted (HTTPS).

## Option C — SSH

```bash
git remote add origin git@github.com:YOUR_USER/deal-desk-flask.git
git push -u origin main
```

Requires your SSH key to be added to GitHub.

## Option D — One script (DSW / CI)

`gh` is installed to `~/.local/bin/gh` (if you used the curl install). Then:

```bash
cd deal-desk-flask
export PATH="$HOME/.local/bin:$PATH"
export GH_TOKEN=ghp_your_classic_pat_with_repo_scope
./scripts/publish-github.sh
```

Creates `deal-desk-flask` on your account (public by default) and pushes `main`.
