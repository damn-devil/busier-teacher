import requests
import json
from datetime import datetime, timedelta
import os

class BsuirAPI:
    def __init__(self):
        self.base_url = "https://iis.bsuir.by/api/v1"
    
    def get_schedule(self, url_id=None, group_number=None):
        """Получить расписание для преподавателя или группы"""
        try:
            if url_id:
                url = f"{self.base_url}/employees/schedule/{url_id}"
            elif group_number:
                url = f"{self.base_url}/schedule?studentGroup={group_number}"
            else:
                raise ValueError("Either url_id or group_number must be provided")
                
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"API Error: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error getting schedule: {e}")
            return None
    
    def parse_schedule_data(self, schedule_data):
        """Парсинг данных расписания"""
        if not schedule_data:
            return None
        
        try:
            # Check if it's teacher schedule (has employeeDto)
            if 'employeeDto' in schedule_data and schedule_data['employeeDto'] is not None:
                employee_info = schedule_data.get('employeeDto', {})
                schedules = schedule_data.get('schedules', {})
                
                # Extract teacher name
                first_name = employee_info.get('firstName', '')
                last_name = employee_info.get('lastName', '')
                middle_name = employee_info.get('middleName', '')
                full_name = f"{last_name} {first_name} {middle_name}".strip()
                if not full_name:
                    full_name = "Преподаватель"
                
                return {
                    'group_name': full_name,  # Using group_name field for teacher name
                    'faculty': employee_info.get('rank', 'Неизвестно'),  # Using faculty for rank/position
                    'course': employee_info.get('degreeAbbrev', ''),  # Using course for degree
                    'schedules': schedules
                }
            # Check if it's group schedule (has studentGroupDto)
            elif 'studentGroupDto' in schedule_data and schedule_data['studentGroupDto'] is not None:
                group_info = schedule_data.get('studentGroupDto', {})
                schedules = schedule_data.get('schedules', {})
                
                return {
                    'group_name': group_info.get('name', 'Неизвестно'),
                    'faculty': group_info.get('facultyAbbrev', 'Неизвестно'),
                    'course': group_info.get('course', 'Неизвестно'),
                    'schedules': schedules
                }
            # Fallback to old structure (studentGroupDoc) for backward compatibility
            else:
                group_info = schedule_data.get('studentGroupDoc', {})
                schedules = schedule_data.get('schedules', {})
                
                return {
                    'group_name': group_info.get('name', 'Неизвестно'),
                    'faculty': group_info.get('facultyAbbrev', 'Неизвестно'),
                    'course': group_info.get('course', 'Неизвестно'),
                    'schedules': schedules
                }
        except Exception as e:
            print(f"Error parsing schedule: {e}")
            return None
    
    def get_today_schedule(self, schedule_data):
        """Получить расписание на сегодня"""
        parsed = self.parse_schedule_data(schedule_data)
        if not parsed:
            return None
            
        weekdays_ru = {
            'Monday': 'Понедельник',
            'Tuesday': 'Вторник', 
            'Wednesday': 'Среда',
            'Thursday': 'Четверг',
            'Friday': 'Пятница',
            'Saturday': 'Суббота',
            'Sunday': 'Воскресенье'
        }
        
        today_en = datetime.now().strftime("%A")
        today_ru = weekdays_ru.get(today_en, today_en)
        
        return parsed['schedules'].get(today_ru, [])
    
    def get_current_lesson(self, schedule_data):
        """Получить текущую пару"""
        today_schedule = self.get_today_schedule(schedule_data)
        if not today_schedule:
            return None
            
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        for lesson in today_schedule:
            start_time = lesson.get('startLessonTime', '')
            end_time = lesson.get('endLessonTime', '')
            
            if start_time <= current_time <= end_time:
                return lesson
        
        return None
    
    def get_next_lesson(self, schedule_data):
        """Получить следующую пару"""
        today_schedule = self.get_today_schedule(schedule_data)
        if not today_schedule:
            return None
            
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        for lesson in today_schedule:
            start_time = lesson.get('startLessonTime', '')
            if start_time > current_time:
                return lesson
        
        return None
    
    def get_lessons_for_time_check(self, schedule_data):
        """Получить все пары для проверки времени"""
        today_schedule = self.get_today_schedule(schedule_data)
        if not today_schedule:
            return []
            
        return today_schedule
    
    def format_lesson_info(self, lesson, prefix="📚"):
        """Форматировать информацию о паре"""
        if not lesson:
            return ""
            
        lesson_num = lesson.get('lessonNumber', '?')
        start_time = lesson.get('startLessonTime', '?:?')
        end_time = lesson.get('endLessonTime', '?:?')
        subject = lesson.get('subject', 'Не указано')
        lesson_type = lesson.get('lessonType', '')
        auditory = lesson.get('auditory', [''])[0] if lesson.get('auditory') else 'Не указана'
        
        employees = lesson.get('employee', [])
        employee_name = employees[0].get('fullName', 'Не указан') if employees else 'Не указан'
        
        message = f"{prefix} Пара {lesson_num}. {start_time}-{end_time}\n"
        message += f"📖 {subject}\n"
        if lesson_type:
            message += f"📝 {lesson_type}\n"
        message += f"👨‍🏫 {employee_name}\n"
        message += f"📍 {auditory}"
        
        return message
    
    def get_week_schedule_text(self, schedule_data):
        """Получить расписание на неделю в текстовом формате"""
        parsed = self.parse_schedule_data(schedule_data)
        if not parsed:
            return "❌ Ошибка обработки расписания"
        
        message = f"📅 Расписание группы {parsed['group_name']} на неделю\n"
        message += f"🏛 {parsed['faculty']} | {parsed['course']} курс\n\n"
        
        weekdays_order = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
        
        for day in weekdays_order:
            day_schedule = parsed['schedules'].get(day, [])
            message += f"**{day}:**\n"
            
            if not day_schedule:
                message += "    Пар нет 🎉\n"
            else:
                for lesson in day_schedule:
                    lesson_num = lesson.get('lessonNumber', '?')
                    start_time = lesson.get('startLessonTime', '?:?')
                    subject = lesson.get('subject', 'Не указано')
                    auditory = lesson.get('auditory', [''])[0] if lesson.get('auditory') else ''
                    
                    message += f"    {lesson_num}. {start_time} - {subject}"
                    if auditory:
                        message += f" ({auditory})"
                    message += "\n"
            
            message += "\n"
        
        return message