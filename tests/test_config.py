import json

import pytest

from alethe_tui.config import load_config


def test_dotenv_accepts_multiple_project_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text(
        "# Pastas que contêm projetos\n"
        "AGENT_WATCH_PROJECT_DIRS='[\"~/projects\", \"~/other projects\", \"~/projects\"]'\n"
        "UNRELATED_SECRET=ignored\n"
    )
    config = load_config(path=tmp_path / 'missing.toml', environ={'HOME': str(tmp_path)})
    assert config.project_dirs == [tmp_path / 'projects', tmp_path / 'other projects']


def test_environment_overrides_project_directories_in_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text('AGENT_WATCH_PROJECT_DIRS=invalid\n')
    config = load_config(path=tmp_path / 'missing.toml', environ={
        'HOME': str(tmp_path), 'AGENT_WATCH_PROJECT_DIRS': json.dumps([str(tmp_path / 'chosen')]),
    })
    assert config.project_dirs == [tmp_path / 'chosen']


@pytest.mark.parametrize('value', ['invalid', '{}', '[null]', '[""]'])
def test_invalid_project_directories_have_actionable_error(tmp_path, monkeypatch, value):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text('AGENT_WATCH_PROJECT_DIRS=' + value + '\n')
    with pytest.raises(ValueError, match='AGENT_WATCH_PROJECT_DIRS'):
        load_config(path=tmp_path / 'missing.toml', environ={'HOME': str(tmp_path)})


def test_missing_dotenv_keeps_all_projects(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_config(path=tmp_path / 'missing.toml', environ={'HOME': str(tmp_path)}).project_dirs == []
