# Changelog

## Unreleased

- Validate PLC UDP response origin, full transaction handle, HAP header, length,
  CRC, read phase and block size before decoding values.
- Generate a fresh handle for each read and replace the UDP socket after a timeout
  to isolate delayed responses.
- Commit the read cache only after a complete successful polling cycle.
- Log the tag, register and raw words before propagating BCD decode failures.

## 0.1.0 — 2026-08-03

- First product packaging of the Koyo OPC UA server.
- Modular configuration, CSV import, PLC protocol, and OPC UA server layers.
- CSV validation, configurable endpoint, access rights, PLC status tag, and
  serialized bit writes.
- Kepware CSV import, grouped reads, OPC UA tag tree, and tag writes.
