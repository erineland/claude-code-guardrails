#!/usr/bin/env python3
import json
import os
import re
import sys
import datetime

VAULT_DIR = os.path.expanduser(
    os.environ.get("CLAUDE_SESSION_LOG_DIR", "~/Documents/Obsidian/Claude Code Sessions")
)

REDACT_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    # KEY/TOKEN/SECRET/PASSWORD as a substring of the name (e.g. YNAB_API_TOKEN, OBSIDIAN_API_KEY)
    re.compile(
        r'(?i)([A-Za-z0-9_]*(?:api[_-]?key|token|secret|password)[A-Za-z0-9_]*)'
        r'(["\']?\s*[:=]\s*["\']?)'
        r'([A-Za-z0-9_\-.]{8,})'
    ),
    re.compile(r"\b[a-f0-9]{32,}\b"),
    # A credential stated in PROSE, which the name=value patterns above all miss.
    # A user typing "Router password is '<secret>'" in chat once sailed straight
    # through into the vault. Group 3 is the secret; groups 1+2 are kept verbatim.
    re.compile(
        r"(?i)\b(password|passphrase|passcode|api[ _-]?key|secret key|auth token)\b"
        r"(\s*(?:is|was|=|:)\s*[\'\"\u2018\u201c]?)"
        r"([^\s\'\"\u2019\u201d\n]{6,})"
    ),
    # ...or rendered as a form field in a page dump, e.g. a Playwright accessibility
    # snapshot:  textbox "Password:" [ref=x]:  /placeholder: ""  text: <secret>
    re.compile(
        r"(?i)(password|passphrase|api[ _-]?key)(\"?[\s\S]{0,90}?\btext:[ \t]*)"
        r"([^\s\n]{6,})"
    ),
    # ... or simply quoted somewhere just after the word.
    re.compile(
        r"(?i)\b(password|passphrase|passcode|api[ _-]?key)\b"
        r"([^\n\'\"\u2018\u201c]{0,24}[\'\"\u2018\u201c])"
        r"([^\'\"\u2019\u201d\n]{6,})"
    ),
]


def redact(text):
    for pattern in REDACT_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def extract_text(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            parts.append(block.get("text", ""))
        elif block_type == "tool_use":
            parts.append(f"\n> 🔧 Tool call: `{block.get('name', 'unknown')}`\n")
        elif block_type == "tool_result":
            inner = block.get("content")
            snippet = ""
            if isinstance(inner, list):
                for c in inner:
                    if isinstance(c, dict) and c.get("type") == "text":
                        snippet += c.get("text", "")
            elif isinstance(inner, str):
                snippet = inner
            snippet = snippet[:800]
            parts.append(f"\n> Result: {snippet}\n")
    return "\n".join(parts)


def sanitize_cwd(cwd):
    return re.sub(r"[^A-Za-z0-9]", "-", cwd or "")


def resolve_transcript_path(hook_input):
    path = hook_input.get("transcript_path")
    if path and os.path.exists(path):
        return path
    session_id = hook_input.get("session_id")
    cwd = hook_input.get("cwd")
    if session_id and cwd:
        guess = os.path.expanduser(
            f"~/.claude/projects/{sanitize_cwd(cwd)}/{session_id}.jsonl"
        )
        if os.path.exists(guess):
            return guess
    return None


def main():
    try:
        hook_input = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return

    transcript_path = resolve_transcript_path(hook_input)
    if not transcript_path:
        return

    session_id = hook_input.get("session_id", "unknown-session")

    entries = []
    with open(transcript_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") not in ("user", "assistant"):
                continue
            message = record.get("message", {})
            role = message.get("role")
            text = extract_text(message.get("content"))
            if not text.strip():
                continue
            timestamp = record.get("timestamp", "")
            entries.append(f"### {role} — {timestamp}\n\n{text}\n")

    if not entries:
        return

    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")

    os.makedirs(VAULT_DIR, exist_ok=True)
    filename = f"{date_str}-{time_str}-{session_id[:8]}.md"
    filepath = os.path.join(VAULT_DIR, filename)

    header = (
        "---\n"
        "tags: [claude-code, session-log]\n"
        f"session_id: {session_id}\n"
        "---\n\n"
        f"# Claude Code Session — {date_str} {time_str}\n\n"
    )
    body = redact("\n---\n\n".join(entries))

    with open(filepath, "w") as f:
        f.write(header + body)


if __name__ == "__main__":
    main()
