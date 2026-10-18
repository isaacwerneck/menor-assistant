import unittest
from unittest.mock import Mock, patch

from src.api import main


class ApiTests(unittest.TestCase):
    def test_ui_available(self):
        response = main.serve_chat_ui()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"messagesContainer", response.body)

    @patch("src.api.main.requests.get")
    def test_health_online(self, get):
        get.return_value = Mock(status_code=200)
        self.assertEqual(main.health_check()["ollama_status"], "online")

    @patch("src.api.main.requests.get")
    def test_health_offline(self, get):
        get.side_effect = main.requests.ConnectionError("offline")
        self.assertEqual(main.health_check()["ollama_status"], "offline")


if __name__ == "__main__":
    unittest.main()
