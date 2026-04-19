# Быстрый старт — Лабораторная работа №3

## 0) Важно
ЛР3 выполняется **на коде из ЛР2**.  
В каталоге `lab_03` уже лежит копия `backend/frontend` из `lab_02`.

## 1) Поднять окружение
```bash
cd lab_03
docker compose down -v
docker compose up -d --build
```

## 2) Сгенерировать данные (готовый seed)
```bash
docker compose exec -T db psql -U postgres -d marketplace -f /sql/01_seed_100k.sql
```

## 3) Снять baseline EXPLAIN ANALYZE (заполняется студентом)
Заполните `sql/02_explain_before.sql`, затем:
```bash
docker compose exec -T db psql -U postgres -d marketplace -f /sql/02_explain_before.sql
```

## 4) Индексы и повторные замеры (заполняется студентом)
Заполните:
- `sql/03_indexes.sql`
- `sql/04_explain_after_indexes.sql`

Выполните:
```bash
docker compose exec -T db psql -U postgres -d marketplace -f /sql/03_indexes.sql
docker compose exec -T db psql -U postgres -d marketplace -f /sql/04_explain_after_indexes.sql
```

## 5) Партиционирование и финальные замеры (заполняется студентом)
Заполните:
- `sql/05_partition_orders.sql`
- `sql/06_explain_after_partition.sql`

Выполните:
```bash
docker compose exec -T db psql -U postgres -d marketplace -f /sql/05_partition_orders.sql
docker compose exec -T db psql -U postgres -d marketplace -f /sql/06_explain_after_partition.sql
```

## 6) Отчёт
Заполните `REPORT.md` по результатам всех замеров и сравнений.
