# Kepware tag export

[Русская версия](../tag-export.md)

Export tags as CSV using the standard Kepware columns. Required fields are:

- `Tag Name`
- `Address`
- `Data Type`
- `Client Access`

Supported types are `Boolean`, `Word`, `BCD`, `LBCD`, and `Float`.

A dotted tag name creates OPC UA folders. For example,
`Mixer.Speed.Setpoint` becomes:

```text
Objects/Mixer/Speed/Setpoint
```

Do not commit production CSV files to Git when names or addresses disclose
equipment details. Use the small file in `examples/` for demonstrations and CI.

CSV import is optional. With `plc.tags_csv = ""`, the server loads tags already
stored in SQLite, or starts with an empty catalog on first launch.
