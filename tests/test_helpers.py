"""Unit tests for pure helpers and URL building."""

import datetime

import pytest

import checker


def test_days_between():
    a = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    b = datetime.datetime(2024, 1, 11, tzinfo=datetime.timezone.utc)
    assert checker.days_between(a, b) == 10


def test_string_to_datetime_gmt():
    dt = checker.string_to_datetime("Aug 15 09:37:47 2022 GMT")
    assert dt.tzinfo == datetime.timezone.utc
    assert dt.year == 2022 and dt.month == 8 and dt.day == 15


@pytest.mark.parametrize(
    "vhost,expected",
    [
        (
            {"protocol": "https", "domain": "a.com", "port": 443},
            "https://a.com",
        ),
        (
            {"protocol": "https", "domain": "a.com", "port": 8443},
            "https://a.com:8443",
        ),
        (
            {"protocol": "http", "domain": "a.com", "port": 443},
            "http://a.com:443",
        ),
        (
            {"protocol": "https", "domain": "a.com", "port": 80},
            "https://a.com:80",
        ),
        (
            {
                "protocol": "https",
                "domain": "a.com",
                "port": 443,
                "suffix": "/health",
            },
            "https://a.com/health",
        ),
        (
            {
                "protocol": "http",
                "domain": "a.com",
                "port": 8080,
                "suffix": "api/v1",
            },
            "http://a.com:8080/api/v1",
        ),
    ],
)
def test_build_request_url(vhost, expected):
    assert checker.build_request_url(vhost) == expected
