---
name: git_sync
description: Syncs the current branch to a remote target branch (default: staging). Handles commit, fetch, merge, push, and generates a PR link. Triggers when user says "同步云端", "推送代码", "push to staging", "sync to remote", etc. No external API required.
---

# Git Sync

Push the current working branch to remote and prepare a PR against the target branch. Replaces manual `push_to_staging.sh` scripts with a dynamic, project-aware workflow.

## When to Activate

Activate this skill when the user's message **semantically matches** any of the following intents:

- "同步云端" / "推送代码" / "push代码" / "推到staging"
- "push to staging" / "sync to remote" / "push code"
- "提交并推送" / "commit and push"
- Any message that signals intent to push the current branch to a remote target

---

## Configuration

Each project can have a `.agent/sync.json` in its root:

```json
{
  "target_branch": "staging"
}
```

- **`target_branch`** — the remote branch to merge from and PR into (default: `staging`)

### If `.agent/sync.json` does NOT exist:

1. Default target branch to `staging`.
2. Proceed with the sync.

---

## Execution Steps

When triggered, execute the following steps **sequentially**. Show each step's output to the user. Stop immediately if any step fails.

### Step 1: Read Config

```bash
cat .agent/sync.json
```

- Extract `target_branch` (default to `staging` if missing or file not found)

### Step 2: Identify Branch & Remote

```bash
git branch --show-current
git remote get-url origin
```

- Record `CURRENT_BRANCH` and `REMOTE_URL`
- Parse GitHub org/repo from remote URL for PR link generation

### Step 3: Pre-flight Summary

Present a summary to the user and **auto-proceed** (do not wait for confirmation):

```
🔍 自动同步已启动:
  当前分支: <current_branch>
  目标分支: <target_branch>
  操作: auto commit → merge origin/<target_branch> → push <current_branch> → PR
```

This prevents the workflow from stalling.

### Step 4: Check for Uncommitted Changes

```bash
git status --porcelain
```

- If working tree is **clean** → skip to Step 5
- If there are **uncommitted changes**:
  1. Run `git diff --stat` to see what changed
  2. **Auto-generate a commit message** based on the diff:
     - Analyze changed files and diff content
     - Generate a conventional commit message (e.g., `feat: add X`, `fix: resolve Y`, `refactor: extract Z`)
  3. **Auto-commit** without asking for confirmation:
     ```bash
     git add -A
     git commit -m "<generated message>"
     ```

### Step 5: Fetch & Merge Target Branch

```bash
git fetch origin <target_branch>
git merge origin/<target_branch> -m "Merge origin/<target_branch> into <current_branch>"
```

- If merge **succeeds** → proceed
- If merge **conflicts**:
  - Show conflicting files via `git diff --name-only --diff-filter=U`
  - Inform user: "合并冲突，请手动解决后再次触发同步"
  - **Stop execution** — do NOT attempt to auto-resolve

### Step 6: Push to Remote

```bash
git push origin <current_branch>
```

### Step 7: Generate PR Link

Using the parsed remote URL, generate and display:

```
✅ 推送完成！

请创建 Pull Request:
  从: <current_branch>
  到: <target_branch>

PR 链接: https://github.com/<org>/<repo>/compare/<target_branch>...<current_branch>
```

---

## Error Handling

| Scenario | Action |
|----------|--------|
| Not a git repo | Inform user, stop |
| No remote configured | Inform user, stop |
| Merge conflict | Show conflicting files, stop |
| Push rejected (force needed) | Ask user before `--force-with-lease` |
| Network error | Retry once, then inform user |

---

## Important Rules

1. **Never force push** without explicit user confirmation
2. **Auto-commit**: Do not ask for confirmation on the commit message or the sync itself, unless there is a conflict.
3. **Stop on merge conflicts** — never auto-resolve
4. **Dynamic, not hardcoded** — always derive branch/remote/repo info from git commands
5. **One sync at a time** — if already mid-sync, don't restart
