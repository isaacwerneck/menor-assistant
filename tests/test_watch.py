import os
import tempfile
import unittest
from unittest.mock import patch

from src.agent.watch import review
from src.tools.audit import record


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"MENOR_DATA_DIR": self.tmp.name,
                                   "MENOR_AUTODEV_ENABLED": "0", "MENOR_GITHUB_TOKEN": ""})
        env.start()
        self.addCleanup(env.stop)

    def test_no_events_does_not_make_proposals(self):
        with patch("src.agent.watch.propose") as proposal:
            self.assertEqual(review()["status"], "no-action")
            proposal.assert_not_called()

    def test_unrelated_provider_failures_never_trigger_code_edits(self):
        for _ in range(4):
            record("images.generate", "failed")
        with patch("src.agent.watch.propose") as proposal:
            self.assertEqual(review()["status"], "no-action")
            proposal.assert_not_called()

    def test_router_failures_produce_at_most_one_daily_review(self):
        for _ in range(3):
            record("agent.route", "failed")
        with patch("src.agent.watch.propose") as proposal:
            response = review()
            self.assertEqual(response["status"], "pending-configuration")
            self.assertEqual(review()["status"], "already-reviewed")
            proposal.assert_not_called()

    def test_enabled_watch_can_propose_one_draft_pr_per_day(self):
        for _ in range(3):
            record("agent.resolve", "failed")
        with patch.dict(os.environ, {
            "MENOR_AUTODEV_ENABLED": "1", "MENOR_GITHUB_TOKEN": "fake",
        }):
            with patch("src.agent.watch.propose") as proposal:
                proposal.return_value = {
                    "status": "pr_created", "pr": 42, "requires_review": True,
                }
                result = review()
                self.assertEqual(result["status"], "review-opened")
                self.assertEqual(result["result"]["pr"], 42)
                self.assertEqual(review()["status"], "already-reviewed")
                proposal.assert_called_once()


if __name__ == "__main__":
    unittest.main()
