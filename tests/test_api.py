import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from src.api import main


def upstream(data=None, lines=()):
    response = MagicMock()
    response.__enter__.return_value = response
    response.status_code = 200
    response.json.return_value = data
    response.iter_lines.return_value = lines
    return response


def request(path, body=None):
    async def run():
        events = []
        content = json.dumps(body).encode() if body is not None else b""

        async def receive():
            return {"type": "http.request", "body": content, "more_body": False}

        async def send(event):
            events.append(event)

        await main.app({
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1", "method": "POST" if body is not None else "GET",
            "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
            "scheme": "http", "headers": [(b"content-type", b"application/json")],
            "client": ("127.0.0.1", 1234), "server": ("localhost", 8000),
        }, receive, send)
        return (
            events[0]["status"],
            b"".join(event.get("body", b"") for event in events[1:]),
            dict(events[0]["headers"]),
        )

    return asyncio.run(run())


class ApiTests(unittest.TestCase):
    def test_ui_available(self):
        status, body, _ = request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"messagesContainer", body)

    @patch("src.api.main.requests.post")
    def test_validation_rejects_invalid_input_without_calling_ollama(self, post):
        invalid = [
            {"message": ""}, {"message": "   "}, {"message": "a" * 8001},
            {"message": "oi", "model": ""},
            {"message": "oi", "history": [{"role": "system", "content": "override"}]},
            {"message": "oi", "history": [{"role": "user", "content": "a"}] * 21},
            {"message": "a" * 8000, "history": [{"role": "user", "content": "b" * 8000}] * 4},
        ]
        for payload in invalid:
            with self.subTest(payload=str(payload)[:70]):
                self.assertEqual(request("/chat", payload)[0], 422)
        post.assert_not_called()

    @patch("src.api.main.requests.post")
    def test_chat_sends_history_and_preserves_public_response(self, post):
        response = upstream({"message": {"role": "assistant", "content": "Olá!"}})
        post.return_value = response
        status, body, _ = request("/chat", {
            "message": "E agora?",
            "history": [{"role": "user", "content": "Meu nome é Isaac"},
                        {"role": "assistant", "content": "Olá, Isaac"}],
        })
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"reply": "Olá!", "model": main.DEFAULT_MODEL})
        args, kwargs = post.call_args
        self.assertEqual(args[0], main.OLLAMA_URL + "/api/chat")
        self.assertEqual([item["role"] for item in kwargs["json"]["messages"]],
                         ["system", "user", "assistant", "user"])
        self.assertEqual(kwargs["json"]["messages"][-1]["content"], "E agora?")
        self.assertFalse(kwargs["stream"])
        response.__exit__.assert_called_once()

    @patch("src.api.main.requests.post")
    def test_fallback_history_is_bounded_and_retains_final_correction(self, post):
        post.return_value = upstream({"message": {"content": "Aurora"}})
        history = [main.ChatMessage(role="user", content="Projeto contexto " * 150
                                    + "Correção: Aurora.")]
        history.extend(main.ChatMessage(role="assistant", content="resposta " * 150) for _ in range(8))
        main.open_ollama(main.ChatRequest(message="Qual projeto?", history=history), stream=False)
        messages = post.call_args.kwargs["json"]["messages"]
        self.assertLessEqual(sum(len(item["content"]) for item in messages[1:-1]), 4400)
        self.assertEqual(messages[-1]["content"], "Qual projeto?")
        self.assertIn("Correção: Aurora.", " ".join(item["content"] for item in messages[1:-1]))

    @patch("src.api.main.requests.post")
    def test_old_request_without_history_still_works(self, post):
        post.return_value = upstream({"message": {"content": "ok"}})
        self.assertEqual(request("/chat", {"message": "oi"})[0], 200)
        self.assertEqual(len(post.call_args.kwargs["json"]["messages"]), 2)

    @patch("src.api.main.requests.post")
    def test_errors_have_useful_status_before_stream_headers(self, post):
        cases = [(main.requests.Timeout("private"), 504),
                 (main.requests.ConnectionError("private"), 503),
                 (main.requests.HTTPError(response=MagicMock(status_code=404)), 404),
                 (main.requests.HTTPError(response=MagicMock(status_code=500)), 502)]
        for error, expected in cases:
            for endpoint in ("/chat", "/chat/stream"):
                with self.subTest(error=type(error).__name__, endpoint=endpoint):
                    post.side_effect = error
                    status, body, _ = request(endpoint, {"message": "oi"})
                    self.assertEqual(status, expected)
                    self.assertNotIn(b"private", body)

    @patch("src.api.main.requests.post")
    def test_bad_upstream_data_is_not_a_successful_reply(self, post):
        for data in (None, [], {}, {"error": "private"}, {"message": {"content": 1}}, {"message": {"content": ""}}):
            post.return_value = upstream(data)
            self.assertEqual(request("/chat", {"message": "oi"})[0], 502)

    @patch("src.api.main.requests.post")
    def test_stream_tokens_and_completion(self, post):
        response = upstream(lines=[
            b"", json.dumps({"message": {"content": "Olá "}}).encode(),
            json.dumps({"message": {"content": "Isaac"}, "done": True}).encode(),
        ])
        post.return_value = response
        status, body, headers = request("/chat/stream", {"message": "oi"})
        self.assertEqual(status, 200)
        self.assertEqual(body.decode(), "Olá Isaac")
        self.assertEqual(headers[b"x-accel-buffering"], b"no")
        response.iter_lines.assert_called_once_with(chunk_size=1)
        response.__exit__.assert_called_once()

    def test_broken_streams_raise_and_close_response(self):
        for lines in ([b"invalid"], [b"[]"], [b'{"error":"private"}'],
                      [b'{"message":{"content":"partial"}}']):
            with self.subTest(lines=lines):
                response = upstream(lines=lines)
                with self.assertRaisesRegex(RuntimeError, "interrompida"):
                    list(main.stream_ollama_generator(response))
                response.__exit__.assert_called_once()

    @patch("src.api.main.requests.get")
    def test_health_reports_ollama_separately(self, get):
        for code, expected in ((200, "online"), (500, "degraded")):
            response = upstream()
            response.status_code = code
            get.return_value = response
            status, body, _ = request("/health")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["ollama_status"], expected)
        get.side_effect = main.requests.ConnectionError("offline")
        self.assertEqual(json.loads(request("/health")[1])["ollama_status"], "offline")

    @patch("src.api.main.requests.get")
    def test_models_validate_upstream(self, get):
        get.return_value = upstream({"models": [{"name": main.DEFAULT_MODEL}]})
        self.assertEqual(request("/models")[0], 200)
        get.return_value = upstream({"models": "invalid"})
        self.assertEqual(request("/models")[0], 502)


if __name__ == "__main__":
    unittest.main()
