# Smart-AI-Backup — Deferred Setup

The local mirror (E:) and local git commits work right now. Two destinations need
your one-time interactive setup:

## 1. GitHub remote (off-machine git mirror)

The local git repo at [D:/CLAUDE/_ai_backups_git/](file:///D:/CLAUDE/_ai_backups_git/)
is committing every 30 min, but nothing is being pushed off-box. To push to your
account `iddo111`:

```cmd
cd /d D:\CLAUDE\_ai_backups_git
git remote add origin https://github.com/iddo111/claude-ai-backups.git
git push -u origin main
```

If the repo `claude-ai-backups` does not exist yet on GitHub, create it first
(empty, no README) at https://github.com/new — name it `claude-ai-backups`,
mark it **Private** (it contains training data).

After the first manual push, the daemon will keep pushing automatically every 30
min.

## 2. rclone -> Google Drive

```powershell
winget install Rclone.Rclone
# then, in a new terminal:
rclone config
# n  -> name=gdrive  -> Storage=drive  -> follow OAuth in browser
# (use the default scope; the `gdrive` name MUST match)
```

Once `rclone listremotes` shows `gdrive:`, the daemon will sync to
`gdrive:claude-ai-backups/` on the next 30-min pass — capped at 100 MB per file
and 8 MB/s, so it won't eat your quota or upload bandwidth.

---

Status JSON for the watchdog: [last_status.json](file:///D:/CLAUDE/tools/ai_backup/last_status.json)
Log: [backup.log](file:///D:/CLAUDE/tools/ai_backup/backup.log) (rotates at 50 MB)
