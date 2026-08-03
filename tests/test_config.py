from pathlib import Path

from koyo_opc_ua_server.config import load_config


def test_resolves_tag_path_relative_to_config_file(tmp_path):
    config_file = tmp_path / "config.toml"
    config_file.write_text("[plc]\nhost = '10.0.0.1'\ntags_csv = '../tags.csv'\n", encoding="utf-8")
    config = load_config(config_file)
    assert config.plc_host == "10.0.0.1"
    assert config.tags_csv == (tmp_path / "../tags.csv").resolve()
