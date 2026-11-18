# Vigilante del PC (bot de agentes)

Avisa por Telegram si el PC deja de dar latido (>25 min) y cuando vuelve. Solo biblioteca estandar, sin IA.
Este repo es publico a proposito (minutos de Actions ilimitados): **no contiene ningun secreto**. El token y el chat
estan en *Settings > Secrets and variables > Actions* (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).

## Regla de los 60 dias
GitHub desactiva los workflows programados de un repo sin actividad en 60 dias. `keepalive.yml` hace un commit vacio
los dias 1 y 15 si el ultimo commit tiene >=40 dias y reactiva `vigilante_pc.yml`. Si aun asi se parase:
Actions > Vigilante PC > *Enable workflow*.

## Pruebas (sin red)
`python -m unittest discover -s tests -v`
