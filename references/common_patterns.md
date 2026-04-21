
---

## 📚 Файл: references/common_patterns.md

```markdown
# Common Browser Automation Patterns

## Паттерн 1: Авторизация

### Сценарий
Пользователь хочет автоматизировать вход в систему.

### Реализация
```python
{
  "action": "sequence",
  "steps": [
    {"action": "goto", "url": "https://example.com/login"},
    {"action": "wait", "selector": "form", "timeout": 5000},
    {"action": "fill", "selector": "input[name='email']", "value": "user@example.com"},
    {"action": "fill", "selector": "input[name='password']", "value": "password123"},
    {"action": "click", "selector": "button[type='submit']"},
    {"action": "wait", "selector": ".dashboard", "timeout": 10000},
    {"action": "screenshot", "path": "/tmp/after_login.png"}
  ]
}