# CV Extractor MVP

Pet-проект: сервис на Python + FastAPI, который с помощью LLM извлекает данные из резюме и возвращает строго типизированный JSON по Pydantic-схеме.

Основные фичи:
- `POST /parse_resume` — принимает сырой текст резюме (`text`, `lang`), возвращает структуру с name/contacts/links/skills/education/jobs/languages.
- Нормализация телефона (E.164), дат (YYYY-MM), skills (lower + dedup).
- Фоллбеки на regex для email/phone.
- Идемпотентность по `hash(text)`, кэш и логи в SQLite (`runs`, `results`).
- Метаданные: `request_id`, `model`, `tokens_in/out`, `latency_ms`, `status`.

## Как запустить локально

```bash
git clone https://github.com/ConsciousnessOno/cv-extractor-mvp.git
cd cv-extractor-mvp

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # вписать LLM_API_KEY в .env
uvicorn app.main:app --reload --port 8000
```

Проверка:
curl http://127.0.0.1:8000/health

Пример запроса: 
curl -X POST "http://127.0.0.1:8000/parse_resume" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Иван Иванов, ML Engineer. Email: ivan@example.com, телефон 8 999 123-45-67. Работал в Yandex с июня 2020 по март 2023. Занимался обучением различных моделей, а также оптимизацией бизнес задач. Мой стек: Python; FastAPI; ML; SQL; Проживаю в Москве, по образованию SoftWare Engineer, закончил МГУ в 2019 году, бакалавр. Языки: Русский C2, Английский B1",
    "lang": "ru"
  }' | jq

Тесты:
pytest -q
