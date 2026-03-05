---
name: project_tracker
description: Tracks project session lifecycle in TASKS.md. Use when user semantically indicates starting/resuming or ending work, including variants and longer phrases such as 开始工作, 开工, 开始coding, 进入开发, 继续上次, 接着做, 今天做什么, 安排下任务, 收工, 下班, 结束工作, 结束今天, 今天先到这, 保存进度, wrap up, end session, start coding, continue where we left off. No external API required.
---

# Project Tracker

Maintain a single `TASKS.md` in each project root that serves as the living source of truth for **architecture**, **data flow**, **tasks**, and **change history**.

## When to Activate

Activate this skill when the user's message **semantically matches** any of the following intents (not exact string match — interpret meaning):

### Session Start Intents
- "开始 coding" / "开始工作" / "start coding" / "let's begin"
- "继续上次的" / "pick up where we left off"
- "今天做什么" / "what's on the agenda"
- Any message that signals the beginning of a work session

### Session End Intents
- "结束工作" / "收工" / "结束今天的" / "wrap up" / "end session"
- "今天就到这里" / "let's stop here" / "save progress"
- Any message that signals the end of a work session

---

## Session Start Behavior

When a session start intent is detected:

### If `TASKS.md` exists in project root:

1. **Read** the full `TASKS.md`
2. **Present a summary** to the user:
   - Last session date and summary (from the file header)
   - Current branch name (run `git branch --show-current`)
   - All **In Progress** (`[/]`) tasks
   - Top 5 **TODO** (`[ ]`) tasks by priority
   - Any recent Change Log entries from the last session
3. **Ask**: "要继续上次的任务，还是做新的事情？"

### If `TASKS.md` does NOT exist (first time):

1. **Check** for existing documentation:
   - `PROJECT.md` → extract architecture and data flow sections
   - `todo.md` or `TODO.md` → extract task list
2. **Scan** for code-level TODOs:
   ```bash
   grep -rn "TODO\|FIXME\|HACK\|XXX" --include="*.py" --include="*.ts" --include="*.js" . | head -30
   ```
3. **Generate** initial `TASKS.md` using the template below
4. **Show** the generated file to user for review before saving

---

## Session End Behavior

When a session end intent is detected:

### Step 1: Evaluate Code-Structure Relevance (Gate Check)

Review the **entire conversation** and determine whether any changes **directly impacted the project's code structure or data flow**:
- ✅ **Relevant** (triggers update): architecture changes, data flow changes, refactoring, new features, significant bug fixes, new modules/files, dependency changes — anything that modifies how the codebase is organized or how data moves through the system
- ❌ **NOT relevant** (skip update): general Q&A, technical discussions that don't change code (e.g. asking about agent/tool capabilities, comparing technologies), tool/skill management, casual conversation, documentation-only edits, trivial fixes, manual edits to TASKS.md itself, configuration of dev tools/skills

**If the session has NO relevance to the project's code structure or data flow** → **skip the entire session end update**. Do NOT update `Last session` timestamp, do NOT record Session Stats, do NOT modify TASKS.md at all. Simply inform the user: "本次会话没有涉及项目代码结构或数据流变更，跳过 TASKS.md 更新。" and exit.

**If code-structure-relevant changes DID occur** → proceed to Step 2.

### Step 2: Determine Session Time Range

- **If "开始工作" was said earlier in this conversation**: use that timestamp as start time
- **If NO "开始工作" was said** (user jumped straight into work): read `Last session` timestamp from TASKS.md header → use the **first message timestamp of the current conversation** as start time
- **End time**: current timestamp when "结束工作" is detected
- **Duration**: end - start

### Step 3: Estimate Token Consumption

Review the entire conversation from start to end. Estimate tokens by character count:

**Input tokens** (user messages):
- Count total characters across all user messages in this session
- Formula: `input_tokens ≈ chinese_chars × 1.5 + english_words × 1.3`
- Simplified: `input_tokens ≈ total_user_chars × 1.4`

**Output tokens** (agent responses):
- Count total characters across all agent responses in this session
- Formula: `output_tokens ≈ total_agent_chars × 1.4`

**Note**: These are rough estimates (±30%). For exact billing, check provider dashboard.

### Step 4: Update TASKS.md

- **Header**: Update `Last session` timestamp and write a 1-line summary
- **Session Stats**: Append new row with date, duration, input/output tokens, summary
- **Task Board**: Move tasks between In Progress / TODO / Done as needed
- **Architecture / Data Flow**: Update mermaid diagrams if structural shifts occurred
- **Change Log**: Add entry only for architecture/data flow impacting changes
- **Quick Reference**: Update if new commands, config files, or entry points were added

### Step 5: Show diff summary to user and confirm before saving

---

## Passive Behavior (During Session)

While working, do NOT auto-modify `TASKS.md`. Instead:

