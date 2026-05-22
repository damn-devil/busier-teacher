from flask import Flask, jsonify
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
import os
import threading
import time
import requests
import json
from datetime import datetime, timedelta
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
            "Чтобы начать получать уведомления о парах, "
            "отправьте свой ID преподавателя:\n"
            "/set_teacher ВАШ_ID\n\n"
            "Пример: /set_teacher s-nesterenkov"
        )
        await update.message.reply_text(msg)

    async def set_teacher(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Укажите ID преподавателя:\n/set_teacher ВАШ_ID")
            return

        teacher_id = context.args[0]
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
            "/set_teacher [id] - Установить преподавателя\n"
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


def run_scheduler():
    """Фоновый планировщик уведомлений"""
    print("⏰ Scheduler started")
    while True:
        try:
            now = datetime.now(MINSK_TZ)
            today_en = now.strftime("%A")
            weekdays_ru = {
                "Monday": "Понедельник", "Tuesday": "Вторник", "Wednesday": "Среда",
                "Thursday": "Четверг", "Friday": "Пятница", "Saturday": "Суббота", "Sunday": "Воскресенье",
            }
            today_ru = weekdays_ru.get(today_en, today_en)

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

                for lesson in lessons:
                    start_str = lesson.get("startLessonTime", "")
                    end_str = lesson.get("endLessonTime", "")
                    if not start_str or not end_str:
                        continue

                    start_h, start_m = map(int, start_str.split(":"))
                    end_h, end_m = map(int, end_str.split(":"))
                    lesson_start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
                    lesson_end = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

                    # За 10 минут до начала
                    if now == lesson_start - timedelta(minutes=10):
                        info = api.format_lesson_info(lesson, "🔔")
                        send_tg(chat_id, f"🔔 Скоро пара!\n\n{info}", parse_mode="Markdown")

                    # Начало пары
                    if now == lesson_start:
                        info = api.format_lesson_info(lesson, "🎯")
                        send_tg(chat_id, f"🎯 Пара началась!\n\n{info}", parse_mode="Markdown")

                    # Конец пары
                    if now == lesson_end:
                        info = api.format_lesson_info(lesson, "✅")
                        next_lesson = api.get_next_lesson(sched)
                        extra = ""
                        if next_lesson and next_lesson != lesson:
                            extra = f"\n\n➡️ Следующая:\n{api.format_lesson_info(next_lesson, '⏰')}"
                        else:
                            extra = "\n\n🎉 Пар больше нет сегодня!"
                        send_tg(chat_id, f"✅ Пара окончена!\n\n{info}{extra}", parse_mode="Markdown")

            # 7:00 утра — рассылка расписания
            if now.hour == 7 and now.minute == 0:
                for t in teachers:
                    chat_id = t["telegram_chat_id"]
                    teacher_id = t["teacher_url_id"]
                    sched = db.get_schedule(teacher_id)
                    if not sched:
                        continue
                    today = api.get_today_schedule(sched)
                    if today:
                        msg = f"🌅 Доброе утро!\n\n📚 Расписание на сегодня:\n\n"
                        for lesson in today:
                            msg += api.format_lesson_info(lesson) + "\n\n"
                        send_tg(chat_id, msg, parse_mode="Markdown")

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
    application.add_handler(CommandHandler("set_teacher", schedule_bot.set_teacher))
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
