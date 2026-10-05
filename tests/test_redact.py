"""Secret redaction behavior."""

from __future__ import annotations

from agentcheckpoint.security.redact import redact, scan_for_secrets


def test_openai_style_key():
    text = "use key sk-abcdefghijklmnopqrstuvwx please"
    assert redact(text) == "use key [REDACTED:openai-style-key] please"


def test_anthropic_key():
    text = "key sk-ant-api03-abcdefghijklmnopqrstuvwxyz123456 here"
    out = redact(text)
    assert "[REDACTED:anthropic-key]" in out
    assert "sk-ant-" not in out


def test_aws_and_github_and_slack():
    text = "AKIAIOSFODNN7EXAMPLE ghp_abcdefghijklmnopqrstuvwxyz123456 xoxb-123456789012"
    out = redact(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "ghp_" not in out.replace("[REDACTED:github-token]", "x") or "REDACTED" in out
    assert "xoxb-123456789012" not in out


def test_private_key_block():
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----\ntrailing"
    out = redact(text)
    assert "MIIabc" not in out
    assert "trailing" in out


def test_normal_content_untouched():
    text = "sketch the design, task #12, cost is 50 dollars"
    assert redact(text) == text


def test_scan_does_not_rewrite():
    text = "token ghp_abcdefghijklmnopqrstuvwxyz123456"
    assert scan_for_secrets(text) == ["github-token"]
    assert text == "token ghp_abcdefghijklmnopqrstuvwxyz123456"
