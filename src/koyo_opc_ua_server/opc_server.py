"""OPC UA tree, PLC polling, and client write handling."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from asyncua import Server, ua
from asyncua.common.methods import uamethod

from .config import ServerConfig
from .plc import READ_TRIGGER, KoyoPLC
from .tag_store import TagStore
from .tags import TagConfigurationError, TagDefinition, create_tag


logger = logging.getLogger(__name__)


@dataclass
class TagBinding:
    definition: TagDefinition
    node: object
    ua_type: ua.VariantType
    last_value: bool | int | float


class PLCWriteHandler:
    def __init__(self, manager: "OpcServerManager") -> None:
        self.manager = manager

    async def datachange_notification(self, node, value, _data) -> None:
        binding = self.manager.bindings.get(str(node))
        if binding is None or not binding.definition.writable or binding.last_value == value:
            return
        await self.manager.write_tag(binding, value)


class OpcServerManager:
    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self.plc = KoyoPLC(config.plc_host, config.plc_port, config.receive_timeout)
        self.server = Server()
        self.namespace_index = 0
        self.tags: list[TagDefinition] = []
        self.tag_store = TagStore(config.tags_database)
        self.bindings: dict[str, TagBinding] = {}
        self.word_cache: dict[int, int] = {}
        self.read_requests: list[tuple[int, bytes]] = []
        self.folders: dict[tuple[str, str], object] = {}
        self.write_lock = asyncio.Lock()
        self.tag_lock = asyncio.Lock()
        self.subscription = None
        self.online_node = None
        self._online_value: bool | None = None
        self.operation_node = None
        self._last_operation = "Ready"
        self.loop: asyncio.AbstractEventLoop | None = None

    async def initialize(self) -> None:
        # asyncua executes synchronous OPC UA Method callbacks in a worker
        # thread. Keep the server event loop so those callbacks can safely
        # schedule coroutine work back on the main loop.
        self.loop = asyncio.get_running_loop()
        if self.config.tags_csv is not None:
            imported = self.tag_store.import_csv(self.config.tags_csv)
            logger.info("Imported %d tags from %s", imported, self.config.tags_csv)
        self.tags = self.tag_store.load_all()
        self.build_read_requests()
        await self.sync_plc()

        await self.server.init()
        self.server.set_endpoint(self.config.endpoint)
        self.namespace_index = await self.server.register_namespace("http://koyo.opcua.server")
        await self.create_status_nodes()
        await self.create_management_methods()
        for tag in self.tags:
            await self.create_tag_node(tag)

        handler = PLCWriteHandler(self)
        self.subscription = await self.server.create_subscription(
            self.config.write_subscription_interval_ms, handler
        )
        if self.bindings:
            await self.subscription.subscribe_data_change([binding.node for binding in self.bindings.values()])
        logger.info("Server ready. Loaded %d tags and %d PLC read blocks.", len(self.tags), len(self.read_requests))

    async def create_status_nodes(self) -> None:
        folder = await self.server.nodes.objects.add_folder(self.namespace_index, "ServerStatus")
        self.online_node = await folder.add_variable(self.namespace_index, "PlcOnline", self.plc.is_online)
        self.operation_node = await folder.add_variable(self.namespace_index, "LastTagOperation", self._last_operation)
        await self.update_online_status()

    async def create_management_methods(self) -> None:
        management = await self.server.nodes.objects.add_object(self.namespace_index, "TagManagement")
        await management.add_method(
            ua.NodeId("AddTag", self.namespace_index),
            ua.QualifiedName("AddTag", self.namespace_index),
            self.add_tag_method,
            [ua.VariantType.String, ua.VariantType.String, ua.VariantType.String, ua.VariantType.String],
            [ua.VariantType.String],
        )
        await management.add_method(
            ua.NodeId("RemoveTag", self.namespace_index),
            ua.QualifiedName("RemoveTag", self.namespace_index),
            self.remove_tag_method,
            [ua.VariantType.String],
            [ua.VariantType.String],
        )
        await management.add_method(
            ua.NodeId("BackupTags", self.namespace_index),
            ua.QualifiedName("BackupTags", self.namespace_index),
            self.backup_tags_method,
            [],
            [ua.VariantType.String],
        )

    @uamethod
    def add_tag_method(self, _parent, name: str, address: str, data_type: str, client_access: str) -> str:
        self.schedule(self.add_tag(name, address, data_type, client_access))
        return "Queued; see Objects/ServerStatus/LastTagOperation"

    @uamethod
    def backup_tags_method(self, _parent) -> str:
        self.schedule(self.backup_tags())
        return "Queued; see Objects/ServerStatus/LastTagOperation"

    @uamethod
    def remove_tag_method(self, _parent, name: str) -> str:
        self.schedule(self.remove_tag(name))
        return "Queued; see Objects/ServerStatus/LastTagOperation"

    def schedule(self, coroutine) -> None:
        if self.loop is None or self.loop.is_closed():
            coroutine.close()
            raise RuntimeError("server event loop is not available")
        asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    async def create_tag_node(self, tag: TagDefinition) -> None:
        parent = self.server.nodes.objects
        parts = tag.name.split(".")
        for part in parts[:-1]:
            parent = await self.get_or_create_folder(parent, part)
        value = tag.decode(self.word_cache)
        ua_type = self.ua_type(tag)
        node = await parent.add_variable(self.namespace_index, parts[-1], value, varianttype=ua_type)
        if tag.writable:
            await node.set_writable()
        self.bindings[str(node)] = TagBinding(tag, node, ua_type, value)

    async def set_last_operation(self, message: str) -> None:
        self._last_operation = message
        if self.operation_node is not None:
            await self.operation_node.write_value(message)

    async def add_tag(self, name: str, address: str, data_type: str, client_access: str) -> None:
        """Persist a tag and expose it immediately without pausing the PLC scan."""
        try:
            tag = create_tag(name, address, data_type, client_access)
            async with self.tag_lock:
                if any(existing.name == tag.name for existing in self.tags):
                    raise TagConfigurationError(f"tag {tag.name!r} already exists")
                self.tag_store.upsert(tag, "opcua")
                self.tags.append(tag)
                self.build_read_requests()
                await self.create_tag_node(tag)
                if self.subscription is not None:
                    await self.subscription.subscribe_data_change(self.bindings[next(reversed(self.bindings))].node)
            await self.set_last_operation(f"Added tag {tag.name}")
            logger.info("OPC UA client added tag %s", tag.name)
        except Exception as exc:
            logger.warning("Cannot add OPC UA tag: %s", exc)
            await self.set_last_operation(f"AddTag failed: {exc}")

    async def backup_tags(self) -> None:
        try:
            path = await asyncio.to_thread(self.tag_store.backup, self.config.backup_directory)
            await self.set_last_operation(f"Backup created: {path.name}")
            logger.info("Tag database backup created: %s", path)
        except Exception as exc:
            logger.warning("Tag backup failed: %s", exc)
            await self.set_last_operation(f"BackupTags failed: {exc}")

    async def remove_tag(self, name: str) -> None:
        """Remove a dynamic tag from SQLite, polling, and the OPC UA address space."""
        name = name.strip()
        try:
            async with self.tag_lock:
                node_id, binding = next(
                    ((node_id, item) for node_id, item in self.bindings.items()
                     if item.definition.name == name),
                    (None, None),
                )
                if binding is None or node_id is None:
                    raise TagConfigurationError(f"tag {name!r} does not exist")
                await binding.node.delete(delete_references=True)
                if not self.tag_store.remove(name):
                    raise RuntimeError(f"tag {name!r} is missing from SQLite")
                del self.bindings[node_id]
                self.tags = [tag for tag in self.tags if tag.name != name]
                self.build_read_requests()
            await self.set_last_operation(f"Removed tag {name}")
            logger.info("OPC UA client removed tag %s", name)
        except Exception as exc:
            logger.warning("Cannot remove OPC UA tag: %s", exc)
            await self.set_last_operation(f"RemoveTag failed: {exc}")

    @staticmethod
    def ua_type(tag: TagDefinition) -> ua.VariantType:
        if tag.is_boolean:
            return ua.VariantType.Boolean
        if tag.is_float:
            return ua.VariantType.Float
        return ua.VariantType.Int32

    async def get_or_create_folder(self, parent, name: str):
        key = (str(parent.nodeid), name)
        if key not in self.folders:
            self.folders[key] = await parent.add_folder(self.namespace_index, name)
        return self.folders[key]

    def build_read_requests(self) -> None:
        words = sorted({word for tag in self.tags for word in range(tag.word, tag.word + tag.word_count)})
        self.read_requests = []
        index = 0
        while index < len(words):
            start = words[index]
            end_index = index
            while end_index + 1 < len(words) and words[end_index + 1] - start < self.config.read_block_words:
                end_index += 1
            length = words[end_index] - start + 1
            self.read_requests.append((start, self.plc.make_read_packet(start, length)))
            index = end_index + 1

    async def sync_plc(self) -> bool:
        # Publish one coherent cycle; a failed block must not partially replace the cache.
        candidate = self.word_cache.copy()
        for start, packet in tuple(self.read_requests):
            response = await self.plc.exchange(packet, 0x48, READ_TRIGGER)
            expected_bytes = packet[13]
            if not isinstance(response, bytes) or len(response) != expected_bytes:
                self.plc.is_online = False
                logger.warning("PLC read cycle discarded: start=%d expected_bytes=%d received_bytes=%s",
                               start, expected_bytes, len(response) if isinstance(response, bytes) else None)
                await self.update_online_status()
                return False
            for offset in range(0, len(response), 2):
                candidate[start + offset // 2] = response[offset] | response[offset + 1] << 8
        self.word_cache = candidate
        await self.update_online_status()
        return True

    async def update_online_status(self) -> None:
        if self.online_node is not None and self._online_value != self.plc.is_online:
            self._online_value = self.plc.is_online
            await self.online_node.write_value(self.plc.is_online)

    async def write_tag(self, binding: TagBinding, value: bool | int | float) -> bool:
        """Serialize client writes so bit read-modify-write operations cannot race."""
        async with self.write_lock:
            if binding.last_value == value:
                return True
            try:
                values = binding.definition.encode(value, self.word_cache)
            except (KeyError, ValueError, TypeError) as exc:
                logger.warning("Rejected write to %s: %s", binding.definition.name, exc)
                return False
            packet, sequence = self.plc.make_write_packet(binding.definition.word, values)
            if await self.plc.exchange(packet, sequence) is not True:
                logger.warning("PLC did not confirm write to %s", binding.definition.name)
                await self.update_online_status()
                return False
            for offset, word in enumerate(values):
                self.word_cache[binding.definition.word + offset] = word
            binding.last_value = value
            logger.info("PLC write: %s -> %s", binding.definition.name, value)
            await self.update_online_status()
            return True

    async def poll_loop(self) -> None:
        while True:
            # A write takes priority. It is protected by write_lock so two Boolean
            # updates cannot overwrite each other's bits in one PLC word.
            if not self.write_lock.locked():
                async with self.tag_lock:
                    if await self.sync_plc():
                        for binding in tuple(self.bindings.values()):
                            tag = binding.definition
                            try:
                                value = tag.decode(self.word_cache)
                            except ValueError:
                                logger.exception(
                                    "PLC decode failed: tag=%s word=%s raw=%r next_word=%r",
                                    tag.name,
                                    tag.word,
                                    self.word_cache.get(tag.word),
                                    self.word_cache.get(tag.word + 1),
                                )
                                raise
                            if binding.last_value != value:
                                binding.last_value = value
                                await binding.node.write_value(
                                    ua.DataValue(ua.Variant(value, binding.ua_type))
                                )
            await asyncio.sleep(self.config.poll_interval)

    async def run(self) -> None:
        await self.initialize()
        try:
            async with self.server:
                await self.poll_loop()
        finally:
            self.plc.close()
            self.tag_store.close()
