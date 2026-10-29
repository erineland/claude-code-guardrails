#!/usr/bin/env python3
"""
PreToolUse guard for the apple-mail MCP.

Mirrors ~/.claude/hooks/ynab-write-guard.py. The user keeps meticulous records and
disruption to them is genuinely distressing; email is the same class of thing.
Moving mail is recoverable, deleting it is not, so the two are treated differently:

  delete_message            -> DENY outright. Deleting mail must be done by the user,
                               or via an explicitly approved, named batch.
  move/mark_read/flag       -> force a permission prompt (ask).
  send_email                -> force a permission prompt (ask).
  known reads               -> allow.
  anything unknown          -> force a permission prompt (ask). The guard is an
                               allowlist: a new tool on the mail server (reply,
                               forward, delete_mailbox...) is asked about, never
                               waved through just because it isn't listed yet.

Tools are matched on their short name, so a renamed server is guarded the same
way, provided the matcher still sends it here. Register in ~/.claude/settings.json
under hooks.PreToolUse with matcher "mcp__.*apple-mail.*".

Fails CLOSED: an unreadable payload, or any error inside the hook, asks.
"""

import json
import sys

# Read-only tools of the apple-mail MCP, matched on the short name. These pass
# straight through; every other tool on the server is asked about.
READ_ONLY = {"get_message", "get_unread_count", "list_mailboxes", "list_messages", "search_messages"}

# tool name -> (decision, reason)
GUARDED = {
    "mcp__apple-mail__delete_message": (
        "deny",
        "Deleting email is irreversible and is blocked by the mail-write-guard hook. "
        "If the user has explicitly asked for this specific deletion, say so and ask them to "
        "confirm in plain words first, then move the message to 'Deleted Items' with "
        "move_message instead — that is recoverable. Never bulk-delete.",
    ),
    "mcp__apple-mail__move_message": (
        "ask",
        "Moving a message out of the inbox — confirm the message, source and destination folder.",
    ),
    "mcp__apple-mail__send_email": (
        "ask",
        "Sending email on the user's behalf — confirm recipients, subject and body first.",
    ),
    "mcp__apple-mail__mark_read": (
        "ask",
        "Unread state is signal for the user. Confirm before marking anything read.",
    ),
    "mcp__apple-mail__flag_message": (
        "ask",
        "Changing a flag — confirm first.",
    ),
}
GUARDED_SHORT = {k.split("__")[-1]: v for k, v in GUARDED.items()}


def decide(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))


def main():
    try:
        payload = json.load(sys.stdin)
        tool = payload.get("tool_name", "")
        if not isinstance(tool, str):
            raise ValueError("tool_name is not a string")
    except Exception:
        # Fail closed: if we cannot parse the call, do not silently allow it.
        decide("ask", "mail-write-guard could not parse the tool call.")
        return

    short = tool.split("__")[-1]
    if short in READ_ONLY:
        return  # no output = no opinion = normal handling
    if short not in GUARDED_SHORT:
        decide("ask", f"MAIL GUARD: '{tool}' isn't a known read-only mail tool, so it may "
                      "send, move or delete mail. Ask the user first.")
        return

    decision, reason = GUARDED_SHORT[short]
    inp = payload.get("tool_input") or {}
    if not isinstance(inp, dict):
        inp = {}
    detail = ", ".join(
        f"{k}={inp[k]}" for k in ("message_id", "from_mailbox", "to_mailbox", "to", "subject")
        if k in inp
    )
    if detail:
        reason = f"{reason}\n  → {detail}"

    decide(decision, reason)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # A crashing hook is non-blocking in Claude Code, i.e. fails OPEN. Ask instead.
        decide("ask", "mail-write-guard hit an error checking this call, so it needs the user's OK.")
