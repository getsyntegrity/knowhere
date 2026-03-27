---
description: MUST use this skill when responding to ANY user message (NOT OPTIONAL). Auto-execute pre-flight hooks in .agent-hooks before each response to inject computed context. 
---

# Agent Hooks — Pre-flight Context Injection

> **MANDATORY**: This skill MUST be executed as the VERY FIRST action before composing ANY response to the user. No exceptions.

## Protocol

On EVERY user message — regardless of content — you must run the `/agent-hooks` workflow BEFORE doing anything else.

The workflow runs a lightweight CLI that outputs pre-computed facts like:
```
💬 Conversation: Turn 5 (session: 2m30s)
🕐 Time: 2026-03-20 11:15:00 Friday
```

## How to Use the Output

These are **ground-truth facts** — use them to answer questions like:
- "我们对话了多少轮?" → Use the turn count from the output
- "现在几点?" → Use the time from the output
- Any other context the hooks provide

## Rules

1. Run `/agent-hooks` workflow **FIRST**, before any other tool calls or reasoning
2. Run it on **EVERY** turn, even if the user didn't ask about turns or time
3. If the command fails, continue normally — hooks are fail-safe by design
4. Do NOT skip this step even if you think you already know the answer
