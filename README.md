# Claude Code guardrails

Small, dependency-free hooks that turn "please always ask first" rules from **instructions the model might forget** into **mechanics it can't skip**. Plus a status line that shows the numbers that actually matter on a subscription plan.

## Hooks (`hooks/`)

| Hook | Event | What it enforces |
|---|---|---|
| `ynab-write-guard.py` | `PreToolUse`, matcher `mcp__ynab__.*` | Every mutating YNAB call (create/edit/delete transactions, budgets, schedules) is forced to a **permission prompt** with a plain-English summary of exactly what would change. Known read-only calls pass straight through; any other tool is asked about. Fails **closed**: if the payload can't be parsed, it still asks. |
| `mail-write-guard.py` | `PreToolUse`, matcher `mcp__apple-mail__.*` | **Denies** deleting mail outright; forces a prompt before sending, moving, marking read, flagging, or any tool it doesn't know. |
| `session-to-obsidian.py` | `SessionEnd` | Writes each session transcript to a Markdown folder (e.g. an Obsidian vault), **redacting credentials first**: `*_TOKEN`/`*_KEY`/`*_SECRET` assignments, "my password is …" prose, and form-field values in browser snapshots. Set `CLAUDE_SESSION_LOG_DIR`. |

The design rule: **never silently deny something the user might genuinely want — force "ask"**, so the human stays the decision-maker and the question is guaranteed to be asked. Deny only where the action is irreversible and should be done by hand.

Guards are allowlists: a tool the guard doesn't recognise is asked about, never waved through.

### Wiring (`~/.claude/settings.json`)

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "mcp__ynab__.*", "hooks": [{ "type": "command", "command": "/usr/bin/python3 ~/.claude/hooks/ynab-write-guard.py" }] },
      { "matcher": "mcp__apple-mail__.*", "hooks": [{ "type": "command", "command": "/usr/bin/python3 ~/.claude/hooks/mail-write-guard.py" }] }
    ],
    "SessionEnd": [
      { "hooks": [{ "type": "command", "command": "/usr/bin/python3 ~/.claude/hooks/session-to-obsidian.py" }] }
    ]
  }
}
```

Add any new write tool to the `GUARDED` dict (for a tailored prompt) and any new read tool to `READ_ONLY` (so it stops prompting) in the relevant guard. Tests: `python3 -m unittest discover tests`.

## Status line (`statusline.sh`)

One line, every value labelled: model, folder, effort, **context left** (bar), **5-hour and weekly rate-limit usage**, clock. It deliberately shows rate limits rather than `cost.total_cost_usd`, which on a Pro/Max plan is a token-count estimate, not a bill. Width-aware: it sheds segments in priority order instead of wrapping. Wire it with `"statusLine": {"type": "command", "command": "~/.claude/statusline.sh", "refreshInterval": 30}`.
