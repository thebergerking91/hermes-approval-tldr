"""Exercise release publication with fake subprocesses, never remote writes."""
import importlib.util
import json
from pathlib import Path
import subprocess
from unittest import TestCase, mock

PATH = Path(__file__).resolve().parents[1] / "scripts" / "release.py"
spec = importlib.util.spec_from_file_location("release_helper", PATH)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(TestCase):
    def run_case(self, responses):
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            result = responses.pop(0)
            return subprocess.CompletedProcess(args, *result)

        with mock.patch.object(release.subprocess, "run", side_effect=run):
            result = release.publish("owner/repo", "v1.0.0", "a" * 40, "/tmp/notes")
        self.assertFalse(responses)
        return result, calls

    @staticmethod
    def ok(data):
        return (0, json.dumps(data), "")

    def initial(self, obj=None):
        return [(0, "a" * 40 + "\n", ""), self.ok({"object": obj or {"type": "commit", "sha": "a" * 40}})]

    def test_create_missing(self):
        result, calls = self.run_case(self.initial() + [(1, "", "gh: Not Found (HTTP 404)"), (0, "created", ""), self.ok({"tag_name": "v1.0.0", "draft": False, "prerelease": False})])
        self.assertEqual(result, 0)
        self.assertEqual(calls[-2][:3], ["gh", "release", "create"])
        self.assertIn("--verify-tag", calls[-2])

    def test_created_release_readback_failure_is_fatal(self):
        result, calls = self.run_case(self.initial() + [(1, "", "gh: Not Found (HTTP 404)"), (0, "created", ""), (1, "", "network error")])
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 5)

    def test_existing_matching_is_not_altered(self):
        result, calls = self.run_case(self.initial() + [self.ok({"tag_name": "v1.0.0", "draft": False, "prerelease": False})])
        self.assertEqual(result, 0)
        self.assertFalse(any(c[1:3] == ["release", "create"] for c in calls))

    def test_annotated_tag_is_peeled(self):
        data = self.initial({"type": "tag", "sha": "b" * 40}) + [self.ok({"object": {"type": "commit", "sha": "a" * 40}}), self.ok({"tag_name": "v1.0.0", "draft": False, "prerelease": False})]
        result, calls = self.run_case(data)
        self.assertEqual(result, 0)
        self.assertIn("git/tags/" + "b" * 40, calls[2][-1])

    def test_remote_mismatch_stops(self):
        result, calls = self.run_case(self.initial({"type": "commit", "sha": "b" * 40}))
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 2)

    def test_release_mismatch_stops(self):
        for change in ({"tag_name": "v2.0.0"}, {"draft": True}, {"prerelease": True}, {"draft": None}):
            with self.subTest(change=change):
                data = {"tag_name": "v1.0.0", "draft": False, "prerelease": False}
                data.update(change)
                result, calls = self.run_case(self.initial() + [self.ok(data)])
                self.assertEqual(result, 1)
                self.assertEqual(len(calls), 3)

    def test_auth_and_network_errors_are_not_missing(self):
        for error in ("gh: Bad credentials (HTTP 401)", "network error", "gh: Forbidden (HTTP 403)"):
            with self.subTest(error=error):
                result, calls = self.run_case(self.initial() + [(1, "", error)])
                self.assertEqual(result, 1)
                self.assertEqual(len(calls), 3)

    def test_create_failure_is_fatal(self):
        result, calls = self.run_case(self.initial() + [(1, "", "gh: Not Found (HTTP 404)"), (1, "", "HTTP 422 already exists")])
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 4)

    def test_tag_api_failure_is_fatal(self):
        result, calls = self.run_case([(0, "a" * 40, ""), (1, "", "gh: Not Found (HTTP 404)")])
        self.assertEqual(result, 1)
        self.assertEqual(len(calls), 2)
