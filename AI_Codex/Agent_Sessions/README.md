# Agent Sessions

Operational journal entries for agent work.

Use filenames in this format:

```text
YYYY-MM-DD-HHMMSS-kebab-slug.md
```

Each session note should include frontmatter with at least:

```yaml
---
date: YYYY-MM-DD
type: session
---
```

Sessions form a doubly-linked chain: close an open session before opening a new one, and set `Previous Session` / `Next Session` links.
