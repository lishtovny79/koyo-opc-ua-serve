# Troubleshooting

[Русская версия](../troubleshooting.md)

| Symptom | Check |
| --- | --- |
| PLC values do not update | PLC IP, UDP port 28784, routing, firewall, and Ethernet-interface configuration. |
| OPC UA client cannot connect | TCP port 4840, host firewall, and configured endpoint. |
| Tags are absent | CSV columns, supported address notation, and server startup log. |
| A new tag does not appear | `Objects/ServerStatus/LastTagOperation` for validation errors or the add confirmation. |
| A tag backup is needed | Call `Objects/TagManagement/BackupTags`; the file is created in `plc.backup_directory`. |
| Writes do not work | `Client Access`, data type, PLC mode, and server logs. |
| `AddTag`/`BackupTags` use old code | Rebuild the Docker image without cache as described in [installation](installation.md). |

When PLC communication is lost, the server retains the last values in cache.
`Objects/ServerStatus/PlcOnline` shows whether the latest PLC exchange succeeded.
Treat cached values as stale while it is `false`.

## Rejected UDP responses

`Rejected PLC UDP response: ...` identifies an unexpected sender, transaction
handle, HAP header, declared length, CRC, response phase, status, or read block
size. Invalid packets are ignored within the receive timeout. The first rejection
and every hundredth rejection of each kind are logged to limit log volume.
Each read uses a new two-byte handle. After a failed exchange the UDP socket is
replaced so that a delayed response to the old source port cannot satisfy the
next request. A complete polling cycle must succeed before its cache is committed.
If any block fails, the previous cache is retained, publication is skipped, and
`PlcOnline` becomes `false`; consumers must not treat cached values as current.

Check competing PLC clients, network delays and the configured `read_block_words`
when read lengths differ. Do not increase the block size past the PLC's actual
response limit. Strict validation does not prove which cause produced an older
incorrect value.

## Invalid BCD values

`PLC decode failed: tag=... word=... raw=... next_word=...` identifies the tag,
decimal word address, and raw words before the decode exception is propagated.
For example, V56 is octal and maps to decimal word 46. BCD nibbles must be 0–9;
an A–F nibble cannot be decoded as BCD. Check the tag's address and data type
against the PLC program. This diagnostic does not change the configured type or
substitute a made-up value, and a genuine decode error still stops the server.
