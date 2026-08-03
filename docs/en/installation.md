# Installation and operation

[Русская версия](../installation.md)

## Windows

Install Python 3.11+, create a virtual environment, and run `pip install .`.
Start the server with:

```powershell
koyo-opc-ua-server --config config/config.toml
```

For unattended operation, register this command as a Windows service using the
organization's approved service manager. Use a dedicated account that has access
only to the configuration and tag CSV export.

## Linux

Create `/opt/koyo-opc-ua-server`, install the package in a virtual environment,
copy `config.example.toml` to `config.toml`, and configure it. The supplied
[systemd unit](../../systemd/koyo-opc-ua-server.service) assumes this path.

## Docker

Build the image and pass configuration as an external file. Do not embed
production CSV files or configuration in the Docker image:

```bash
docker build -t koyo-opc-ua-server .
docker run --rm --network host \
  -v /srv/koyo-opc/config.toml:/app/config/config.toml:ro \
  -v /srv/koyo-opc/tags.csv:/app/data/tags.csv:ro \
  koyo-opc-ua-server
```

With Docker Desktop, publish TCP port 4840 and ensure the container can reach
the PLC over UDP.

## Docker Compose

Copy `config/config.example.toml` to `config/config.toml`, configure the
controller IP, then run:

```bash
docker compose up -d --build
```

`compose.yaml` mounts `data/` for the SQLite catalog and `backups/` for online
backups, so both survive a container rebuild or restart.

After modifying source code, rebuild without cache:

```bash
docker compose down --remove-orphans
docker compose build --no-cache
docker compose up -d --force-recreate
```
