#!/usr/bin/env python3
"""
PreToolUse guard for YNAB write operations.

The user's standing rule is that no YNAB transaction may be created, edited or
deleted without explicit per-action confirmation. Until now that rule lived only
in CLAUDE.md, which means it held only as long as the model remembered it.
This hook makes it structural: every mutating YNAB call is forced to a
permission prompt, with a plain-English summary of exactly what would change.

It never silently denies. It forces "ask", so the user stays the decision-maker —
the point is that the question is guaranteed to be asked, not that the tool is
blocked.

Fails CLOSED: if anything goes wrong parsing the payload, it still asks.
"""

import json
import sys

# Every YNAB tool that mutates state. Read-only tools are not listed and pass
# straight through without a prompt.
GUARDED = {
    "mcp__ynab__create_transactions": "create transaction(s)",
    "mcp__ynab__update_transactions": "EDIT existing transaction(s)",
    "mcp__ynab__delete_transactions": "DELETE transaction(s)",
    "mcp__ynab__create_scheduled_transactions": "create scheduled transaction(s)",
    "mcp__ynab__update_scheduled_transactions": "edit scheduled transaction(s)",
    "mcp__ynab__delete_scheduled_transactions": "delete scheduled transaction(s)",
    "mcp__ynab__set_category_budgets": "change category budget amount(s)",
    "mcp__ynab__set_category_targets": "change category target(s)",
    "mcp__ynab__undo_operations": "UNDO a previous YNAB operation",
}

# Deleting a schedule leaves its already-generated instances intact, so the
# account balance does not move. Worth saying, because it changes the risk.
BALANCE_SAFE = {"mcp__ynab__delete_scheduled_transactions"}


def money(value):
    try:
        return f"£{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def describe(tool_name, tool_input):
    """Build a human-readable summary of the pending change."""
    lines = []

    for key in ("transactions", "scheduled_transactions"):
        items = tool_input.get(key)
        if isinstance(items, list):
            for t in items[:12]:
                if not isinstance(t, dict):
                    continue
                bits = [
                    t.get("date") or t.get("date_first") or "?",
                    str(t.get("payee_name") or t.get("payee_id") or "?"),
                    money(t.get("amount")),
                ]
                if t.get("memo"):
                    bits.append(f"memo={t['memo']!r}")
                lines.append("  - " + "  ".join(bits))
            if len(items) > 12:
                lines.append(f"  … and {len(items) - 12} more")

    for key in ("transaction_ids", "scheduled_transaction_ids"):
        ids = tool_input.get(key)
        if isinstance(ids, list):
            for i in ids[:12]:
                lines.append(f"  - id {i}")
            if len(ids) > 12:
                lines.append(f"  … and {len(ids) - 12} more")

    for key in ("budgets", "targets", "categories"):
        items = tool_input.get(key)
        if isinstance(items, list):
            for c in items[:12]:
                if isinstance(c, dict):
                    name = c.get("category_name") or c.get("category_id") or "?"
                    amt = c.get("budgeted", c.get("amount", c.get("target_amount")))
                    lines.append(f"  - {name}: {money(amt)}")

    if not lines:
        # Unrecognised shape: show the raw payload rather than pretending to know.
        raw = json.dumps(tool_input, ensure_ascii=False)
        lines.append("  " + (raw[:600] + "…" if len(raw) > 600 else raw))

    return lines


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}

    tool_name = payload.get("tool_name", "")

    # Not a guarded tool: stay out of the way entirely.
    if tool_name not in GUARDED:
        sys.exit(0)

    action = GUARDED[tool_name]
    tool_input = payload.get("tool_input") or {}

    try:
        detail = describe(tool_name, tool_input)
    except Exception as e:  # fail closed, but say why
        detail = [f"  (could not summarise payload: {e})"]

    header = f"YNAB WRITE GUARD — about to {action}."
    footer = (
        "The user's standing rule: never create, edit or delete a YNAB transaction "
        "without explicit per-action confirmation. Every transaction individually "
        "unless a batch was explicitly approved."
    )
    if tool_name in BALANCE_SAFE:
        footer += (
            " Note: deleting a SCHEDULE leaves its existing instances in place, "
            "so the account balance will not move."
        )

    reason = "\n".join([header, ""] + detail + ["", footer])

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


if __name__ == "__main__":
    main()
