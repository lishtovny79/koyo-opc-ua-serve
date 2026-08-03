# Установка и запуск

[English version](en/installation.md)

## Windows

Установите Python 3.11+, создайте виртуальное окружение и выполните
`pip install .`. Сервер запускается командой:

```powershell
koyo-opc-ua-server --config config/config.toml
```

Для постоянной работы зарегистрируйте эту команду как службу Windows через
принятый в организации менеджер служб. Используйте отдельную учётную запись,
имеющую доступ только к конфигурации и CSV-экспорту тегов.

## Linux

Создайте каталог `/opt/koyo-opc-ua-server`, установите пакет в виртуальное
окружение, скопируйте `config.example.toml` в `config.toml` и настройте его.
Пример [systemd-службы](../systemd/koyo-opc-ua-server.service) предполагает
именно этот путь.

## Docker

Соберите образ и передайте конфигурацию как внешний файл. Не помещайте
производственные CSV и конфигурации в Docker-образ:

```bash
docker build -t koyo-opc-ua-server .
docker run --rm --network host \
  -v /srv/koyo-opc/config.toml:/app/config/config.toml:ro \
  -v /srv/koyo-opc/tags.csv:/app/data/tags.csv:ro \
  koyo-opc-ua-server
```

В Docker Desktop опубликуйте TCP-порт 4840 и убедитесь, что контейнер имеет
UDP-доступ к PLC.

## Docker Compose

Скопируйте `config/config.example.toml` в `config/config.toml`, укажите IP
контроллера, затем выполните:

```bash
docker compose up -d --build
```

`compose.yaml` подключает `data/` для SQLite-каталога и `backups/` для резервных
копий. Поэтому они не пропадут при пересборке или перезапуске контейнера.

При изменении исходного кода пересоберите контейнер без кэша:

```bash
docker compose down --remove-orphans
docker compose build --no-cache
docker compose up -d --force-recreate
```
