# Koyo OPC UA Server

**Язык:** Русский | [English](README.en.md)

OPC UA-сервер для контроллеров Koyo / DirectLOGIC. Текущая реализация
транспорта рассчитана на DL205. Сервер импортирует теги из CSV-экспорта Kepware,
создаёт дерево OPC UA, читает значения из PLC и принимает запись от OPC UA-клиентов.

Поддерживаемые типы: `Boolean`, `Word`, `BCD`, `LBCD`, `Float`.

> Программа управляет промышленным оборудованием. До подключения к реальному
> процессу проверьте работу на стенде или тестовом контроллере.

## Возможности

- Импорт иерархических имён тегов из Kepware CSV.
- Групповое чтение PLC для уменьшения сетевой нагрузки.
- Запись значений, включая атомарную запись Float из двух слов.
- Запуск с пустым каталогом или с опциональным CSV-импортом.
- Постоянное хранение тегов в SQLite: добавленные клиентом теги сохраняются
  после перезапуска.
- Создание online-backup SQLite из OPC UA-клиента без остановки сервера.
- Запуск как Python-пакета, Docker-контейнера или системной службы.

## Быстрый запуск

Нужен Python 3.11 или новее.

```bash
git clone <your-gitlab-url>/koyo-opc-ua-server.git
cd koyo-opc-ua-server
python -m venv .venv
```

Активируйте виртуальное окружение, установите пакет и создайте рабочую
конфигурацию:

```bash
pip install .
copy config\config.example.toml config\config.toml
koyo-opc-ua-server --config config/config.toml
```

В Linux/macOS вместо `copy` используйте `cp`. До запуска задайте IP контроллера
в `config/config.toml`.

### Docker Compose

Скопируйте `config/config.example.toml` в `config/config.toml`, укажите
`plc.host`, затем выполните:

```bash
docker compose up -d --build
```

[compose.yaml](compose.yaml) сохраняет каталог SQLite в `data/`, а резервные
копии — в `backups/`. Остановка контейнера: `docker compose down`.

Endpoint OPC UA настраивается в секции `[opcua]`, например:

```text
opc.tcp://<IP_сервера>:4840/freeopcua/server/
```

Сервер намеренно работает без сертификатов OPC UA. Ограничьте доступ к порту
4840 доверенной промышленной сетью или firewall.

## Конфигурация

Смотрите [config/config.example.toml](config/config.example.toml). Скопируйте
его в `config/config.toml`; этот рабочий файл исключён из Git.

- `plc.host` — IP-адрес контроллера или Ethernet-интерфейса.
- `plc.tags_csv` — необязательный путь к CSV-экспорту Kepware. Пустая строка
  запускает сервер без импорта тегов.
- `plc.tags_database` — SQLite-каталог тегов.
- `plc.backup_directory` — каталог для online-backup SQLite.
- `polling.interval_seconds` — пауза после полного цикла чтения.
- `polling.write_subscription_interval_ms` — задержка обработки записи клиента.

Подробности: [установка](docs/installation.md),
[экспорт тегов](docs/tag-export.md) и [диагностика](docs/troubleshooting.md).

## Управление тегами из OPC UA-клиента

В `Objects/TagManagement` доступны методы:

- `AddTag(Name, Address, DataType, ClientAccess)` — добавляет тег в память и SQLite.
  Допустимые `DataType`: `Boolean`, `Word`, `BCD`, `LBCD`, `Float`; обычно
  `ClientAccess` имеет значение `R/W` или `R`.
- `RemoveTag(Name)` — удаляет тег из SQLite, плана чтения PLC и дерева OPC UA.
  Пустые папки в дереве остаются.
- `BackupTags()` — создаёт согласованную SQLite-копию с отметкой времени.

Методы сразу возвращают `Queued`. Итог операции смотрите в
`Objects/ServerStatus/LastTagOperation`. БД не используется в цикле опроса PLC,
поэтому хранение тегов не замедляет штатное чтение и запись значений.

## Поддержка проекта

Если проект помогает в работе, поддержите его добровольным переводом. Донаты
помогают развивать поддержку новых контроллеров и улучшать документацию.

<a href="https://finance.ozon.ru/apps/sbp/ozonbankpay/019fc906-85e1-7e75-9b85-4807314b4aab">
  <img src="docs/donate-qr.jpg" width="220" alt="QR-код для поддержки проекта через СБП">
</a>

**[Открыть страницу перевода через СБП](https://finance.ozon.ru/apps/sbp/ozonbankpay/019fc906-85e1-7e75-9b85-4807314b4aab)**

Отсканируйте QR-код в банковском приложении или откройте ссылку с мобильного
устройства. Спасибо за поддержку проекта.

## Обратная связь и релизы

Сообщайте о воспроизводимых проблемах через GitLab Issues. Укажите версию
сервера, модель контроллера/интерфейса, обезличенную строку тега, логи и сетевой
трафик только если в нём нет производственных адресов или учётных данных.

Версии имеют формат `MAJOR.MINOR.PATCH`; видимые пользователю изменения
записываются в [CHANGELOG.md](CHANGELOG.md).

## Лицензия

Проект подготовлен под [лицензией MIT](LICENSE). Перед первой публичной
публикацией замените держателя авторских прав при необходимости.
