# BrowserUse_and_ComputerUse_skills

Чтобы запустить tool browser-use вместе с hermes agent тебе нужно выполнить следующие действия
```commandline
git clone https://git.lambda.coredump.ru/APEX/BrowserUse_and_ComputerUse_skills.git
git switch feature/telegram-browser-integration
touch .env
```
В создавшемся .env файле заполните переменные в соответствии с шаблоном, расположенном в .env.example
BROWSER_VIEW_URL заполняется после запуска
```commandline
docker compose up -d --build
docker compose logs tunnel
```
После команды логов листаешь терминал и ищешь ссылку https в рамке. Её вписываешь в переменную BROWSER_VIEW_URL.
Чтобы увидеть действия агента, переходишь по данной сслыке и выбираешь vnc.html.
Далее в мессенджере просишь агента сделать что-то через tool browser-use.
Во время выполнения Hermes будет обновлять одно progress-сообщение в Telegram:
текущая страница, короткие действия, ошибки и просьба помочь, если замечена капча
или антибот-проверка. Частоту и объем можно настроить через
`BROWSER_LIVE_LOG_POLL_INTERVAL` и `BROWSER_LIVE_LOG_MAX_EVENTS` в `.env`.
Возможно придётся перезапустить контейнеры, но при перезапуске контейнеров меняется ссылка.
```commandline
docker compose down
docker compose up -d
```
## Удачного пользования
