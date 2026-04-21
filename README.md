# Лабораторная работа №3
## Диагностика и оптимизация маркетплейса

## Важное уточнение
Эта лабораторная является **продолжением lab_02**.  
В `lab_03` уже добавлена кодовая база предыдущей лабораторной:
- `backend/`
- `frontend/`
- `Dockerfile.backend`
- `Dockerfile.frontend`
- `.github/`

Если у студента в lab_02 есть доработки, их нужно перенести в соответствующие файлы `lab_03`.

## Цель работы
Научиться находить узкие места SQL-запросов и оптимизировать их:
- через `EXPLAIN ANALYZE`;
- через индексы с обоснованием типа;
- через партиционирование `orders` по дате;
- через сравнение метрик до/после.

## Что дано готовым
1. Кодовая база из lab_02.
2. Готовый seed на `100k` заказов: `sql/01_seed_100k.sql`.
3. Шаблоны для этапов диагностики и оптимизации:
   - `sql/02_explain_before.sql`
   - `sql/03_indexes.sql`
   - `sql/04_explain_after_indexes.sql`
   - `sql/05_partition_orders.sql`
   - `sql/06_explain_after_partition.sql`
4. Шаблон отчёта `REPORT.md`.

## Что нужно сделать студенту
1. Убедиться, что схема из предыдущих лаб доступна (обычно `backend/migrations/001_init.sql`).
2. Сгенерировать `100 000` заказов (скрипт уже готов).
3. Заполнить `02_explain_before.sql` — найти медленные запросы.
4. Заполнить `03_indexes.sql` — добавить индексы и обосновать выбор типа.
5. Заполнить `04_explain_after_indexes.sql` — снять повторные замеры.
6. Заполнить `05_partition_orders.sql` — реализовать партиционирование `orders` по дате.
7. Заполнить `06_explain_after_partition.sql` — финальные замеры.
8. Заполнить `REPORT.md`.

## Запуск
```bash
cd lab_03
docker compose down -v
docker compose up -d --build
```

Проверка сервисов (адреса открывайте в браузере или вызывайте через `curl` — строку `http://...` нельзя вводить в терминале как команду: shell воспринимает её как имя программы и выдаст `No such file or directory`).

Из каталога `lab_03`:

```bash
# Backend (ожидается JSON {"status":"ok"})
curl -sS http://127.0.0.1:8082/health

# Frontend (ожидается HTTP 200 и HTML)
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5174/

# PostgreSQL (проверка из контейнера — не нужен локальный pg_isready)
docker compose exec -T db pg_isready -U postgres
```

Порт Postgres на хосте: **5434** (с хоста: `localhost:5434`; из контейнеров Compose — сервис `db`, порт **5432**).

### Интерфейс в браузере

После `docker compose up -d` можно открыть вручную:

- фронтенд: http://localhost:5174  
- проверка API: http://localhost:8082/health  

**WSL2** (браузер Windows из терминала WSL):

```bash
cmd.exe /c start http://localhost:5174
cmd.exe /c start http://localhost:8082/health
```

**Linux** с графикой:

```bash
xdg-open http://localhost:5174
```

## Порядок выполнения SQL
```bash
# 1) Seed (готовый)
docker compose exec -T db psql -U postgres -d marketplace -f /sql/01_seed_100k.sql

# 2) Диагностика до оптимизаций (заполняется студентом)
docker compose exec -T db psql -U postgres -d marketplace -f /sql/02_explain_before.sql

# 3) Индексы (заполняется студентом)
docker compose exec -T db psql -U postgres -d marketplace -f /sql/03_indexes.sql

# 4) Повторные замеры после индексов (заполняется студентом)
docker compose exec -T db psql -U postgres -d marketplace -f /sql/04_explain_after_indexes.sql

# 5) Партиционирование (заполняется студентом)
docker compose exec -T db psql -U postgres -d marketplace -f /sql/05_partition_orders.sql

# 6) Финальные замеры (заполняется студентом)
docker compose exec -T db psql -U postgres -d marketplace -f /sql/06_explain_after_partition.sql
```

