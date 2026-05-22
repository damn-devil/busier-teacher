# BSUIR Teacher Schedule Bot

Telegram-бот для преподавателей БГУИР: расписание, уведомления о парах.

## Стек

Python · Flask · python-telegram-bot · Supabase (PostgreSQL) · Render

## Локальный запуск

```bash
cp .env.example .env
# заполните .env: BOT_TOKEN, SUPABASE_URL, SUPABASE_ANON_KEY
pip install -r requirements.txt
python api/bot.py
```

## Деплой на Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy)

1. Нажмите кнопку выше или создайте Web Service вручную
2. Подключите репозиторий
3. Установите переменные окружения (см. .env.example)
4. В настройках Render добавьте **Cron Job** с URL `https://your-app.onrender.com/cron` (для уведомлений)

## Supabase (база данных)

1. Создайте проект в [supabase.com](https://supabase.com)
2. Выполните SQL из `supabase_schema.sql` в SQL Editor
3. Скопируйте `Project URL` и `anon public key` в `.env`

## Команды

- `/start` — приветствие
- `/set_teacher [urlId]` — установить преподавателя (например, s-nesterenkov)
- `/schedule` — расписание на сегодня
- `/schedule_tomorrow` — на завтра
- `/week_schedule` — на неделю
- `/next_lesson` — следующая пара
- `/current_lesson` — текущая пара
- `/settings` — настройки уведомлений
- `/stats` — статистика
- `/help` — помощь
