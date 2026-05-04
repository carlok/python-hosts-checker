"""Tests for lambda_handler without real network."""

from unittest.mock import patch

import checker


def test_lambda_handler_dispatches_lists():
    event = {
        "authenticated": [
            {
                "domain": "auth.example.com",
                "port": 443,
                "protocol": "https",
                "username": "u",
                "password": "p",
            }
        ],
        "unauthenticated": [
            {
                "domain": "pub.example.com",
                "port": 443,
                "protocol": "https",
            }
        ],
    }
    with patch.object(checker, "vhost_https_get_authenticated") as auth_fn:
        with patch.object(checker, "vhost_https_check_unauthenticated") as pub_fn:
            result = checker.lambda_handler(event, {})

    assert result == {"statusCode": 200, "body": "ok"}
    assert auth_fn.call_count == 1
    assert pub_fn.call_count == 1


def test_lambda_handler_empty_lists():
    with patch.object(checker, "vhost_https_get_authenticated") as auth_fn:
        with patch.object(checker, "vhost_https_check_unauthenticated") as pub_fn:
            result = checker.lambda_handler({}, {})

    assert result == {"statusCode": 200, "body": "ok"}
    assert auth_fn.call_count == 0
    assert pub_fn.call_count == 0
