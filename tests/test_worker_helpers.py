import importlib.util
import sys
import types
import unittest
from pathlib import Path

fake_workers = types.ModuleType("workers")


class _FakeResponse:
    def __init__(self, body=None, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = headers or {}


class _FakeWorkerEntrypoint:
    pass


async def _fake_fetch(*args, **kwargs):
    raise RuntimeError("fetch is not available in unit tests")


fake_workers.Response = _FakeResponse
fake_workers.WorkerEntrypoint = _FakeWorkerEntrypoint
fake_workers.fetch = _fake_fetch
sys.modules["workers"] = fake_workers

WORKER_PATH = (
    Path(__file__).resolve().parents[1] / "cloudflare-api" / "src" / "worker.py"
)
spec = importlib.util.spec_from_file_location("cf_worker_module", WORKER_PATH)
worker = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(worker)


class WorkerHelperTests(unittest.TestCase):
    def test_is_gmail_address(self):
        self.assertTrue(worker.is_gmail_address("user@gmail.com"))
        self.assertTrue(worker.is_gmail_address("USER@GMAIL.COM"))
        self.assertFalse(worker.is_gmail_address("user@example.com"))
        self.assertFalse(worker.is_gmail_address("user@gmail.com@x"))

    def test_require_fields_returns_missing(self):
        payload = {"name": "A", "topic": "", "message": "ok"}
        missing = worker.require_fields(payload, ["name", "topic", "message"])
        self.assertEqual(missing, ["topic"])

    def test_normalize_feedback_text_strips_lines_and_masks_at(self):
        value = "  hi@test.com \n\n second line  "
        normalized = worker.normalize_feedback_text(value, 120)
        self.assertIn("@\u200b", normalized)
        self.assertEqual(normalized.splitlines(), ["hi@\u200btest.com", "second line"])

    def test_clamp_text_adds_ellipsis(self):
        self.assertEqual(worker.clamp_text("abcdef", 4), "abc…")
        self.assertEqual(worker.clamp_text("abc", 4), "abc")

    def test_normalized_bool(self):
        self.assertTrue(worker.normalized_bool(True))
        self.assertTrue(worker.normalized_bool("yes"))
        self.assertFalse(worker.normalized_bool("no"))
        self.assertTrue(worker.normalized_bool(None, default=True))
        self.assertFalse(worker.normalized_bool(None, default=False))


if __name__ == "__main__":
    unittest.main()
