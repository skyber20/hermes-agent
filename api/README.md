# Browser REST API

REST API-обертка над `browser-use` RPC (`POST /run` в контейнере браузера).

Сервис принимает задачу, ставит ее в in-memory очередь, выполняет через `browser-use` и отдает статус/результат по `task_id`.

## Актуальный статус

Проверено smoke-тестом:
- `GET /health` отвечает `200` с `{"ok": true}`
- `POST /api/browser/tasks` возвращает `202` и `task_id`
- `GET /api/browser/tasks/{task_id}` возвращает `queued/running/...`
- `GET /api/browser/tasks/{task_id}/result` возвращает `202`, пока задача не завершена

## Архитектура

Слои сейчас разделены и выглядят нормально для MVP:

- `api/main.py` — точка входа ASGI (`uvicorn api.main:app`), сборка `FastAPI` и lifespan
- `api/routes/tasks.py` — HTTP-слой (валидация входа/выхода, status codes)
- `api/services/task_service.py` — orchestration (фоновые задачи, timeout, обработка ошибок)
- `api/repositories/task_store.py` — in-memory хранилище задач
- `api/clients/browser_rpc_client.py` — aiohttp-клиент к browser RPC
- `api/clients/browser_rpc_contracts.py` — protocol + исключения RPC-слоя
- `api/contracts/task_schemas.py` — Pydantic request/response DTO
- `api/domain/task_status.py` — доменный enum статусов
- `api/core/settings.py` — конфигурация из env

## Ограничения текущей реализации

- хранилище in-memory: после рестарта контейнера задачи теряются
- нет ретраев RPC при транспортных ошибках
- нет отмены задач через API
- один инстанс процесса хранит задачи только локально (без shared state)

## Переменные окружения

- `BROWSER_API_HOST` (default: `0.0.0.0`)
- `BROWSER_API_PORT` (default: `8080`)
- `BROWSER_USE_RPC_URL` (default: `http://browser:8787/run`)
- `BROWSER_USE_RPC_TIMEOUT` (default: `900`)
- `BROWSER_API_MAX_CONCURRENCY` (default: `2`)

## Локальный запуск

```zsh
cd "/Users/fedorkobylkevic/PycharmProjects/BrowserUse_and_ComputerUse_skills"
source .venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8088
```

## Запуск через Docker Compose

```zsh
cd "/Users/fedorkobylkevic/PycharmProjects/BrowserUse_and_ComputerUse_skills"
docker compose build browser-api
docker compose up -d browser browser-api
docker compose logs -f browser-api
```

## REST API

### `GET /health`

Проверка доступности API.

Пример ответа:

```json
{"ok": true}
```

### `POST /api/browser/tasks`

Создать задачу.

Request:

```json
{
  "task": "Открой example.com и верни title",
  "timeout": 300,
  "metadata": {"source": "manual"}
}
```

Response `202`:

```json
{
  "task_id": "53f54fa4c1f24219b3949d56b0457875",
  "status": "queued"
}
```

### `GET /api/browser/tasks/{task_id}`

Текущий статус и таймстемпы.

### `GET /api/browser/tasks/{task_id}/result`

- `202` если задача еще `queued/running`
- `200` с финальным payload после завершения

## Быстрый end-to-end пример

```zsh
curl -sS http://localhost:8088/health

RESP=$(curl -sS -X POST http://localhost:8088/api/browser/tasks \
  -H "Content-Type: application/json" \
  -d '{"task":"Открой example.com и верни title","timeout":30}')

echo "$RESP"

TASK_ID=$(python -c "import json,sys;print(json.loads(sys.argv[1])['task_id'])" "$RESP")

curl -sS "http://localhost:8088/api/browser/tasks/$TASK_ID"
curl -sS "http://localhost:8088/api/browser/tasks/$TASK_ID/result"
```
