---
name: nve
description: Edit videos end to end with nve-studio. The user drops in raw videos/photos (talking head, product footage, green screen, everyday clips) and wants a finished short video with cuts, filler removal, colour look, word-highlight captions, an opening hook title, highlight stamps, emoji, B-roll frames, transitions, SFX and music. Plans a storyboard, previews stills, renders, checks quality. Use for "/nve", "edit this video", "dựng video", "cắt video", "làm video quảng cáo", "làm như cũ".
---

# nve (shell skill)

The full instructions for this skill are **not here**. They live on GitHub in `nhathm/video-editor-studio-standard`,
branch `stable`, file `skills/nve/SKILL.md`. This shell skill only loads that file, so updating nve only
needs a push to `stable`, never a reinstall of the skill.

First work out where you are running. Only case A (claude.ai) downloads and runs nve in the cloud.

## A. claude.ai (web or phone app, Free or paid plan): `/mnt/user-data` or `/home/claude` exists

1. **Get the repo** (latest version), `REPO=/tmp/video-editor-studio-standard`:
   - `$REPO` missing: `GIT_TERMINAL_PROMPT=0 git clone -q --depth 1 --branch stable https://github.com/nhathm/video-editor-studio-standard.git $REPO`.
     On failure run it again exactly once. Still failing **and** the `add_repo` tool exists → call `add_repo`
     for `nhathm/video-editor-studio-standard` (read access), then clone into `$REPO` as the tool instructs
     (`--depth 1 --branch stable`). No `add_repo` → tell the user in one line with the error, and stop.
   - `$REPO` present: `git -C $REPO fetch -q --depth 1 origin stable && git -C $REPO reset -q --hard origin/stable`
     (on failure keep using the copy you have).
2. Workspace: `export NVE_WORKSPACE=/tmp/nve-ws`, then run `nve init /tmp/nve-ws`.
3. Also read `$REPO/skills/nve/references/cloud.md`.

## B. Claude Code (CLI, Code tab in the desktop app, IDE) on Mac / Windows / Linux

This shell skill does **not run** here. On a computer nve is installed as a **Claude Code plugin** from git
and runs locally:
- If a `nve` skill already exists from the plugin (`nve:nve`) or from the workspace's `.claude/skills/nve` →
  use that skill and stop this shell skill.
- Otherwise → tell the user (briefly): open Claude Code in the folder that should hold the videos, type
  `/plugin marketplace add nhathm/video-editor-studio-standard` then `/plugin install nve@nve-studio`, open a new
  session in the same folder and type `/nve` (the first run sets itself up with `nve-setup`). Stop there.

## How to talk

The user is not technical. Reply briefly (1–3 sentences) about their video, in the user's language. Never
mention commits, branches, repos, paths, the shell skill, engine names or how nve works inside unless they
ask. Getting the repo happens silently.

## When running (case A)

- Always call the CLI as `bash $REPO/skills/nve/bin/nve <command>` (called `nve` below).
- Read all of `$REPO/skills/nve/SKILL.md` and follow it **exactly**. It replaces this shell skill; the user's
  request and files apply to it unchanged.
- Never write files into `$REPO` (extra code written for the user goes in the workspace `custom/`).
- Repo unavailable (see step 1) → tell the user in one line with the error, and stop. Never edit the video
  from memory.

This shell skill only needs updating when the `description` or the way the repo is fetched changes. It is
stored at `shells/nve/SKILL.md` in the repo.
