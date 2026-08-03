from koyo_opc_ua_server.tag_store import TagStore
from koyo_opc_ua_server.tags import create_tag


def test_store_persists_tags_and_creates_backup(tmp_path):
    store = TagStore(tmp_path / "data" / "tags.db")
    try:
        store.upsert(create_tag("Pump.Run", "C0", "Boolean", "R/W"), "opcua")
        assert store.load_all()[0].name == "Pump.Run"
        assert store.remove("Pump.Run") is True
        assert store.load_all() == []
        store.upsert(create_tag("Pump.Run", "C0", "Boolean", "R/W"), "opcua")
        backup = store.backup(tmp_path / "backups")
        assert backup.is_file()
    finally:
        store.close()
