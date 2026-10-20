import os
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from src.api.remote_lab import LabRequest
from src.api.remote_lab_api import _authorize, remote_compare


class RemoteLabApiTests(unittest.TestCase):
    def setUp(self):
        self.body = LabRequest(mode="direct", message="Ola")
        self.token = "a" * 48

    def request(self, authorization="", origin=None):
        headers = {"authorization": authorization}
        if origin:
            headers["origin"] = origin
        return Mock(headers=headers)

    def test_disabled_without_token(self):
        with patch.dict(os.environ, {"MENOR_LAB_API_TOKEN": ""}):
            with self.assertRaises(HTTPException) as caught:
                _authorize(self.request())
            self.assertEqual(caught.exception.status_code, 401)

    def test_wrong_token(self):
        with patch.dict(os.environ, {"MENOR_LAB_API_TOKEN": self.token,
                                     "MENOR_LAB_REMOTE_ENABLED": "1"}):
            with self.assertRaises(HTTPException) as caught:
                _authorize(self.request("Bearer wrong"))
            self.assertEqual(caught.exception.status_code, 401)

    def test_feature_off(self):
        with patch.dict(os.environ, {"MENOR_LAB_API_TOKEN": self.token,
                                     "MENOR_LAB_REMOTE_ENABLED": "0"}):
            with self.assertRaises(HTTPException) as caught:
                _authorize(self.request("Bearer " + self.token))
            self.assertEqual(caught.exception.status_code, 503)

    def test_origin_denied(self):
        with patch.dict(os.environ, {"MENOR_LAB_API_TOKEN": self.token,
                                     "MENOR_LAB_REMOTE_ENABLED": "1"}):
            with self.assertRaises(HTTPException) as caught:
                _authorize(self.request("Bearer " + self.token, "https://evil.example"))
            self.assertEqual(caught.exception.status_code, 403)

    def test_authorized_inference(self):
        with patch.dict(os.environ, {"MENOR_LAB_API_TOKEN": self.token,
                                     "MENOR_LAB_REMOTE_ENABLED": "1"}), \
             patch("src.api.remote_lab._limit"), \
             patch("src.api.remote_lab._direct", return_value={
                 "status": "answered", "reply": "Oi", "model": "qwen", "move": None}):
            result = remote_compare(self.body, self.request("Bearer " + self.token))
            self.assertEqual(result["reply"], "Oi")
            self.assertEqual(result["tools_executed"], 0)


if __name__ == "__main__":
    unittest.main()
