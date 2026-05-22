from flask import Flask, request, jsonify
import os
import asyncio
from datetime import datetime, timedelta
import schedule
import time
import threading

from utils.database import Database
from utils.api_client import BsuirAPI
from telegram import Bot

app = Flask(__name__)

db = Database()
api = BsuirAPI()
bot = Bot(token=os.getenv('BOT_TOKEN'))

class NotificationScheduler:
    def __init__(self):
        self.db = db
        self.api = api
        self.bot = bot
    
    async def send_morning_schedule(self):
        """Отправить утреннее расписание"""
        try:
            print("🕔 Отправка утреннего расписания...")
            active_teachers = self.db.get_active_teachers()
            
            for teacher_settings in active_teachers:
                if not teacher_settings.get('morning_schedule', True):
                    continue
                
                chat_id = teacher_settings['telegram_chat_id']
                teacher_id = teacher_settings['teacher_url_id']
                
                # Получаем актуальное расписание
                schedule_data = self.api.get_schedule(url_id=teacher_id)
                if schedule_data:
                    self.db.save_schedule(teacher_id, schedule_data)
                    
                    today_schedule = self.api.get_today_schedule(schedule_data)
                    
                    if today_schedule:
                        message = f"🌅 *Доброе утро!* \n\n📚 *Расписание на сегодня:*\n\n"
                        
                        for lesson in today_schedule:
                            message += self.api.format_lesson_info(lesson) + "\n\n"
                        
                        # Добавляем информацию о первой паре
                        first_lesson = today_schedule[0] if today_schedule else None
                        if first_lesson:
                            message += f"⏰ *Первая пара:* {first_lesson['startLessonTime']}\n"
                            message += f"📖 {first_lesson['subject']}"
                    
                    else:
                        message = "🌅 *Доброе утро!* \n\n🎉 *Сегодня пар нет!* Отличный день для отдыха! 😊"
                    
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode='Markdown'
                    )
                    
                    self.db.log_notification(chat_id, 'morning_schedule', message)
                    print(f"✅ Отправлено утреннее расписание для преподавателя {teacher_id}")
                    
        except Exception as e:
            print(f"❌ Ошибка в утреннем расписании: {e}")
    
    async def check_lessons(self):
        """Проверить расписание и отправить уведомления"""
        try:
            active_teachers = self.db.get_active_teachers()
            now = datetime.now()
            
            print(f"🔍 Проверка пар для {len(active_teachers)} преподавателей...")
            
            for teacher_settings in active_teachers:
                if not teacher_settings.get('lesson_notifications', True):
                    continue
                
                chat_id = teacher_settings['telegram_chat_id']
                teacher_id = teacher_settings['teacher_url_id']
                
                schedule_data = self.db.get_schedule(teacher_id)
                if not schedule_data:
                    # Пробуем обновить расписание
                    schedule_data = self.api.get_schedule(url_id=teacher_id)
                    if schedule_data:
                        self.db.save_schedule(teacher_id, schedule_data)
                    else:
                        continue
                
                lessons = self.api.get_lessons_for_time_check(schedule_data)
                
                for lesson in lessons:
                    try:
                        start_time_str = lesson.get('startLessonTime', '')
                        end_time_str = lesson.get('endLessonTime', '')
                        
                        if not start_time_str or not end_time_str:
                            continue
                            
                        start_time = datetime.strptime(start_time_str, '%H:%M').time()
                        end_time = datetime.strptime(end_time_str, '%H:%M').time()
                        current_time = now.time()
                        
                        # Уведомление за 10 минут до начала пары
                        start_datetime = datetime.combine(now.date(), start_time)
                        notification_time = (start_datetime - timedelta(minutes=10)).time()
                        
                        if self.is_time_match(current_time, notification_time):
                            message = "🔔 *Скоро пара!*\n\n"
                            message += self.api.format_lesson_info(lesson, "⏰")
                            
                            await self.bot.send_message(
                                chat_id=chat_id,
                                text=message,
                                parse_mode='Markdown'
                            )
                            self.db.log_notification(chat_id, 'lesson_reminder', message)
                            print(f"✅ Уведомление о начале пары для преподавателя {teacher_id}")
                        
                        # Уведомление за 5 минут до конца пары
                        end_datetime = datetime.combine(now.date(), end_time)
                        end_notification_time = (end_datetime - timedelta(minutes=5)).time()
                        
                        if self.is_time_match(current_time, end_notification_time):
                            message = "⏳ *До конца пары 5 минут!*\n\n"
                            message += self.api.format_lesson_info(lesson, "📚")
                            
                            await self.bot.send_message(
                                chat_id=chat_id,
                                text=message,
                                parse_mode='Markdown'
                            )
                            self.db.log_notification(chat_id, 'lesson_end_reminder', message)
                            print(f"✅ Уведомление о конце пары для преподавателя {teacher_id}")
                        
                        # Уведомление о начале пары (точно в время)
                        if self.is_time_match(current_time, start_time):
                            message = "🎯 *Пара началась!*\n\n"
                            message += self.api.format_lesson_info(lesson, "📚")
                            
                            await self.bot.send_message(
                                chat_id=chat_id,
                                text=message,
                                parse_mode='Markdown'
                            )
                            self.db.log_notification(chat_id, 'lesson_start', message)
                            print(f"✅ Уведомление о начале пары для преподавателя {teacher_id}")
                        
                        # Уведомление о конце пары (точно в время)
                        if self.is_time_match(current_time, end_time):
                            message = "✅ *Пара окончена!*\n\n"
                            message += self.api.format_lesson_info(lesson, "📚")
                            
                            next_lesson = self.api.get_next_lesson(schedule_data)
                            if next_lesson and next_lesson != lesson:
                                message += f"\n\n➡️ *Следующая пара:*\n"
                                message += self.api.format_lesson_info(next_lesson, "⏰")
                            else:
                                message += "\n\n🎉 *Пар больше нет сегодня!*"
                            
                            await self.bot.send_message(
                                chat_id=chat_id,
                                text=message,
                                parse_mode='Markdown'
                            )
                            self.db.log_notification(chat_id, 'lesson_end', message)
                            print(f"✅ Уведомление о конце пары для преподавателя {teacher_id}")
                            
                    except Exception as e:
                        print(f"❌ Ошибка обработки пары: {e}")
                        continue
                        
        except Exception as e:
            print(f"❌ Ошибка в проверке пар: {e}")
    
    async def update_schedules(self):
        """Обновить расписание всех активных преподавателей"""
        try:
            print("🔄 Обновление расписаний...")
            active_teachers = self.db.get_active_teachers()
            
            for teacher_settings in active_teachers:
                teacher_id = teacher_settings['teacher_id']
                
                schedule_data = self.api.get_schedule(url_id=teacher_id)
                if schedule_data:
                    self.db.save_schedule(teacher_id, schedule_data)
                    print(f"✅ Обновлено расписание для преподавателя {teacher_id}")
                else:
                    print(f"❌ Не удалось обновить расписание для преподавателя {teacher_id}")
            
            print(f"✅ Обновлено расписание для {len(active_teachers)} преподавателей")
            
        except Exception as e:
            print(f"❌ Ошибка обновления расписаний: {e}")
    
    async def send_test_notification(self):
        """Тестовое уведомление"""
        try:
            admin_chat_id = os.getenv('ADMIN_CHAT_ID')
            if admin_chat_id:
                await self.bot.send_message(
                    chat_id=admin_chat_id,
                    text=f"🤖 Бот работает! Проверка {datetime.now().strftime('%H:%M')}"
                )
        except Exception as e:
            print(f"❌ Ошибка тестового уведомления: {e}")

