from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.utils.config import Settings, load_settings


def test_environment_secrets_and_mode_override(monkeypatch, tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("mode: PAPER\nleverage: 5\npaper_initial_balance: '1234'\n")
    monkeypatch.setenv("BOT_CONFIG", str(path))
    monkeypatch.setenv("WEBHOOK_SECRET", "w" * 32)
    monkeypatch.setenv("ADMIN_TOKEN", "a" * 32)
    monkeypatch.setenv("TRADING_ENABLED", "false")
    settings = load_settings()
    assert settings.paper_initial_balance == Decimal(1234)
    assert not settings.trading_enabled
    assert "w" * 32 not in repr(settings)
    assert "a" * 32 not in repr(settings)


def test_yaml_secrets_forbidden(monkeypatch, tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("webhook_secret: should-not-be-here\n")
    monkeypatch.setenv("BOT_CONFIG", str(path))
    with pytest.raises(ValueError, match="environment"):
        load_settings()


@pytest.mark.parametrize(
    "bad",
    [
        {"leverage": 0},
        {"risk_per_trade": "0"},
        {"risk_per_trade": "0.5"},
        {"quantity_step": "0"},
        {"max_open_positions": 2},
        {"paper_fee_rate": "NaN"},
        {"max_notional": "Infinity"},
        {"mode": "UNKNOWN"},
    ],
)
def test_invalid_configuration(bad):
    with pytest.raises(ValidationError):
        Settings.model_validate(bad)


def test_bootstrap_idempotent_no_tokens_printed(monkeypatch, tmp_path, capsys):
    from scripts.bootstrap import main

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.example").write_text("WEBHOOK_SECRET=\nADMIN_TOKEN=\nBOT_MODE=PAPER\n")
    main()
    content = (tmp_path / ".env").read_text()
    tokens = [line.split("=", 1)[1] for line in content.splitlines()[:2]]
    assert all(len(token) >= 32 for token in tokens)
    assert tokens[0] != tokens[1]
    main()
    assert (tmp_path / ".env").read_text() == content
    output = capsys.readouterr().out
    assert all(token not in output for token in tokens)
