---
description: how to discover and use installed agent skills from ~/.agents/skills/
---

# Check Installed Skills

Before searching the web or using manual approaches for specialized capabilities, always check for pre-installed skills.

## Steps

1. List the contents of `~/.agents/skills/` to see all globally installed skills
```bash
ls ~/.agents/skills/
```

2. If a relevant skill is found, read its SKILL.md
```bash
cat ~/.agents/skills/<skill-name>/SKILL.md
```

3. Follow the instructions documented in the SKILL.md file

## Example

If the user asks to "find a skill" or "search skills.sh":
- Check if `~/.agents/skills/find-skills/` exists
- Read its SKILL.md
- Run `npx skills find <query>` as documented