def run_scheduler():
    """Запуск планировщика"""
    scheduler = NotificationScheduler()
    
    # Настройка расписания
    schedule.every().day.at("07:00").do(lambda: asyncio.run(scheduler.send_morning_schedule()))
    schedule.every(1).minutes.do(lambda: asyncio.run(scheduler.check_lessons()))
    schedule.every().day.at("00:00").do(lambda: asyncio.run(scheduler.update_schedules()))
    schedule.every(6).hours.do(lambda: asyncio.run(scheduler.update_schedules()))
    
    print("🚀 Планировщик запущен")
    
    while True:
        schedule.run_pending()
        time.sleep(30)  # Проверяем каждые 30 секунд

@app.route('/cron', methods=['GET', 'POST'])
def cron_handler():
    """Обработчик для Vercel Cron"""
    try:
        # Запускаем одну итерацию проверок
        scheduler = NotificationScheduler()
        asyncio.run(scheduler.check_lessons())
        
        return jsonify({"status": "Cron executed successfully", "timestamp": datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка здоровья сервиса"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/test', methods=['GET'])
def test_handler():
    """Тестовый маршрут"""
    try:
        scheduler = NotificationScheduler()
        asyncio.run(scheduler.send_test_notification())
        return jsonify({"status": "Test notification sent"})
    except Exception as e:
        return jsonify({"status": "Error", "error": str(e)}), 500

# Запуск планировщика в отдельном потоке
def start_scheduler():
    time.sleep(10)  # Ждем инициализации
    run_scheduler()

if __name__ == '__main__':
    # Запускаем планировщик в отдельном потоке
    scheduler_thread = threading.Thread(target=start_scheduler, daemon=True)
    scheduler_thread.start()
    
    app.run(host='0.0.0.0', port=3001)