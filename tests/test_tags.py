from pathlib import Path

import pytest

from koyo_opc_ua_server.tags import TagConfigurationError, load_tags, map_address


def test_maps_kepware_addresses():
    assert map_address("V3007") == (int("3007", 8), None)
    assert map_address("C560") == (int("40600", 8) + int("560", 8) // 16, int("560", 8) % 16)


def test_loads_example_tags():
    tags = load_tags(Path("examples/tags-kepware.csv"))
    assert [tag.word_count for tag in tags] == [1, 1, 2]
    assert tags[2].decode({tags[2].word: 0, tags[2].word + 1: 0}) == 0.0


def test_rejects_unknown_address(tmp_path):
    csv = tmp_path / "tags.csv"
    csv.write_text("Tag Name,Address,Data Type,Client Access\nBad,Z1,Word,R/W\n", encoding="utf-8")
    with pytest.raises(TagConfigurationError, match="unsupported address"):
        load_tags(csv)
