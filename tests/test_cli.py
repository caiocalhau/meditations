from meditations.cli import main


def test_init_command(tmp_path, capsys):
    assert main(["init", "--workspace", str(tmp_path), "--timezone", "UTC"]) == 0
    assert (tmp_path / "workspace.json").is_file()
    assert "Initialized" in capsys.readouterr().out


def test_init_error_returns_nonzero_without_traceback(tmp_path, capsys):
    assert main(["init", "--workspace", str(tmp_path), "--timezone", "invalid"]) == 1
    assert "Error:" in capsys.readouterr().err
    assert not (tmp_path / "workspace.json").exists()
