---
description: "CRITICAL — Run at EVERY conversation start: scan ~/.agents/skills/ and .agent/skills/ for installed skills, read each SKILL.md, and check if the user's message matches any trigger condition. Also triggered by: 开始工作, 开始coding, 收工, 结束工作, 同步云端, 推送代码, find a skill, search skills, how do I do X, is there a skill for X."
---

# Skill Auto-Discovery & Trigger

## Installed Skills

| Skill | Location | Triggers |
|-------|----------|----------|
| `project_tracker` | `~/.agents/skills/project_tracker/SKILL.md` | 开始工作, 开始coding, 收工, 结束工作, let's begin, wrap up |
| `find-skills` | `~/.agents/skills/find-skills/SKILL.md` | how do I do X, find a skill, search skills |
| `git_sync` | `~/.agents/skills/git_sync/SKILL.md` | 同步云端, 推送代码, push to staging, sync to remote |

## Steps

// turbo-all

1. Read the `SKILL.md` of every skill listed above (use `view_file` on each path).
2. Match the user's message against each skill's trigger conditions using **semantic matching** (not exact string).
3. If a match is found, **execute that skill's documented behavior immediately**.
4. If no match, proceed normally.
