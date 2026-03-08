# Prompt Enhancement Design: Web Search + Idea Generation

## Goal

Enhance program.md template to enable AI agents to search for latest related work (papers, GitHub repos, blogs) and use structured idea generation strategies for better experiment quality.

## Key Changes

### 1. New Phase: Literature Review (Phase 2)

Insert between "Understand Project" and "Design Evaluation":

- Agent searches the web for related papers, repos, blog posts
- Generates `.research/literature.md` with structured findings
- Generates `.research/ideas.md` as prioritized idea backlog
- Uses agent's built-in tools (WebSearch for Claude Code, browsing for Codex)
- Graceful fallback for agents without web access

### 2. Enhanced Experiment Loop (Phase 5)

- Replace vague "think of an improvement" with structured strategy:
  1. Literature-first (pick from ideas.md)
  2. Result-driven (variations of successful experiments)
  3. Ablation studies
  4. Diverse exploration (switch categories every 3+ same-category experiments)
- Add idea refresh every N experiments (configurable, default 5)
- Anti-patterns list to prevent common failure modes

### 3. New Template Files

- `literature.md.j2` — structured literature review template
- `ideas.md.j2` — prioritized idea backlog template

### 4. Config Extension

```yaml
research:
  web_search: true
  search_interval: 5
```

### 5. Agent Capability Awareness

Prompt includes instructions for both web-capable and non-web agents:
- Web-capable: use search tools during Phase 2 and periodic refresh
- Non-web: rely on training knowledge + repo documentation

## Files to Modify

- `src/open_researcher/templates/program.md.j2` — major rewrite (4 → 5 phases + enhanced loop)
- `src/open_researcher/templates/config.yaml.j2` — add research section
- Create: `src/open_researcher/templates/literature.md.j2`
- Create: `src/open_researcher/templates/ideas.md.j2`
- `src/open_researcher/init_cmd.py` — render 2 new templates
- `src/open_researcher/status_cmd.py` — detect Phase 2 (literature review)
- `tests/test_init.py` — verify new files created
- `tests/test_status.py` — verify Phase 2 detection
