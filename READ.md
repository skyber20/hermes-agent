# BrowserUse_and_ComputerUse_skills

Чтобы запустить tool browser-use вместе с hermes agent тебе нужно выполнить следующие действия
```commandline
git clone https://git.lambda.coredump.ru/APEX/BrowserUse_and_ComputerUse_skills.git
git switch feature/telegram-browser-integration
touch .env
```

В создавшемся .env файле заполните переменные в соответствии с шаблоном, расположенном в .env.example
BROWSER_VIEW_URL заполняется после запуска

#### Запуск удаленно

```commandline
docker compose --profile remote up --build
docker compose logs tunnel
```
После команды логов листаешь терминал и ищешь ссылку https в рамке. Её вписываешь в переменную BROWSER_VIEW_URL.
Чтобы увидеть действия агента, переходишь по данной ссылке и выбираешь vnc.html.
Далее в мессенджере просишь агента сделать что-то через tool browser-use.
Возможно придётся перезапустить контейнеры, но при перезапуске контейнеров меняется ссылка.

#### Запуск локально

BROWSER_VIEW_URL устанавливается как http://localhost:6080

```commandline
docker compose up
```

---
```commandline
docker compose down
docker compose up -d
```
## Удачного пользования