from ghostchef_ai import config


def test_fake_mode_values(monkeypatch):
    for v in ("1", "true", "YES", "True"):
        monkeypatch.setenv("GHOSTCHEF_AI_FAKE", v)
        assert config.is_fake()
    for v in ("0", "", "no"):
        monkeypatch.setenv("GHOSTCHEF_AI_FAKE", v)
        assert not config.is_fake()


def test_fake_mode_model_ids_are_fake():
    assert config.model_ids() == {"video": "fake", "check": "fake", "watch": "fake", "live": "fake"}


def test_model_env_overrides(monkeypatch):
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE", "0")
    monkeypatch.setenv("GHOSTCHEF_MODEL_WATCH", "my-watch-model")
    ids = config.model_ids()
    assert set(ids) == {"video", "check", "watch", "live"}
    assert ids["watch"] == "my-watch-model"
    assert all(ids.values())


def test_fixture_dir_default_and_override(monkeypatch, tmp_path):
    assert (config.fixture_dir() / "sushi_recipe.json").is_file()
    monkeypatch.setenv("GHOSTCHEF_FIXTURE_DIR", str(tmp_path))
    assert config.fixture_dir() == tmp_path.resolve()


def test_import_does_not_load_dotenv(tmp_path):
    """A program that imports the package must not pick up ai/.env (code review)."""
    import subprocess
    import sys
    from pathlib import Path

    src = str(Path(config.__file__).resolve().parents[1])
    code = ("import os, ghostchef_ai; "
            "print(os.environ.get('GHOSTCHEF_AI_FAKE', '<unset>'), "
            "'set' if os.environ.get('GEMINI_API_KEY') else '<unset>')")
    env = {k: v for k, v in __import__("os").environ.items()
           if k not in ("GHOSTCHEF_AI_FAKE", "GEMINI_API_KEY", "OPENAI_API_KEY")}
    env["PYTHONPATH"] = src
    r = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["<unset>", "<unset>"]


def test_load_env_reads_ai_dotenv_only_when_called():
    assert config.AI_DIR.name == "ai" and callable(config.load_env)
