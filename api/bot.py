from flask import Flask, request, jsonify
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
import os
import asyncio
import threading
from datetime import datetime, timedelta

from utils.database import Database
from utils.api_client import BsuirAPI

# Инициализация Flask приложения
app = Flask(__name__)

# Глобальные переменные
db = Database()
api = BsuirAPI()
bot = None
application = None
loop = asyncio.new_event_loop()

def _start_loop(lo):
    asyncio.set_event_loop(lo)
    lo.run_forever()

t = threading.Thread(target=_start_loop, args=(loop,), daemon=True)
t.start()

class ScheduleBot:
    def __init__(self):
        self.db = db
        self.api = api
        self.bot = Bot(token=os.getenv('BOT_TOKEN'))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_text = """
👨‍🏫 *Бот расписания БГУИР для преподавателей*

*Основные команды:*
/schedule - Расписание на сегодня
/schedule_tomorrow - На завтра  
/next_lesson - Следующая пара
/current_lesson - Текущая пара
/week_schedule - На всю неделю
/set_teacher - Установить преподавателя

*Дополнительно:*
/help - Помощь
/stats - Статистика зарегистрированных преподавателей

🔔 *Авто-уведомления:* 
• Утреннее расписание (7:00)
• За 10 мин до пары
• За 5 мин до конца парy
• О начале/конце пары
• На перерыве (пятиминутка в середине пары)
        """
        
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def set_teacher(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Установить ID преподавателя"""
        if not context.args:
            await update.message.reply_text("❌ Укажите ID преподавателя: `/set_teacher 12345`", parse_mode='Markdown')
            return
        
        teacher_id = context.args[0]
        
        # Проверяем преподавателя через API
        schedule_data = self.api.get_schedule(url_id=teacher_id)
        
        if not schedule_data:
            await update.message.reply_text("❌ Не удалось получить расписание. Проверьте ID преподавателя.")
            return
        
        parsed_data = self.api.parse_schedule_data(schedule_data)
        if not parsed_data:
            await update.message.reply_text("❌ Ошибка обработки расписания.")
            return
        
        # Сохраняем настройки
        self.db.save_teacher_settings(
            update.effective_chat.id,
            teacher_id,
            parsed_data['group_name'],
            parsed_data['faculty'],
            parsed_data['course']
        )
        
        self.db.save_schedule(teacher_id, schedule_data)
        
        success_msg = f"""
✅ *Преподаватель установлен!*

*Преподаватель:* {parsed_data['group_name']}
*Кафедра:* {parsed_data['faculty']}  
*Должность:* {parsed_data['course']}

Теперь вы будете получать уведомления о расписании! 🎉
        """
        
        await update.message.reply_text(success_msg, parse_mode='Markdown')
    
    async def schedule_today(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Расписание на сегодня"""
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя: `/set_teacher 12345`", parse_mode='Markdown')
            return
        
        schedule_data = self.db.get_schedule(settings['teacher_url_id'])
        if not schedule_data:
            schedule_data = self.api.get_schedule(url_id=settings['teacher_url_id'])
            if schedule_data:
                self.db.save_schedule(settings['teacher_url_id'], schedule_data)
        
        if schedule_data:
            today_schedule = self.api.get_today_schedule(schedule_data)
            
            if not today_schedule:
                await update.message.reply_text("🎉 На сегодня пар нет!")
                return
            
            message = f"📚 *Расписание на сегодня* ({datetime.now().strftime('%d.%m.%Y')})\n\n"
            
            for lesson in today_schedule:
                message += self.api.format_lesson_info(lesson) + "\n\n"
            
        else:
            message = "❌ Не удалось получить расписание"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def schedule_tomorrow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Расписание на завтра"""
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя: `/set_teacher 12345`", parse_mode='Markdown')
            return
        
        schedule_data = self.db.get_schedule(settings['teacher_url_id'])
        if not schedule_data:
            schedule_data = self.api.get_schedule(url_id=settings['teacher_url_id'])
            if schedule_data:
                self.db.save_schedule(settings['teacher_url_id'], schedule_data)
        
        if schedule_data:
            # Получаем завтрашний день
            tomorrow = datetime.now() + timedelta(days=1)
            tomorrow_en = tomorrow.strftime("%A")
            
            weekdays_ru = {
                'Monday': 'Понедельник',
                'Tuesday': 'Вторник', 
                'Wednesday': 'Среда',
                'Thursday': 'Четверг',
                'Friday': 'Пятница',
                'Saturday': 'Суббота',
                'Sunday': 'Воскресенье'
            }
            
            tomorrow_ru = weekdays_ru.get(tomorrow_en, tomorrow_en)
            parsed_data = self.api.parse_schedule_data(schedule_data)
            
            if parsed_data:
                tomorrow_schedule = parsed_data['schedules'].get(tomorrow_ru, [])
                
                if not tomorrow_schedule:
                    await update.message.reply_text("🎉 На завтра пар нет!")
                    return
                
                message = f"📚 *Расписание на завтра* ({tomorrow.strftime('%d.%m.%Y')})\n\n"
                
                for lesson in tomorrow_schedule:
                    message += self.api.format_lesson_info(lesson) + "\n\n"
                
                await update.message.reply_text(message, parse_mode='Markdown')
                return
        
        await update.message.reply_text("❌ Не удалось получить расписание")
    
    async def week_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Расписание на неделю"""
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя: `/set_teacher 12345`", parse_mode='Markdown')
            return
        
        schedule_data = self.db.get_schedule(settings['teacher_url_id'])
        if not schedule_data:
            schedule_data = self.api.get_schedule(url_id=settings['teacher_url_id'])
            if schedule_data:
                self.db.save_schedule(settings['teacher_url_id'], schedule_data)
        
        if schedule_data:
            message = self.api.get_week_schedule_text(schedule_data)
        else:
            message = "❌ Не удалось получить расписание"
        
        # Разбиваем длинное сообщение
        if len(message) > 4096:
            parts = [message[i:i+4096] for i in range(0, len(message), 4096)]
            for part in parts:
                await update.message.reply_text(part, parse_mode='Markdown')
        else:
            await update.message.reply_text(message, parse_mode='Markdown')
    
    async def next_lesson(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Следующая пара"""
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя: `/set_teacher 12345`", parse_mode='Markdown')
            return
        
        schedule_data = self.db.get_schedule(settings['teacher_url_id'])
        if not schedule_data:
            await update.message.reply_text("❌ Расписание не найдено")
            return
        
        next_lesson = self.api.get_next_lesson(schedule_data)
        
        if next_lesson:
            message = "➡️ *Следующая пара:*\n\n"
            message += self.api.format_lesson_info(next_lesson, "⏰")
            
            # Добавляем время до начала
            start_time = datetime.strptime(next_lesson['startLessonTime'], '%H:%M')
            now = datetime.now()
            time_left = start_time - now.replace(year=start_time.year, month=start_time.month, day=start_time.day)
            minutes_left = int(time_left.total_seconds() / 60)
            
            if minutes_left > 0:
                message += f"\n\n⏳ *До начала:* {minutes_left} минут"
            
        else:
            message = "🎉 *Пар больше нет сегодня!*"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def current_lesson(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Текущая пара"""
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя: `/set_teacher 12345`", parse_mode='Markdown')
            return
        
        schedule_data = self.db.get_schedule(settings['teacher_url_id'])
        if not schedule_data:
            await update.message.reply_text("❌ Расписание не найдено")
            return
        
        current_lesson = self.api.get_current_lesson(schedule_data)
        
        if current_lesson:
            message = "🎯 *Сейчас идет:*\n\n"
            message += self.api.format_lesson_info(current_lesson, "📚")
            
            # Добавляем время до конца пары
            end_time = datetime.strptime(current_lesson['endLessonTime'], '%H:%M')
            now = datetime.now()
            time_left = end_time - now.replace(year=end_time.year, month=end_time.month, day=end_time.day)
            minutes_left = int(time_left.total_seconds() / 60)
            
            if minutes_left > 0:
                message += f"\n\n⏳ *До конца:* {minutes_left} минут"
        
        else:
            message = "📝 *Сейчас пары нет*"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки уведомлений"""
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя: `/set_teacher 12345`", parse_mode='Markdown')
            return
        
        message = f"""
⚙️ *Настройки уведомлений*

*Преподаватель:* {settings['teacher_name']} ({settings['teacher_url_id']})

🔔 *Уведомления:* {'✅ ВКЛ' if settings['notifications_enabled'] else '❌ ВЫКЛ'}
🌅 *Утреннее расписание:* {'✅ ВКЛ' if settings['morning_schedule'] else '❌ ВЫКЛ'}  
⏰ *О начале пар:* {'✅ ВКЛ' if settings['lesson_notifications'] else '❌ ВЫКЛ'}
☕ *О переменах:* {'✅ ВКЛ' if settings['break_notifications'] else '❌ ВЫКЛ'}

*Команды:*
/enable_notifications - Включить все
/disable_notifications - Выключить все
/toggle_morning - Утренние уведомления
/toggle_lessons - Уведомления о парах
/toggle_breaks - Уведомления о переменах
        """
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def enable_notifications(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Включить все уведомления"""
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        if settings:
            self.db.update_teacher_setting(update.effective_chat.id, 'notifications_enabled', True)
            await update.message.reply_text("✅ Все уведомления включены")
    
    async def disable_notifications(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выключить все уведомления"""
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        if settings:
            self.db.update_teacher_setting(update.effective_chat.id, 'notifications_enabled', False)
            await update.message.reply_text("❌ Все уведомления выключены")
    
    async def toggle_morning(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Переключить утренние уведомления"""
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя")
            return
        
        new_value = not settings.get('morning_schedule', True)
        self.db.update_teacher_setting(update.effective_chat.id, 'morning_schedule', new_value)
        
        status = "включены" if new_value else "выключены"
        await update.message.reply_text(f"✅ Утренние уведомления {status}")
    
    async def toggle_lessons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Переключить уведомления о парах"""
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя")
            return
        
        new_value = not settings.get('lesson_notifications', True)
        self.db.update_teacher_setting(update.effective_chat.id, 'lesson_notifications', new_value)
        
        status = "включены" if new_value else "выключены"
        await update.message.reply_text(f"✅ Уведомления о парах {status}")
    
    async def toggle_breaks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Переключить уведомления о переменах"""
        settings = self.db.get_teacher_settings(update.effective_chat.id)
        
        if not settings:
            await update.message.reply_text("❌ Сначала установите преподавателя")
            return
        
        new_value = not settings.get('break_notifications', True)
        self.db.update_teacher_setting(update.effective_chat.id, 'break_notifications', new_value)
        
        status = "включены" if new_value else "выключены"
        await update.message.reply_text(f"✅ Уведомления о переменах {status}")
    
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика использования"""
        total = self.db.get_total_teachers()
        teachers = self.db.get_all_teachers()

        msg = f"📊 *Статистика бота*\n\n"
        msg += f"👨‍🏫 *Всего преподавателей:* {total}\n\n"

        if teachers:
            msg += "*Зарегистрированные преподаватели:*\n"
            for t in teachers:
                name = t.get('teacher_name', 'Неизвестно')
                dept = t.get('department', '')
                line = f"• {name}"
                if dept:
                    line += f" ({dept})"
                msg += line + "\n"

        await update.message.reply_text(msg, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Помощь"""
        help_text = """
🆘 *Помощь по боту для преподавателей*

*Основные команды:*
/schedule - Расписание на сегодня
/schedule_tomorrow - На завтра
/next_lesson - Следующая пара  
/current_lesson - Текущая пара
/week_schedule - На неделю
/set_teacher [id] - Установить преподавателя

*Настройки:*
/settings - Показать настройки
/enable_notifications - Включить уведомления
/disable_notifications - Выключить уведомления
/toggle_morning - Утренние уведомления
/toggle_lessons - Уведомления о парах
/toggle_breaks - Уведомления о переменах

*Авто-уведомления:*
• 📅 Ежедневное расписание в 7:00
• 🔔 За 10 минут до начала пары
• ⏰ За 5 минут до конца пары  
• 🎯 О начале пары
• ✅ О конце пары

*Поддержка:*
Для помощи обращайтесь к администратору.
        """
        
        await update.message.reply_text(help_text, parse_mode='Markdown')

def setup_bot():
    """Настройка бота"""
    global bot, application
    
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        print("❌ BOT_TOKEN not found in environment variables")
        return
    
    bot = Bot(token=bot_token)
    application = Application.builder().token(bot_token).updater(None).build()
    asyncio.run_coroutine_threadsafe(application.initialize(), loop).result()
    
    schedule_bot = ScheduleBot()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", schedule_bot.start))
    application.add_handler(CommandHandler("set_teacher", schedule_bot.set_teacher))
    application.add_handler(CommandHandler("schedule", schedule_bot.schedule_today))
    application.add_handler(CommandHandler("schedule_tomorrow", schedule_bot.schedule_tomorrow))
    application.add_handler(CommandHandler("next_lesson", schedule_bot.next_lesson))
    application.add_handler(CommandHandler("current_lesson", schedule_bot.current_lesson))
    application.add_handler(CommandHandler("week_schedule", schedule_bot.week_schedule))
    application.add_handler(CommandHandler("settings", schedule_bot.settings))
    application.add_handler(CommandHandler("enable_notifications", schedule_bot.enable_notifications))
    application.add_handler(CommandHandler("disable_notifications", schedule_bot.disable_notifications))
    application.add_handler(CommandHandler("toggle_morning", schedule_bot.toggle_morning))
    application.add_handler(CommandHandler("toggle_lessons", schedule_bot.toggle_lessons))
    application.add_handler(CommandHandler("toggle_breaks", schedule_bot.toggle_breaks))
    application.add_handler(CommandHandler("stats", schedule_bot.stats))
    application.add_handler(CommandHandler("help", schedule_bot.help_command))

# Маршруты для Flask
@app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook для Telegram"""
    try:
        update = Update.de_json(request.get_json(), application.bot)
        asyncio.run_coroutine_threadsafe(application.process_update(update), loop).result()
        return 'OK'
    except Exception as e:
        import traceback
        print(f"Webhook error: {e}\n{traceback.format_exc()}")
        return f'Error: {e}', 500

@app.route('/schedule', methods=['GET'])
def schedule_route():
    """Проверка работы бота"""
    return jsonify({"status": "Bot is running", "timestamp": datetime.now().isoformat()})

@app.route('/')
def home():
    """Главная страница"""
    return jsonify({
        "name": "BSUIR Schedule Bot",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    })

# Инициализация при запуске
setup_bot()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)
