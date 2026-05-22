import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import threading
import time
import requests
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
            "Расписания БГУИР!\n\n"
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

        username = update.effective_user.username if update.effective_user else None

        self.db.save_teacher_settings(
            update.effective_chat.id,
            teacher_id,
            parsed["group_name"],
            parsed["faculty"],
            parsed["course"],
            username,
        )
        self.db.save_schedule(teacher_id, schedule_data)

        settings = self.db.get_teacher_settings(update.effective_chat.id)
        if not settings:
            await update.message.reply_text(
                "✅ Преподаватель *{}* установлен!\n\n"
                "Теперь вы будете получать уведомления о парах.".format(parsed['group_name']),
                parse_mode="Markdown",
            )
            return

        await update.message.reply_text(
            f"✅ Преподаватель *{parsed['group_name']}* установлен!\n\n"
            f"Теперь вы будете получать уведомления о парах.",
            parse_mode="Markdown",
        )
        await self._send_day_schedule(update, settings)

    async def _send_day_schedule(self, update: Update, settings: dict):
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
        cw = self.api.get_current_week()
        week_label = "числитель" if cw == 1 else "знаменатель"
        msg = f"📚 Расписание на сегодня ({now_minsk.strftime('%d.%m.%Y')})\n"
        msg += f"📌 {cw}-я неделя ({week_label})\n\n"
        for i, lesson in enumerate(today, 1):
            msg += self.api.format_lesson_info(lesson, lesson_number=i) + "\n\n"
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def schedule_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя. Отправьте его ID.")
            return
        await self._send_day_schedule(update, settings)

    async def schedule_tomorrow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя. Отправьте его ID.")
            return

        sched = self.db.get_schedule(settings["teacher_url_id"])
        if not sched:
            sched = self.api.get_schedule(url_id=settings["teacher_url_id"])
            if sched:
                self.db.save_schedule(settings["teacher_url_id"], sched)

        if not sched:
            await update.message.reply_text("❌ Не удалось получить расписание")
            return

        tomorrow = self.api.get_tomorrow_schedule(sched)
        if not tomorrow:
            await update.message.reply_text("🎉 На завтра пар нет!")
            return

        now_minsk = datetime.now(MINSK_TZ)
        tomorrow_date = now_minsk + timedelta(days=1)
        cw = self.api.get_current_week()
        week_label = "числитель" if cw == 1 else "знаменатель"
        msg = f"📚 Расписание на завтра ({tomorrow_date.strftime('%d.%m.%Y')})\n"
        msg += f"📌 {cw}-я неделя ({week_label})\n\n"
        for i, lesson in enumerate(tomorrow, 1):
            msg += self.api.format_lesson_info(lesson, lesson_number=i) + "\n\n"
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def week_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя. Отправьте его ID.")
            return

        sched = self.db.get_schedule(settings["teacher_url_id"])
        if not sched:
            sched = self.api.get_schedule(url_id=settings["teacher_url_id"])
            if sched:
                self.db.save_schedule(settings["teacher_url_id"], sched)

        if not sched:
            await update.message.reply_text("❌ Не удалось получить расписание")
            return

        msg = self.api.get_week_schedule_text(sched)
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def current_lesson(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя. Отправьте его ID.")
            return

        sched = self.db.get_schedule(settings["teacher_url_id"])
        if not sched:
            sched = self.api.get_schedule(url_id=settings["teacher_url_id"])
            if sched:
                self.db.save_schedule(settings["teacher_url_id"], sched)

        if not sched:
            await update.message.reply_text("❌ Не удалось получить расписание")
            return

        lesson = self.api.get_current_lesson(sched)
        if not lesson:
            await update.message.reply_text("🎯 Сейчас нет пары")
            return

        msg = self.api.format_lesson_info(lesson, prefix="🎯")
        now = datetime.now(MINSK_TZ)
        now_min = now.hour * 60 + now.minute
        eh, em = parse_time(lesson.get("endLessonTime", ""))
        remaining = eh * 60 + em - now_min
        msg += f"\n\n⏳ До конца: {remaining} мин."
        await update.message.reply_text(f"🎯 Текущая пара\n\n{msg}", parse_mode="Markdown")

    async def next_lesson(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя. Отправьте его ID.")
            return

        sched = self.db.get_schedule(settings["teacher_url_id"])
        if not sched:
            sched = self.api.get_schedule(url_id=settings["teacher_url_id"])
            if sched:
                self.db.save_schedule(settings["teacher_url_id"], sched)

        if not sched:
            await update.message.reply_text("❌ Не удалось получить расписание")
            return

        lesson = self.api.get_next_lesson(sched)
        if not lesson:
            await update.message.reply_text("🎉 На сегодня пар больше нет!")
            return

        msg = self.api.format_lesson_info(lesson, prefix="➡️")
        now = datetime.now(MINSK_TZ)
        now_min = now.hour * 60 + now.minute
        sh, sm = parse_time(lesson.get("startLessonTime", ""))
        until = sh * 60 + sm - now_min
        msg += f"\n\n⏳ Начало через: {until} мин."
        await update.message.reply_text(f"➡️ Следующая пара\n\n{msg}", parse_mode="Markdown")

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
                uname = t.get("username", "")
                line = f"• {name}" + (f" ({dept})" if dept else "")
                if uname:
                    line += f" @{uname}"
                msg += line + "\n"

        await update.message.reply_text(msg)

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.db.delete_teacher(update.effective_chat.id)
        await update.message.reply_text(
            "🔄 Регистрация сброшена!\n\n"
            "Отправьте новый ID преподавателя, чтобы зарегистрироваться заново."
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🆘 Помощь\n\n"
            "Отправьте ID преподавателя (например: s-nesterenkov), чтобы начать.\n\n"
            "/schedule — расписание на сегодня\n"
            "/tomorrow — расписание на завтра\n"
            "/week — расписание на неделю\n"
            "/current — текущая пара\n"
            "/next — следующая пара\n"
            "/reset — сбросить регистрацию\n"
            "/stats — статистика (админ)\n"
            "/help — помощь"
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
                    cw = api.get_current_week()
                    week_label = "числитель" if cw == 1 else "знаменатель"
                    msg = f"🌅 Доброе утро! Через 30 минут начнутся пары.\n📌 {cw}-я неделя ({week_label})\n\n📚 Расписание на сегодня:\n\n"
                    for j, lesson in enumerate(lessons, 1):
                        msg += api.format_lesson_info(lesson, lesson_number=j) + "\n\n"
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

                    total_min = end_min - start_min

                    # — Начало пары —
                    if now_ts == start_min:
                        info = api.format_lesson_info(lesson, lesson_number=i + 1, prefix="🎯")
                        send_tg(
                            chat_id,
                            f"🎯 Пара началась!\n\n{info}\n\n⏳ До конца: {total_min} мин.",
                            parse_mode="Markdown",
                        )

                    # — Перерыв 5 минут внутри пары (через 40 мин от начала) —
                    break_start = start_min + 40
                    if break_start < end_min and now_ts == break_start:
                        remaining = end_min - (start_min + 45)
                        send_tg(
                            chat_id,
                            f"☕ Перерыв 5 минут\n\nДо конца пары осталось {remaining} мин.",
                        )

                    # — За 5 мин до конца пары —
                    if now_ts == end_min - 5:
                        send_tg(chat_id, f"⏰ До конца пары 5 минут!")

                    # — 5 минут до следующей пары (окончание перемены) —
                    if i > 0:
                        prev_end_str = lessons[i - 1].get("endLessonTime", "")
                        if prev_end_str:
                            peh, pem = parse_time(prev_end_str)
                            prev_end_min = peh * 60 + pem
                            if start_min - prev_end_min >= 10 and now_ts == start_min - 5:
                                info = api.format_lesson_info(lesson, lesson_number=i + 1, prefix="⏰")
                                send_tg(chat_id, f"⏰ До пары 5 минут!\n\n{info}", parse_mode="Markdown")

                    # — Конец пары + следующая —
                    if now_ts == end_min:
                        info = api.format_lesson_info(lesson, lesson_number=i + 1, prefix="✅")
                        if i + 1 < len(lessons):
                            next_lesson = lessons[i + 1]
                            next_info = api.format_lesson_info(next_lesson, lesson_number=i + 2, prefix="➡️")
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
    application.add_handler(CommandHandler("schedule", schedule_bot.schedule_today))
    application.add_handler(CommandHandler("tomorrow", schedule_bot.schedule_tomorrow))
    application.add_handler(CommandHandler("week", schedule_bot.week_schedule))
    application.add_handler(CommandHandler("current", schedule_bot.current_lesson))
    application.add_handler(CommandHandler("next", schedule_bot.next_lesson))
    application.add_handler(CommandHandler("reset", schedule_bot.reset))
    application.add_handler(CommandHandler("stats", schedule_bot.stats))
    application.add_handler(CommandHandler("help", schedule_bot.help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_bot.handle_text))

    print("🤖 Bot starting polling...")
    application.run_polling(close_loop=False, drop_pending_updates=True)


@app.route("/")
def home():
    return jsonify({"status": "running"})


if __name__ == "__main__":
    PORT = int(os.getenv("PORT", 3000))
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=PORT, debug=False), daemon=True).start()
    threading.Thread(target=run_scheduler, daemon=True).start()
    run_bot()
