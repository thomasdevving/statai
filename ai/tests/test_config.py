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
