"""Tests for per-key sliding window rate limiter."""
from __future__ import annotations

import time

from StructIQ.api.rate_limiter import RateLimiter


def test_allows_requests_within_quota():
    rl = RateLimiter(max_requests=3, window_seconds=60)
    for _ in range(3):
        assert rl.is_allowed("key1") is True


def test_blocks_when_quota_exceeded():
    rl = RateLimiter(max_requests=2, window_seconds=60)
    rl.is_allowed("key1")
    rl.is_allowed("key1")
    assert rl.is_allowed("key1") is False


def test_different_keys_have_independent_quotas():
    rl = RateLimiter(max_requests=1, window_seconds=60)
    assert rl.is_allowed("key1") is True
    assert rl.is_allowed("key2") is True
    assert rl.is_allowed("key1") is False


def test_window_expires_and_allows_again():
    rl = RateLimiter(max_requests=1, window_seconds=0.1)
    assert rl.is_allowed("key1") is True
    assert rl.is_allowed("key1") is False
    time.sleep(0.15)
    assert rl.is_allowed("key1") is True


def test_reset_clears_quota():
    rl = RateLimiter(max_requests=1, window_seconds=60)
    rl.is_allowed("key1")
    rl.reset("key1")
    assert rl.is_allowed("key1") is True
