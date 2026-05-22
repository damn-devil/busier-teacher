from flask import Flask, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
import threading
import time
import requests
from datetime import datetime
import pytz

from utils.database import Database
from utils.api_client import BsuirAPI

app = Flask(__name__)

db = Database()
api = BsuirAPI()
application = None
MINSK_TZ = pytz.timezone("Europe/Minsk")
BOT_TOKEN = os.getenv("BOT_TOKEN")

class ScheduleBot:
    def __init__(self):
        self.db = db
        self.api = api

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = (
            "👨‍🏫 Добро пожаловать в бот расписания БГУИР!\n\n"
            "Просто отправьте свой ID преподавателя, "
            "и я начну присылать уведомления о парах.\n\n"
            "Пример: отправьте *s-nesterenkov*"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        teacher_id = update.message.text.strip()
        if not teacher_id:
            await update.message.reply_text("❌ Отправьте ID преподавателя (например: s-nesterenkov)")
            return
        schedule_data = self.api.get_schedule(url_id=teacher_id)

        if not schedule_data:
            await update.message.reply_text("❌ Не удалось получить расписание. Проверьте ID преподавателя.")
            return

        parsed = self.api.parse_schedule_data(schedule_data)
        if not parsed:
            await update.message.reply_text("❌ Ошибка обработки расписания.")
            return

        self.db.save_teacher_settings(
            update.effective_chat.id,
            teacher_id,
            parsed["group_name"],
            parsed["faculty"],
            parsed["course"],
        )
        self.db.save_schedule(teacher_id, schedule_data)

        await update.message.reply_text(
            f"✅ Преподаватель *{parsed['group_name']}* установлен!\n\n"
            f"Теперь вы будете получать уведомления о парах.",
            parse_mode="Markdown",
        )
        await self.schedule_today(update, context)

    async def schedule_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя: /set_teacher ВАШ_ID")
            return

        sched = self.db.get_schedule(settings["teacher_url_id"])
        if not sched:
            sched = self.api.get_schedule(url_id=settings["teacher_url_id"])
            if sched:
                self.db.save_schedule(settings["teacher_url_id"], sched)

        if not sched:
            await update.message.reply_text("❌ Не удалось получить расписание")
            return

        today = self.api.get_today_schedule(sched)
        if not today:
            await update.message.reply_text("🎉 На сегодня пар нет!")
            return

        now_minsk = datetime.now(MINSK_TZ)
        msg = f"📚 Расписание на сегодня ({now_minsk.strftime('%d.%m.%Y')})\n\n"
        for lesson in today:
            msg += self.api.format_lesson_info(lesson) + "\n\n"
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        admin_id = os.getenv("ADMIN_CHAT_ID")
        if not admin_id or str(update.effective_chat.id) != admin_id:
            await update.message.reply_text("⛔ Доступ запрещён")
            return

        total = self.db.get_total_teachers()
        teachers = self.db.get_all_teachers()

        msg = f"📊 Статистика бота\n\n"
        msg += f"👨‍🏫 Всего преподавателей: {total}\n\n"
        if teachers:
            msg += "Зарегистрированные преподаватели:\n"
            for t in teachers:
                name = t.get("teacher_name", "Неизвестно")
                dept = t.get("department", "")
                msg += f"• {name}" + (f" ({dept})" if dept else "") + "\n"

        await update.message.reply_text(msg)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🆘 Помощь\n\n"
            "Просто отправьте ID преподавателя, чтобы начать.\n"
            "/schedule - Расписание на сегодня\n"
            "/stats - Статистика (только для админа)\n"
            "/help - Помощь"
        )


def send_tg(chat_id: int, text: str, parse_mode: str = None):
    if not BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")


def parse_time(t_str):
    """Парсит 'HH:MM' → (часы, минуты)"""
    parts = t_str.split(":")
    return int(parts[0]), int(parts[1])


