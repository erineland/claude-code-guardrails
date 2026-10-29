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

# Every YNAB tool known to mutate state, with a description for the prompt.
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

# The 23 read-only tools of @maro-org/ynab-mcp 0.8.0 (checked Oct 2026). Any OTHER tool on a
# YNAB server (a new write tool, or the same tools under a renamed server) is asked about too.
READ_ONLY = {
    "detect_anomalies", "detect_recurring_charges", "diagnose_credit_card_debt",
    "forecast_category_balances", "get_accounts", "get_budget_health", "get_budget_summary",
    "get_income_expense_summary", "get_monthly_budget", "get_scheduled_transactions",
    "get_spending_analysis", "get_spending_breakdown", "get_spending_trends",
    "get_spending_velocity", "get_targets", "list_budgets", "list_categories",
    "list_undo_history", "search_transactions", "suggest_budget_allocation",
    "suggest_overspending_coverage", "suggest_transaction_categories", "sync_budget_data",
}
GUARDED_SHORT = {k.split("__")[-1]: v for k, v in GUARDED.items()}

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


def ask(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }))
    sys.exit(0)


def main():
    try:
        payload = json.load(sys.stdin)
        tool_name = payload.get("tool_name", "")
        if not isinstance(tool_name, str):
            raise ValueError("tool_name is not a string")
    except Exception:
        # fail CLOSED: an unreadable payload is asked about, never waved through
        ask("YNAB WRITE GUARD: couldn't read this YNAB call, so it needs the user's OK.")

    parts = tool_name.split("__")
    short = parts[-1]
    # Read-only tool on a YNAB server: stay out of the way entirely.
    if short in READ_ONLY:
        sys.exit(0)
    if tool_name not in GUARDED and short not in GUARDED_SHORT:
        ask(f"YNAB WRITE GUARD: '{tool_name}' is not one of the known read-only YNAB tools, "
            "so it may change the user's budget. Ask them first.")

    action = GUARDED.get(tool_name) or GUARDED_SHORT[short]
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
    if tool_name in BALANCE_SAFE or short == "delete_scheduled_transactions":
        footer += (
            " Note: deleting a SCHEDULE leaves its existing instances in place, "
            "so the account balance will not move."
        )

    ask("\n".join([header, ""] + detail + ["", footer]))


if __name__ == "__main__":
    main()
