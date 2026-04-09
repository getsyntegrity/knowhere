---
name: git_sync
description: Syncs the current branch to a remote target branch (default: staging). Handles commit, fetch, merge, push, PR link, then returns to the home branch. Triggers when user says "同步云端", "推送代码", "push to staging", "sync to remote", etc. No external API required.
---

# Git Sync

Push the current working branch to remote as a PR branch, then return to the designated home branch in sync with `staging`. The user's permanent working branch is `feat/eric/parsing-update`.

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
  "target_branch": "staging",
  "home_branch": "feat/eric/parsing-update"
}
```

- **`target_branch`** — the remote branch to merge from and PR into (default: `staging`)
- **`home_branch`** — the permanent working branch to return to after sync (default: `feat/eric/parsing-update`)

### If `.agent/sync.json` does NOT exist:

1. Default `target_branch` to `staging`, `home_branch` to `feat/eric/parsing-update`.
2. Create `.agent/sync.json` with those values.
3. Proceed with the sync.

---

## Execution Steps

When triggered, execute the following steps **sequentially** and **without pausing for confirmation** (except on conflicts). Show each step's output to the user. Stop immediately if any step fails.

### Step 1: Read Config

```bash
cat .agent/sync.json
```

- Extract `target_branch` (default: `staging`) and `home_branch` (default: `feat/eric/parsing-update`)

### Step 2: Identify Branch & Remote

```bash
git branch --show-current
git remote get-url origin
```

- Record `CURRENT_BRANCH` and `REMOTE_URL`
- Parse GitHub org/repo from remote URL for PR link generation

### Step 3: Print Pre-flight Summary (no confirmation needed)

```
🔍 自动同步已启动:
  当前分支:  <current_branch>
  目标分支:  <target_branch>
  主工作分支: <home_branch>
  操作流程:  auto-commit → merge origin/<target_branch> → push <current_branch> → PR → checkout <home_branch> → pull staging → delete <current_branch>
```

### Step 4: Handle Uncommitted Changes

```bash
git status --porcelain
```

- If working tree is **clean** → skip to Step 5
- If there are **uncommitted changes**:
  1. Run `git diff --stat` to see what changed
  2. **Auto-generate** a conventional commit message based on the diff (e.g. `feat: add X`, `fix: resolve Y`)
  3. **Auto-commit without asking**:
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
  - Show conflicting files: `git diff --name-only --diff-filter=U`
  - Inform user: "⚠️ 合并冲突，请手动解决后再次触发同步"
  - **Stop** — do NOT attempt to auto-resolve

### Step 6: Push to Remote

```bash
git push origin <current_branch>
```

- If rejected (non-fast-forward), try:
  ```bash
  git pull origin <current_branch> --rebase
  git push origin <current_branch>
  ```

### Step 7: Generate PR Link

```
✅ 推送完成！PR 请在以下链接创建:
https://github.com/<org>/<repo>/compare/<target_branch>...<current_branch>
```

### Step 8: Return to Home Branch & Sync Staging

```bash
git checkout <home_branch>
git pull origin <target_branch> --rebase
```

- This ensures `<home_branch>` is always up-to-date with the latest staging after every sync.

### Step 9: Delete the Temporary Branch Locally

```bash
git branch -D <current_branch>
```

- Always use `-D` (force) because the branch was pushed as a PR and git may report it as "not fully merged".
- Do **not** delete the remote branch — that's for the reviewer/CI to handle after the PR merges.

### Step 10: Done

```
🏠 已返回 <home_branch>，本地临时分支已清理。
   当前状态与 origin/<target_branch> 同步。
```

---

## Error Handling

| Scenario | Action |
|----------|--------|
| Not a git repo | Inform user, stop |
| No remote configured | Inform user, stop |
| Merge conflict | Show conflicting files, stop |
| Push rejected | Pull --rebase, retry once |
| Network error | Retry once, then inform user |
| Already on home_branch | Skip Steps 8–9, nothing to clean up |

---

## Important Rules

1. **Never force push** to remote without explicit user confirmation
2. **Auto-commit** — do not ask for message confirmation, just generate and commit
3. **Auto-proceed** — do not ask for confirmation before starting the sync
4. **Stop on merge conflicts** — never auto-resolve
5. **Always return to home_branch** — leave the workspace clean after every sync
6. **Dynamic, not hardcoded** — always derive branch/remote/repo info from git commands