def run_scheduler():
    print("⏰ Scheduler started")
    while True:
        try:
            now = datetime.now(MINSK_TZ)
            teachers = db.get_all_teachers()

            for t in teachers:
                chat_id = t["telegram_chat_id"]
                teacher_id = t["teacher_url_id"]

                sched = db.get_schedule(teacher_id)
                if not sched:
                    sched = api.get_schedule(url_id=teacher_id)
                    if sched:
                        db.save_schedule(teacher_id, sched)
                    else:
                        continue

                lessons = api.get_today_schedule(sched)
                if not lessons:
                    continue

                now_ts = now.hour * 60 + now.minute

                # — Будильник за 30 мин до первой пары —
                first = lessons[0]
                fh, fm = parse_time(first.get("startLessonTime", ""))
                first_start_min = fh * 60 + fm
                if now_ts == first_start_min - 30:
                    msg = f"🌅 Доброе утро! Через 30 минут начнутся пары.\n\n📚 Расписание на сегодня:\n\n"
                    for lesson in lessons:
                        msg += api.format_lesson_info(lesson) + "\n\n"
                    send_tg(chat_id, msg, parse_mode="Markdown")
                    continue

                for i, lesson in enumerate(lessons):
                    start_str = lesson.get("startLessonTime", "")
                    end_str = lesson.get("endLessonTime", "")
                    if not start_str or not end_str:
                        continue

                    sh, sm = parse_time(start_str)
                    eh, em = parse_time(end_str)
                    start_min = sh * 60 + sm
                    end_min = eh * 60 + em

                    # — Начало пары —
                    if now_ts == start_min:
                        info = api.format_lesson_info(lesson, "🎯")
                        send_tg(chat_id, f"🎯 Пара началась!\n\n{info}", parse_mode="Markdown")

                    # — 5 минут до следующей пары (окончание перемены) —
                    if i > 0:
                        prev_end_str = lessons[i - 1].get("endLessonTime", "")
                        if prev_end_str:
                            peh, pem = parse_time(prev_end_str)
                            prev_end_min = peh * 60 + pem
                            # Если перемена >= 10 мин, предупреждаем за 5 мин до начала
                            if start_min - prev_end_min >= 10 and now_ts == start_min - 5:
                                info = api.format_lesson_info(lesson, "⏰")
                                send_tg(chat_id, f"⏰ До пары 5 минут!\n\n{info}", parse_mode="Markdown")

                    # — Конец пары + следующая —
                    if now_ts == end_min:
                        info = api.format_lesson_info(lesson, "✅")
                        if i + 1 < len(lessons):
                            next_lesson = lessons[i + 1]
                            next_info = api.format_lesson_info(next_lesson, "➡️")
                            extra = f"\n\n☕ Перемена до {next_lesson.get('startLessonTime', '?')}\n\n{next_info}"
                        else:
                            extra = "\n\n🎉 На сегодня пар больше нет! Хорошего дня!"
                        send_tg(chat_id, f"✅ Пара окончена!\n\n{info}{extra}", parse_mode="Markdown")

        except Exception as e:
            print(f"Scheduler error: {e}")

        time.sleep(30)


def run_bot():
    global application
    bot_token = os.getenv("BOT_TOKEN")
    if not bot_token:
        print("❌ BOT_TOKEN not found")
        return

    schedule_bot = ScheduleBot()
    application = Application.builder().token(bot_token).build()
    application.add_handler(CommandHandler("start", schedule_bot.start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_bot.handle_text))
    application.add_handler(CommandHandler("schedule", schedule_bot.schedule_today))
    application.add_handler(CommandHandler("stats", schedule_bot.stats))
    application.add_handler(CommandHandler("help", schedule_bot.help_command))

    print("🤖 Bot starting polling...")
    application.run_polling(close_loop=False)


@app.route("/")
def home():
    return jsonify({"status": "running"})


threading.Thread(target=lambda: app.run(host="0.0.0.0", port=3000, debug=False), daemon=True).start()
threading.Thread(target=run_scheduler, daemon=True).start()
run_bot()
