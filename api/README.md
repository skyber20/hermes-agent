# Browser REST API

REST-обертка над `browser-use` RPC (`http://browser:8787/run`).

## Endpoints

- `GET /health`
- `POST /api/browser/tasks`
- `GET /api/browser/tasks/{task_id}`
- `GET /api/browser/tasks/{task_id}/result`

## Пример

```bash
curl -sS -X POST http://localhost:8088/api/browser/tasks \
  -H "Content-Type: application/json" \
  -d '{"task":"Открой example.com и верни заголовок страницы","timeout":300}'
