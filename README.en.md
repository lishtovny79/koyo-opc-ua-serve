# Koyo OPC UA Server

**Language:** [Русский](README.md) | English

OPC UA server for Koyo / DirectLOGIC PLCs. The current transport implementation
targets DL205. The server imports tags from Kepware CSV exports, creates an OPC
UA tree, reads PLC values, and accepts writes from OPC UA clients.

Supported data types: `Boolean`, `Word`, `BCD`, `LBCD`, and `Float`.

> This software controls industrial equipment. Test each installation on a
> non-production controller before connecting it to a live process.

## Features

- Imports hierarchical tag names from Kepware CSV exports.
- Uses grouped PLC reads to reduce network traffic.
- Supports writes, including atomic two-word Float writes.
- Starts with an empty catalog or imports an optional CSV file.
- Persists tags in SQLite; tags created by a client survive restarts.
- Creates an online SQLite backup from an OPC UA client without stopping the server.
- Runs as a Python package, Docker container, or system service.

## Quick start

Python 3.11 or newer is required.

```bash
git clone <your-gitlab-url>/koyo-opc-ua-server.git
cd koyo-opc-ua-server
python -m venv .venv
```

Activate the virtual environment, install the package, and create a working
configuration:

```bash
pip install .
copy config\config.example.toml config\config.toml
koyo-opc-ua-server --config config/config.toml
```

On Linux/macOS, use `cp` instead of `copy`. Set the controller IP in
`config/config.toml` before starting the server.

### Docker Compose

Copy `config/config.example.toml` to `config/config.toml`, set `plc.host`, then run:

```bash
docker compose up -d --build
```

[compose.yaml](compose.yaml) persists the SQLite catalog in `data/` and online
backups in `backups/`. Stop the container with `docker compose down`.

The OPC UA endpoint is configured in `[opcua]`, for example:

```text
opc.tcp://<server-IP>:4840/freeopcua/server/
```

The server intentionally runs without OPC UA certificates. Restrict access to
port 4840 to a trusted industrial network or firewall.

## Configuration

See [config/config.example.toml](config/config.example.toml). Copy it to
`config/config.toml`; that working file is excluded from Git.

- `plc.host` — controller or Ethernet-interface IP address.
- `plc.tags_csv` — optional path to a Kepware CSV export. An empty value starts
  the server without importing tags.
- `plc.tags_database` — SQLite tag catalog.
- `plc.backup_directory` — directory for online SQLite backups.
- `polling.interval_seconds` — pause after every complete read cycle.
- `polling.write_subscription_interval_ms` — client-write handling delay.

Further documentation: [installation](docs/en/installation.md),
[tag export](docs/en/tag-export.md), and [troubleshooting](docs/en/troubleshooting.md).

## Managing tags through an OPC UA client

`Objects/TagManagement` provides these methods:

- `AddTag(Name, Address, DataType, ClientAccess)` adds a tag to memory and SQLite.
  Valid `DataType` values are `Boolean`, `Word`, `BCD`, `LBCD`, and `Float`;
  `ClientAccess` is normally `R/W` or `R`.
- `RemoveTag(Name)` removes a tag from SQLite, the PLC read plan, and the OPC UA
  address space. Empty folders remain in the tree.
- `BackupTags()` creates a timestamped, consistent SQLite backup.

Methods immediately return `Queued`. Check
`Objects/ServerStatus/LastTagOperation` for the final result. The database is
not used in the PLC polling loop, so tag storage does not slow normal reads or writes.

## Support the project

If this project helps your work, consider making a voluntary donation. Donations
support new controller integrations and better documentation.

<a href="https://finance.ozon.ru/apps/sbp/ozonbankpay/019fc906-85e1-7e75-9b85-4807314b4aab">
  <img src="docs/donate-qr.jpg" width="220" alt="QR code to support the project via SBP">
</a>

**[Open the SBP donation page](https://finance.ozon.ru/apps/sbp/ozonbankpay/019fc906-85e1-7e75-9b85-4807314b4aab)**

Scan the QR code in a banking app or open the link from a mobile device. Thank
you for supporting the project.

## Feedback and releases

Report reproducible issues through GitLab Issues. Include the server version,
controller/interface model, sanitized tag line, logs, and network traffic only
when it contains no production addresses or credentials.

Versions follow `MAJOR.MINOR.PATCH`; user-visible changes are recorded in
[CHANGELOG.md](CHANGELOG.md).

## License

The project is prepared under the [MIT License](LICENSE). Replace the copyright
holder before the first public release if necessary.
