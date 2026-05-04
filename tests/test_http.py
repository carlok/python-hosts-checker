"""HTTP path tests with mocked urllib3 and cert checks."""

from unittest.mock import patch

import checker


class _FakeResponse:
    def __init__(self, status, headers):
        self.status = status
        self.headers = headers or {}


def test_perform_request_200_https_triggers_cert_check():
    vhost = {
        "domain": "example.com",
        "port": 443,
        "protocol": "https",
    }
    url = "https://example.com"
    with patch.object(checker.http, "request") as req:
        req.return_value = _FakeResponse(200, {})
        with patch.object(checker, "certificate_remote_expire_check") as cert:
            checker.perform_request(vhost, "HEAD", url)
    req.assert_called_once()
    cert.assert_called_once_with(vhost)


def test_perform_request_bad_status_alerts():
    vhost = {
        "domain": "example.com",
        "port": 443,
        "protocol": "http",
    }
    url = "http://example.com"
    with patch.object(checker.http, "request") as req:
        req.return_value = _FakeResponse(500, {})
        with patch.object(checker, "_alert") as alert:
            with patch.object(checker, "certificate_remote_expire_check") as cert:
                checker.perform_request(vhost, "HEAD", url)
    alert.assert_called_once()
    cert.assert_not_called()


def test_perform_request_exception_alerts():
    vhost = {
        "domain": "example.com",
        "port": 443,
        "protocol": "https",
    }
    with patch.object(checker.http, "request", side_effect=OSError("boom")):
        with patch.object(checker, "_alert") as alert:
            checker.perform_request(vhost, "HEAD", "https://example.com")
    alert.assert_called_once()
