import json

import pytest

from eclectolog.config import ConfigError, apply_directives, load_config, parse_directives, parse_era
from eclectolog.references import DESCRIPTIONS


def load(tmp_path, env=None, config_yaml=None, interests_yaml=None):
    if config_yaml is not None:
        (tmp_path / "config.yaml").write_text(config_yaml)
    if interests_yaml is not None:
        (tmp_path / "interests.yaml").write_text(interests_yaml)
    return load_config(environ=env or {}, base_dir=tmp_path)


def test_defaults_load(tmp_path):
    cfg = load(tmp_path)
    assert cfg["playlist"]["size"] == 40
    assert cfg["interests"]["genres"] == {}


def test_repo_config_matches_defaults_shape():
    # The shipped config.yaml and interests.yaml must parse and validate.
    cfg = load_config(environ={})
    assert cfg["mix"]["genre_neighbors"] == 0.35


def test_precedence_file_then_vars_json_then_env(tmp_path):
    env = {
        "ECLECTOLOG_VARS_JSON": json.dumps({"ECLECTOLOG_PLAYLIST_SIZE": "25", "ECLECTOLOG_PLAYLIST_NAME": "From Vars", "OTHER": "x"}),
        "ECLECTOLOG_PLAYLIST_SIZE": "30",
        "ECLECTOLOG_PLAYLIST_MODE": "",  # blank = unset (scheduled runs pass blank inputs)
    }
    cfg = load(tmp_path, env, config_yaml="playlist:\n  size: 10\n  name: From File\n  mode: new\n")
    assert cfg["playlist"]["size"] == 30
    assert cfg["playlist"]["name"] == "From Vars"
    assert cfg["playlist"]["mode"] == "new"


def test_config_yaml_blob_and_mix(tmp_path):
    env = {"ECLECTOLOG_CONFIG_YAML": "diversity:\n  max_per_genre: 2\n", "ECLECTOLOG_MIX": "wildcard=0.5, compass=0"}
    cfg = load(tmp_path, env)
    assert cfg["diversity"]["max_per_genre"] == 2
    assert cfg["mix"]["wildcard"] == 0.5 and cfg["mix"]["compass"] == 0
    assert cfg["mix"]["deep_cuts"] == 0.25  # untouched keys survive


def test_interests_file_and_env_append(tmp_path):
    env = {"ECLECTOLOG_EXTRA_GENRES": "Dub, Krautrock", "ECLECTOLOG_AVOID_GENRES": "christmas"}
    cfg = load(tmp_path, env, interests_yaml="genres:\n  bossa nova: 1.5\nartists: [Khruangbin]\neras: [1970s]\n")
    assert cfg["interests"]["genres"] == {"bossa nova": 1.5, "dub": 1.0, "krautrock": 1.0}
    assert cfg["interests"]["artists"] == ["Khruangbin"]
    assert cfg["interests"]["avoid"]["genres"] == ["christmas"]


@pytest.mark.parametrize("env", [
    {"ECLECTOLOG_PLAYLIST_MODE": "sometimes"},
    {"ECLECTOLOG_PLAYLIST_SIZE": "zero"},
    {"ECLECTOLOG_MIX": "bogus=1"},
    {"ECLECTOLOG_MIX": "deep_cuts=0,genre_neighbors=0,wildcard=0,compass=0"},
    {"ECLECTOLOG_TEMPERATURE": "0"},
    {"ECLECTOLOG_ERAS": "the seventies"},
])
def test_invalid_values_raise(tmp_path, env):
    with pytest.raises(ConfigError):
        load(tmp_path, env)


def test_parse_era():
    assert parse_era("1970s") == "1970-1979"
    assert parse_era("1994") == "1994"
    assert parse_era("1965 - 1979") == "1965-1979"


def test_directives_template_is_inert():
    assert parse_directives(DESCRIPTIONS["compass"]) == {}


def test_directives_parse_from_prose():
    d = parse_directives("Steer it → more: Dub, krautrock; less: country &amp; western; size: 30; explore: 0.5; nonsense: 1")
    assert d == {"more": "Dub, krautrock", "less": "country & western", "size": "30", "genre_neighbors": "0.5"}


def test_apply_directives(tmp_path):
    cfg = load(tmp_path)
    notes = apply_directives(cfg, {"more": "Dub", "less": "country", "size": "30", "era": "1970s", "wildcard": "oops"})
    assert cfg["interests"]["genres"]["dub"] == 2.0
    assert "country" in cfg["interests"]["avoid"]["genres"]
    assert cfg["playlist"]["size"] == 30
    assert cfg["interests"]["eras"] == ["1970-1979"]
    assert any(n.startswith("ignored wildcard") for n in notes)


def test_apply_directives_reverts_invalid_combo(tmp_path):
    cfg = load(tmp_path)
    notes = apply_directives(cfg, {"deep_cuts": "0", "genre_neighbors": "0", "wildcard": "0", "compass": "0", "size": "5"})
    assert cfg["playlist"]["size"] == 40
    assert notes[0].startswith("ignored all directives")