- When a **significant refactoring** happens (file moves, module renames, data flow changes), note it internally and **remind** the user at session end
- When a **task is clearly completed**, note it internally for the session end update
- If the user asks "当前进度" / "what have we done" mid-session, provide a verbal summary without modifying `TASKS.md`
- **Ignore non-code conversations** — tool management, skill setup, general Q&A, and casual conversation are NOT project progress
- **Ignore TASKS.md self-edits** — user's manual edits to TASKS.md are always authoritative and should NOT be logged as changes

---

## TASKS.md Template

When generating a new `TASKS.md`, use this structure:

```markdown
# [Project Name] — Project Tracker

> **Last session**: [date] — [1-line summary of last session]
> **Current branch**: [branch name]

---

## 0. Session Stats

| 日期 | 时长 | 输入 token (估) | 输出 token (估) | 摘要 |
|------|------|----------------|----------------|------|
| YYYY-MM-DD | Xh Ym | ~N | ~N | 1-line summary |

---

## 1. Architecture Overview

### Tech Stack

| Dimension | Details |
|-----------|---------|
| **Stack** | [languages, frameworks] |
| **Infrastructure** | [databases, queues, storage] |
| **Deployment** | [deployment method] |

### Directory Structure

[Project directory tree - key directories only, not exhaustive]

### System Architecture

[mermaid graph diagram showing major components and their relationships]

---

## 2. Data Flow

[mermaid sequence diagram showing key data flows]

### Key Processing Routes

| Input | Processor | Output |
|-------|-----------|--------|
| [describe key routing/processing logic] |

---

## 3. Task Board

### 🔴 In Progress
- [/] **Task name** — context (started: YYYY-MM-DD)

### 🟡 TODO

#### High Priority
- [ ] **Task name** — context

#### Normal Priority
- [ ] **Task name** — context

#### Low Priority
- [ ] **Task name** — context

### ✅ Done
- [x] ~~Task name~~ — context (completed: YYYY-MM-DD)

### 📋 Code-Level TODOs

| File | Line | Note |
|------|------|------|
| [file:line] | [TODO comment] |

---

## 4. Change Log

| Date | Type | Description | Files |
|------|------|-------------|-------|
| YYYY-MM-DD | [refactor/feature/fix/cleanup] | [what changed and why] | [affected files] |

---

## 5. Quick Reference

### Dev Commands

[Common development commands]

### Key Config Files

| File | Purpose |
|------|---------|
| [config files and their roles] |

### Quick Locate Guide

| Task | Entry Point |
|------|-------------|
| [common tasks mapped to file entry points] |
```

---

## Change Log: What to Record

The Change Log is reserved for changes that **impact architecture or data flow**. Trivial edits do NOT get logged.

### ✅ Record These
| Type | When to Use |
|------|-------------|
| `refactor` | Code restructuring: file moves, renames, module extraction, dependency changes |
| `feature` | New modules, new API endpoints, new parsers, new data paths |
| `fix` | Bug fixes that changed how components interact or data flows |
| `config` | Infrastructure changes that affect architecture (new services, changed deployment) |

### ❌ Do NOT Record
- Documentation-only edits (updating TASKS.md, README, comments)
- Trivial code fixes (typos, formatting, minor logic tweaks)
- Manual edits the user made to TASKS.md
- Tool/skill installation or configuration
- Merging branches without conflict (routine sync)

---

## Progressive Disclosure

TASKS.md should remain **scannable** (target: 3 minutes to read). For complex topics that need detailed plans, use this pattern:

- **In TASKS.md**: Write a single-line summary with a link to the detail file
  ```markdown
  - [ ] **Table Parser 优化** (P0-P3) — HTML 表头展开、层级扁平化 → 详见 [TABLE_PARSER_OPTIMIZATION.md](./TABLE_PARSER_OPTIMIZATION.md)
  ```
- **In the detail file** (e.g., `TABLE_PARSER_OPTIMIZATION.md`): Full plan with code references, implementation details, comparison tables, etc.

### When to use detail files:
- A task has **3+ sub-items** that each need code-level context
- A feature involves **cross-file refactoring** with before/after comparisons
- A plan requires **reference implementations** or code snippets

### When NOT to use detail files:
- A task is a single, self-explanatory item (keep it inline in TASKS.md)
- The context fits in one line with a file:line reference

---

## Important Rules

1. **Never auto-modify TASKS.md without user confirmation** — always show proposed changes first at session end
2. **Preserve existing content** — when updating, merge changes into the existing structure, don't regenerate from scratch
3. **Keep it concise** — TASKS.md should be scannable in 3 minutes; avoid verbose descriptions
4. **Date everything** — all task state changes and change log entries must include dates
5. **One TASKS.md per project** — always use the project root directory, never a global path
6. **Respect priorities** — maintain the High/Normal/Low priority ordering in the TODO section
7. **Chinese + English** — follow the language convention of the existing project (if PROJECT.md is in Chinese, maintain Chinese; otherwise use English)
8. **Code-related content only** — only track conversations about code structure, data flow, architecture, tasks, refactoring, and implementation. Ignore general Q&A, tool management, off-topic discussions, and casual conversation. The session summary and Change Log should reflect only project-relevant work
