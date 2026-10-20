import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.api.main import app


class RemoteLabApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.url = "/lab/api/compare"
        self.body = {"mode": "direct", "message": "Ola"}
        self.token = "a" * 48

    def test_disabled_without_token(self):
        response = self.client.post(self.url, json=self.body)
        self.assertEqual(response.status_code, 401)

    def test_wrong_token(self):
        with patch.dict(os.environ, {"MENOR_LAB_API_TOKEN": self.token,
                                     "MENOR_LAB_REMOTE_ENABLED": "1"}):
            response = self.client.post(self.url, json=self.body,
                                        headers={"Authorization": "Bearer wrong"})
            self.assertEqual(response.status_code, 401)

    def test_feature_off(self):
        with patch.dict(os.environ, {"MENOR_LAB_API_TOKEN": self.token,
                                     "MENOR_LAB_REMOTE_ENABLED": "0"}):
            response = self.client.post(self.url, json=self.body,
                                        headers={"Authorization": "Bearer " + self.token})
            self.assertEqual(response.status_code, 503)

    def test_origin_denied(self):
        with patch.dict(os.environ, {"MENOR_LAB_API_TOKEN": self.token,
                                     "MENOR_LAB_REMOTE_ENABLED": "1"}):
            response = self.client.post(self.url, json=self.body,
                                        headers={"Authorization": "Bearer " + self.token,
                                                 "Origin": "https://evil.example"})
            self.assertEqual(response.status_code, 403)

    def test_authorized_inference(self):
        with patch.dict(os.environ, {"MENOR_LAB_API_TOKEN": self.token,
                                     "MENOR_LAB_REMOTE_ENABLED": "1"}), \
             patch("src.api.remote_lab._limit"), \
             patch("src.api.remote_lab._direct", return_value={
                 "status": "answered", "reply": "Oi", "model": "qwen", "move": None}):
            response = self.client.post(self.url, json=self.body,
                                        headers={"Authorization": "Bearer " + self.token})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["reply"], "Oi")
            self.assertEqual(response.json()["tools_executed"], 0)


if __name__ == "__main__":
    unittest.main()
