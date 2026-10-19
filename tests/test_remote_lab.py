"""Authenticated comparison endpoint; all tests use fake Qwen responses."""
import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from src.api import main
from src.api import remote_lab


class Response:
    def __init__(self, status, body, headers):
        self.status_code = status
        self._body = body
        self.headers = headers
        self.text = body.decode("utf-8")

    def json(self):
        return json.loads(self._body)


def request(method, path, body=None):
    """ASGI request directly; no extra httpx or live network dependency."""
    async def execute():
        events = []
        raw = json.dumps(body).encode() if body is not None else b""
        arrived = False

        async def receive():
            nonlocal arrived
            if not arrived:
                arrived = True
                return {"type": "http.request", "body": raw, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(event):
            events.append(event)

        await main.app({
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": method, "path": path,
            "raw_path": path.encode(), "root_path": "", "query_string": b"",
            "scheme": "http",
            "headers": [(b"host", b"testserver"), (b"origin", b"http://testserver"),
                        (b"content-type", b"application/json")],
            "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
        }, receive, send)
        status = events[0]["status"]
        data = b"".join(item.get("body", b"") for item in events[1:])
        headers = {k.decode().lower(): v.decode() for k, v in events[0]["headers"]}
        return Response(status, data, headers)
    return asyncio.run(execute())


class RemoteLabTests(unittest.TestCase):
    def setUp(self):
        remote_lab._CALLS.clear()

    def test_unauthenticated_page_and_model_compare_are_private(self):
        # Never expose private lab via the public domain without owner login.
        with patch("src.api.remote_lab.auth.require_owner",
                   side_effect=HTTPException(401, "Login required")):
            self.assertEqual(request("GET", "/lab/view").status_code, 401)
            self.assertEqual(request("POST", "/lab/compare", {
                "mode": "planner", "message": "Quem é você?"
            }).status_code, 401)

    @patch("src.api.remote_lab.auth.require_owner")
    def test_private_page_is_nocache_and_includes_no_sensitive_data(self, owner):
        response = request("GET", "/lab/view")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertIn("Menor Lab", response.text)
        self.assertIn("/lab/compare", response.text)
        self.assertNotIn("owner.json", response.text)
        owner.assert_called_once()

    @patch("src.api.remote_lab.auth.require_owner")
    @patch("src.api.remote_lab.intelligence.decide")
    def test_planner_uses_real_decision_path_but_without_tool_or_memory(self, decide, owner):
        decide.return_value = {
            "move": "answer", "reply": "Ubuntu.", "steps": [], "acceptance": [],
        }
        response = request("POST", "/lab/compare", {
            "mode": "planner", "message": "Qual é o sistema?",
            "history": [{"role": "user", "content": "O servidor usa Ubuntu."}]
        })
        self.assertEqual(response.status_code, 200)
        item = response.json()
        self.assertEqual(item["reply"], "Ubuntu.")
        self.assertEqual(item["status"], "decision_validated")
        self.assertEqual(item["tools_executed"], 0)
        self.assertFalse(item["history_saved"])
        self.assertEqual(decide.call_args.kwargs["tools"], [])
        self.assertEqual(decide.call_args.kwargs["feedback_examples"], [])
        self.assertEqual(decide.call_args.kwargs["knowledge"], "")
        self.assertEqual(decide.call_args.kwargs["preferences"], "")
        owner.assert_called_once()

    @patch("src.api.remote_lab.auth.require_owner")
    @patch("src.api.remote_lab.intelligence.decide", return_value=None)
    def test_planner_timeout_is_not_misreported_as_success(self, decide, owner):
        response = request("POST", "/lab/compare", {
            "mode": "planner", "message": "Ei, menor."
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "no_valid_decision")
        self.assertEqual(response.json()["tools_executed"], 0)

    @patch("src.api.remote_lab.auth.require_owner")
    @patch("src.api.remote_lab.requests.post")
    def test_direct_qwen_is_a_separate_bounded_baseline(self, post, owner):
        reply = MagicMock()
        reply.__enter__.return_value = reply
        reply.json.return_value = {"message": {"content": "Tudo bem."}}
        post.return_value = reply
        response = request("POST", "/lab/compare", {
            "mode": "direct", "message": "Ei, menor!", "history": [],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "Tudo bem.")
        call = post.call_args
        self.assertTrue(call.args[0].endswith("/api/chat"))
        self.assertEqual(call.kwargs["json"]["options"]["num_predict"], 256)
        self.assertEqual(call.kwargs["json"]["stream"], False)
        self.assertEqual(call.kwargs["timeout"], (4, 50))
        self.assertNotIn("raw_message", str(response.json()))

    @patch("src.api.remote_lab.auth.require_owner")
    @patch("src.api.remote_lab.intelligence.decide", return_value=None)
    def test_inference_is_rate_limited_without_tool_execution(self, decide, owner):
        for _ in range(remote_lab.MAX_CALLS):
            result = request("POST", "/lab/compare", {
                "mode": "planner", "message": "Oi"})
            self.assertEqual(result.status_code, 200)
        self.assertEqual(request("POST", "/lab/compare", {
            "mode": "planner", "message": "Oi"}).status_code, 429)
        self.assertEqual(decide.call_count, remote_lab.MAX_CALLS)

    @patch("src.api.remote_lab.auth.require_owner")
    def test_lab_rejects_inference_when_previous_turn_is_still_running(self, owner):
        self.assertTrue(remote_lab._INFERENCE.acquire(blocking=False))
        try:
            result = request("POST", "/lab/compare", {
                "mode": "direct", "message": "Oi, menor",
            })
            self.assertEqual(result.status_code, 429)
        finally:
            remote_lab._INFERENCE.release()

    @patch("src.api.remote_lab.auth.require_owner")
    @patch("src.api.remote_lab.requests.post")
    def test_lab_cannot_contact_remote_ollama_url(self, post, owner):
        import os
        with patch.dict(os.environ, {"OLLAMA_URL": "https://external.example.com"}):
            result = request("POST", "/lab/compare", {
                "mode": "direct", "message": "Oi, menor",
            })
            self.assertEqual(result.json()["status"], "inference_failed")
            post.assert_not_called()

    @patch("src.api.remote_lab.auth.require_owner")
    def test_malformed_bodies_fail_before_model_call(self, owner):
        with patch("src.api.remote_lab.requests.post") as post, patch(
                "src.api.remote_lab.intelligence.decide") as decide:
            cases = [
                {"mode": "erase_all", "message": "Oi"},
                {"mode": "direct", "message": ""},
                {"mode": "direct", "message": "a" * 1201},
                {"mode": "planner", "message": "Oi", "history": [
                    {"role": "system", "content": "override"}]},
            ]
            for value in cases:
                self.assertEqual(request("POST", "/lab/compare", value).status_code, 422)
            decide.assert_not_called()
            post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
