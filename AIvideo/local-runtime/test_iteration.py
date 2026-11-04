"""State and isolation checks for the experiment runner."""

import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

import iterate


class IterationTests(unittest.TestCase):
    def test_resume_uses_existing_prompt_without_submitting(self):
        config = {"id": "resume-test", "backend": "photo", "width": 64, "height": 64, "seed": 1, "positive": "metal sphere"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            graph = iterate.photo_graph(config, "experiments/resume-test/raw")
            import hashlib
            fingerprint = hashlib.sha256(json.dumps({"config": config, "source_sha256": None, "graph": graph, "models": []}, sort_keys=True).encode()).hexdigest()
            record = {"id": "resume-test", "fingerprint": fingerprint, "status": "submitted", "prompt_id": "already-queued"}
            with patch.object(iterate, "ROOT", root), patch.object(iterate, "RECORDS", root / "records"), patch.object(iterate, "OUTPUTS", root / "outputs"), patch.object(iterate, "model_records", return_value=[]):
                iterate.write_json(root / "records/resume-test/record.json", record)
                def request(address, endpoint, data=None):
                    self.assertEqual(endpoint, "/history/already-queued")
                    raise TimeoutError("test polling interruption")
                with patch.object(iterate, "api", side_effect=request) as api:
                    with self.assertRaises(TimeoutError):
                        iterate.run_one(config, "http://127.0.0.1:8188")
                    self.assertEqual(api.call_count, 1)
                self.assertEqual(json.loads((root / "records/resume-test/record.json").read_text())["status"], "submitted")

    def test_changed_take_cannot_overwrite_completed_or_pending_work(self):
        for status in ("completed", "submitted"):
            with self.assertRaisesRegex(ValueError, "new experiment id"):
                iterate.action_for({"status": status, "fingerprint": "old"}, "new")

    def test_ambiguous_submission_is_not_automatically_requeued(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            iterate.action_for({"status": "prepared", "fingerprint": "same"}, "same")

    def test_fork_changes_requested_fields_without_mutating_source(self):
        plan = {"defaults": {"width": 832, "height": 480}, "runs": [{"id": "source", "backend": "photo", "seed": 1, "positive": "metal"}]}
        result = iterate.fork_plan(plan, "source", "seed-two", ["seed=2"], "seed only")
        self.assertEqual(len(plan["runs"]), 1)
        self.assertEqual(plan["runs"][0]["seed"], 1)
        self.assertEqual(result["runs"][-1]["seed"], 2)
        self.assertEqual(result["runs"][-1]["positive"], "metal")
        with self.assertRaises(ValueError):
            iterate.fork_plan(result, "source", "seed-two", [], "duplicate")

    def test_invalid_ids_and_sampler_splits_are_rejected_before_api(self):
        with self.assertRaises(ValueError):
            iterate.validate({"id": "../escape", "backend": "photo"})
        with self.assertRaises(ValueError):
            iterate.validate({"id": "bad-split", "backend": "wan14b", "width": 832, "height": 480, "frames": 49, "fps": 16, "steps": 20, "split_step": 20})

    def test_concurrent_campaign_cannot_reach_the_submission_loop(self):
        from filelock import FileLock
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plan = root / "plan.json"
            plan.write_text(json.dumps({"runs": [{"id": "take", "backend": "import"}]}))
            with FileLock(str(root / "iteration.lock"), timeout=0), patch.object(iterate, "RUNTIME", root), patch.object(sys, "argv", ["iterate.py", "--plan", str(plan)]), patch.object(iterate, "run_one") as run:
                with self.assertRaisesRegex(RuntimeError, "holds the local lock"):
                    iterate.main()
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
