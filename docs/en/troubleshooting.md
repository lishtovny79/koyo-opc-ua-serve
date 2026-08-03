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
