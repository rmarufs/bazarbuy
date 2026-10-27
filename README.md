# Bazarbuy.tj

Каталог товаров с предзаказом через WhatsApp. Подробности: `docs/SPEC.md`.

## Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install   # только для e2e-тестов
cp .env.example .env # затем заполните значения в .env
```

Нужны две базы PostgreSQL: основная и тестовая (адреса в `DATABASE_URL` и `TEST_DATABASE_URL`).

## Запуск

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Проверка: http://127.0.0.1:8000/health

## Тесты

```bash
pytest
```
