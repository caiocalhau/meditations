import json
from datetime import datetime, timezone

from meditations.cli import main
from meditations.machine_config import configure, load_machine_config


def test_english_preference_preserves_legacy_settings_and_survives_reconfigure(
    tmp_path, capsys
):
    vault = tmp_path / "vault"
    vault.mkdir()
    settings = tmp_path / "config.json"
    legacy = {
        "schema_version": 2,
        "workspace": str(vault),
        "timezone": "America/Sao_Paulo",
        "language": "pt-BR",
    }
    settings.write_text(json.dumps(legacy))
    original = settings.read_bytes()
    assert load_machine_config(settings).english_feedback is False
    assert settings.read_bytes() == original
    assert (
        main(
            ["config", "set", "--english-feedback", "on"],
            machine_config_path=settings,
        )
        == 0
    )
    saved = json.loads(settings.read_text())
    assert saved == {**legacy, "english_feedback": True}
    capsys.readouterr()
    assert (
        main(
            ["config", "show"],
            machine_config_path=settings,
            now=datetime(2026, 10, 15, tzinfo=timezone.utc),
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["english_feedback"] is True
    configure(vault, timezone="UTC", language="en", path=settings)
    assert load_machine_config(settings).english_feedback is True
    assert (
        main(
            ["config", "set", "--english-feedback", "off"],
            machine_config_path=settings,
        )
        == 0
    )
    assert load_machine_config(settings).english_feedback is False