## Тестирование (pytest, не SQL-скрипты лабы)

Нужны запущенные контейнеры (`docker compose up -d`) и отдельная БД `marketplace_test` со схемой из миграции (рабочая БД `marketplace` после seed/партиций для тестов не подходит):

```bash
docker compose exec -T db psql -U postgres -c "DROP DATABASE IF EXISTS marketplace_test WITH (FORCE);"
docker compose exec -T db psql -U postgres -c "CREATE DATABASE marketplace_test;"
docker compose exec -T db psql -U postgres -d marketplace_test -f /docker-entrypoint-initdb.d/001_init.sql
```

**Важно:** блок из трёх команд выше нужно выполнить **до** `pytest`. Иначе БД `marketplace_test` не существует: интеграционные тесты упадут с `database "marketplace_test" does not exist`, тесты конкурентной оплаты будут помечены как `SKIPPED`.

**Каталог:** `pytest app/tests/` имеет смысл только **из `backend/`** (там лежит `app/tests/`). Если запустить `pytest app/tests/` из корня `lab_03`, будет ошибка `file or directory not found: app/tests/`.

Из корня репозитория `lab_03`:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH="$(pwd)"
export DATABASE_URL='postgresql+asyncpg://postgres:postgres@127.0.0.1:5434/marketplace_test'
pytest app/tests/ -v --tb=short
```

Без `source .venv/bin/activate` часто подхватывается системный `pytest` из дистрибутива — тогда не находится `pytest_asyncio` (`ModuleNotFoundError`). Проверка: `which pytest` должен указывать на `.../backend/.venv/bin/pytest`.

Без локального venv можно так же из контейнера (после создания `marketplace_test` как выше):

```bash
docker compose run --rm \
  -e DATABASE_URL='postgresql+asyncpg://postgres:postgres@db:5432/marketplace_test' \
  backend pytest app/tests/ -v --tb=short
```

Блок «Порядок выполнения SQL» выше предполагает: вы в каталоге `lab_03`, контейнеры уже подняты (`docker compose up -d`). Скрипт `05_partition_orders.sql` рассчитан на однократное применение: при повторном запуске `psql` завершится с ошибкой (осознанно), пока не выполните `docker compose down -v` и не поднимете БД заново. Повтор `01` после партиционирования без сброса тома тоже не входит в сценарий лабы — для чистого прогона с начала: `docker compose down -v`, затем `up` и шаги 1–6 по порядку.

## Структура проекта
```
lab_03/
├── .github/                     # из lab_02
├── backend/                     # из lab_02
├── frontend/                    # из lab_02
├── Dockerfile.backend           # из lab_02
├── Dockerfile.frontend          # из lab_02
├── docker-compose.yml
├── README.md
├── QUICKSTART.md
├── STATUS.md
├── REPORT.md                    # отчёт по ЛР3
└── sql/
    ├── 00_schema.sql            # справочный (опционально)
    ├── 01_seed_100k.sql         # готовый seed
    ├── 02_explain_before.sql    # диагностика до оптимизаций
    ├── 03_indexes.sql           # индексы
    ├── 04_explain_after_indexes.sql # замеры после индексов
    ├── 05_partition_orders.sql  # партиционирование orders
    └── 06_explain_after_partition.sql # финальные замеры
```

## Критерии оценки
- Диагностика и чтение `EXPLAIN ANALYZE` — 30%
- Индексы и обоснование выбора типа — 25%
- Партиционирование и корректность замеров — 25%
- Качество итогового отчёта — 20%

## Важно
- Оцениваются не только SQL-скрипты, но и качество аналитики в отчёте.
- Нужно явно указать, что **не удалось** ускорить одними индексами и почему.
