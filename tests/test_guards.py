"""Run with: python3 -m unittest discover tests"""

import json
import pathlib
import subprocess
import sys
import unittest

HOOKS = pathlib.Path(__file__).resolve().parent.parent / "hooks"


def run(hook, payload):
    """Feed a PreToolUse payload to a hook; return its decision, or None for no opinion."""
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    out = subprocess.run([sys.executable, str(HOOKS / hook)], input=stdin,
                         capture_output=True, text=True, check=True).stdout.strip()
    return json.loads(out)["hookSpecificOutput"]["permissionDecision"] if out else None


class MailGuard(unittest.TestCase):
    def test_read_tool_passes(self):
        self.assertIsNone(run("mail-write-guard.py", {"tool_name": "mcp__apple-mail__search_messages"}))

    def test_delete_is_denied(self):
        self.assertEqual(run("mail-write-guard.py", {"tool_name": "mcp__apple-mail__delete_message"}), "deny")

    def test_send_asks(self):
        self.assertEqual(run("mail-write-guard.py", {"tool_name": "mcp__apple-mail__send_email"}), "ask")

    def test_unknown_tool_asks(self):
        self.assertEqual(run("mail-write-guard.py", {"tool_name": "mcp__apple-mail__forward_email"}), "ask")

    def test_garbage_payload_asks(self):
        self.assertEqual(run("mail-write-guard.py", "not json"), "ask")

    def test_non_dict_payload_asks(self):
        self.assertEqual(run("mail-write-guard.py", "[]"), "ask")

    def test_odd_tool_input_still_decides(self):
        self.assertEqual(run("mail-write-guard.py", {"tool_name": "mcp__apple-mail__send_email",
                                                     "tool_input": "to=someone"}), "ask")

    def test_renamed_server_delete_still_denied(self):
        self.assertEqual(run("mail-write-guard.py", {"tool_name": "mcp__apple-mail-2__delete_message"}), "deny")


class YnabGuard(unittest.TestCase):
    def test_read_tool_passes(self):
        self.assertIsNone(run("ynab-write-guard.py", {"tool_name": "mcp__ynab__get_accounts"}))

    def test_write_asks(self):
        self.assertEqual(run("ynab-write-guard.py", {"tool_name": "mcp__ynab__create_transactions",
                                                     "tool_input": {"transactions": []}}), "ask")

    def test_unknown_tool_asks(self):
        self.assertEqual(run("ynab-write-guard.py", {"tool_name": "mcp__ynab__import_transactions"}), "ask")

    def test_renamed_server_write_asks(self):
        self.assertEqual(run("ynab-write-guard.py", {"tool_name": "mcp__ynab-personal__delete_transactions"}), "ask")

    def test_garbage_payload_asks(self):
        self.assertEqual(run("ynab-write-guard.py", "not json"), "ask")

    def test_non_dict_payload_asks(self):
        self.assertEqual(run("ynab-write-guard.py", "[]"), "ask")

    def test_odd_tool_input_still_asks(self):
        self.assertEqual(run("ynab-write-guard.py", {"tool_name": "mcp__ynab__create_transactions",
                                                     "tool_input": "oops"}), "ask")


class Matchers(unittest.TestCase):
    """The README's matchers decide which tools a guard ever sees."""

    def test_matchers_catch_renames(self):
        import re
        readme = (HOOKS.parent / "README.md").read_text()
        for matcher, caught in (("mcp__.*ynab.*", ["mcp__ynab__get_accounts", "mcp__plugin_ynab_ynab__create_transactions"]),
                                ("mcp__.*apple-mail.*", ["mcp__apple-mail__send_email", "mcp__apple-mail-2__delete_message"])):
            self.assertIn(f'"matcher": "{matcher}"', readme)
            for tool in caught:
                self.assertTrue(re.fullmatch(matcher, tool), tool)


if __name__ == "__main__":
    unittest.main()
