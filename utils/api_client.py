import requests
import json
from datetime import datetime, timedelta
import os
import pytz

MINSK_TZ = pytz.timezone("Europe/Minsk")

WEEKDAYS_MAP = {
    'Monday': 'Понедельник',
    'Tuesday': 'Вторник',
    'Wednesday': 'Среда',
    'Thursday': 'Четверг',
    'Friday': 'Пятница',
    'Saturday': 'Суббота',
    'Sunday': 'Воскресенье',
}

WEEKDAYS_ORDER = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']

LESSON_TYPES = {
    "ЛР": "Лабораторная",
    "ЛК": "Лекция",
    "ПЗ": "Практическое",
    "ЭК": "Экзамен",
    "КР": "Курсовая",
    "КН": "Консультация",
    "ЗЧ": "Зачёт",
}


class BsuirAPI:
    def __init__(self):
        self.base_url = "https://iis.bsuir.by/api/v1"
        self._current_week = None
        self._current_week_ts = 0

    def get_schedule(self, url_id=None, group_number=None):
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

    def get_current_week(self):
        now = datetime.now(MINSK_TZ).timestamp()
        if self._current_week is not None and now - self._current_week_ts < 3600:
            return self._current_week
        try:
            resp = requests.get(f"{self.base_url}/schedule/current-week", timeout=10)
            if resp.status_code == 200:
                val = resp.text.strip()
                self._current_week = int(val)
                self._current_week_ts = now
                return self._current_week
        except Exception as e:
            print(f"Error getting current week: {e}")
        return 1

    def get_auditories(self):
        try:
            resp = requests.get(f"{self.base_url}/auditories", timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"Error getting auditories: {e}")
        return []

    @staticmethod
    def _filter_by_week(lessons, current_week):
        if not lessons:
            return []
        result = []
        for lesson in lessons:
            wn = lesson.get("weekNumber")
            if wn is None or len(wn) == 0 or current_week in wn:
                result.append(lesson)
        return result

    def parse_schedule_data(self, schedule_data):
        if not schedule_data:
            return None

        try:
            if 'employeeDto' in schedule_data and schedule_data['employeeDto'] is not None:
                employee_info = schedule_data.get('employeeDto', {})
                schedules = schedule_data.get('schedules', {})

                first_name = employee_info.get('firstName', '')
                last_name = employee_info.get('lastName', '')
                middle_name = employee_info.get('middleName', '')
                full_name = f"{last_name} {first_name} {middle_name}".strip()
                if not full_name:
                    full_name = "Преподаватель"

                return {
                    'group_name': full_name,
                    'faculty': employee_info.get('rank', 'Неизвестно'),
                    'course': employee_info.get('degreeAbbrev', ''),
                    'schedules': schedules,
                }
            elif 'studentGroupDto' in schedule_data and schedule_data['studentGroupDto'] is not None:
                group_info = schedule_data.get('studentGroupDto', {})
                schedules = schedule_data.get('schedules', {})

                return {
                    'group_name': group_info.get('name', 'Неизвестно'),
                    'faculty': group_info.get('facultyAbbrev', 'Неизвестно'),
                    'course': group_info.get('course', 'Неизвестно'),
                    'schedules': schedules,
                }
            else:
                group_info = schedule_data.get('studentGroupDoc', {})
                schedules = schedule_data.get('schedules', {})

                return {
                    'group_name': group_info.get('name', 'Неизвестно'),
                    'faculty': group_info.get('facultyAbbrev', 'Неизвестно'),
                    'course': group_info.get('course', 'Неизвестно'),
                    'schedules': schedules,
                }
        except Exception as e:
            print(f"Error parsing schedule: {e}")
            return None

    def _today_name_ru(self):
        return WEEKDAYS_MAP.get(datetime.now(MINSK_TZ).strftime("%A"), "")

    def _day_lessons(self, schedule_data, day_ru):
        parsed = self.parse_schedule_data(schedule_data)
        if not parsed:
            return None
        return parsed['schedules'].get(day_ru, [])

    def _day_lessons_filtered(self, schedule_data, day_ru):
        lessons = self._day_lessons(schedule_data, day_ru)
        if not lessons:
            return []
        cw = self.get_current_week()
        return self._filter_by_week(lessons, cw)

    def get_today_schedule(self, schedule_data):
        return self._day_lessons_filtered(schedule_data, self._today_name_ru())

    def get_tomorrow_schedule(self, schedule_data):
        today_ru = self._today_name_ru()
        try:
            idx = WEEKDAYS_ORDER.index(today_ru)
        except ValueError:
            return []
        tomorrow_ru = WEEKDAYS_ORDER[(idx + 1) % len(WEEKDAYS_ORDER)]
        return self._day_lessons_filtered(schedule_data, tomorrow_ru)

    def get_current_lesson(self, schedule_data):
        today_schedule = self.get_today_schedule(schedule_data)
        if not today_schedule:
            return None

        now_time = datetime.now(MINSK_TZ).strftime("%H:%M")

        for lesson in today_schedule:
            start = lesson.get('startLessonTime', '')
            end = lesson.get('endLessonTime', '')
            if start <= now_time <= end:
                return lesson
        return None

    def get_next_lesson(self, schedule_data):
        today_schedule = self.get_today_schedule(schedule_data)
        if not today_schedule:
            return None

        now_time = datetime.now(MINSK_TZ).strftime("%H:%M")

        for lesson in today_schedule:
            start = lesson.get('startLessonTime', '')
            if start > now_time:
                return lesson
        return None

    def get_lessons_for_time_check(self, schedule_data):
        today_schedule = self.get_today_schedule(schedule_data)
        return today_schedule or []

    @staticmethod
    def format_lesson_info(lesson, lesson_number=None, prefix="📚"):
        if not lesson:
            return ""

        start_time = lesson.get('startLessonTime', '?:?')
        end_time = lesson.get('endLessonTime', '?:?')
        subject = lesson.get('subject', 'Не указано')

        less_type = lesson.get('lessonTypeAbbrev', '')
        less_type_full = LESSON_TYPES.get(less_type, less_type)

        auditories = lesson.get('auditories', [])
        auditory = ", ".join(auditories) if auditories else 'Не указана'

        groups = lesson.get('studentGroups', [])
        group_names = ", ".join(g.get("name", "") for g in groups) if groups else ""

        num = f"{lesson_number}. " if lesson_number else ""
        message = f"{prefix} Пара {num}{start_time}–{end_time}\n"
        message += f"📖 {subject}"
        if less_type_full:
            message += f" ({less_type_full})"
        message += "\n"
        if group_names:
            message += f"👥 Группа: {group_names}\n"
        message += f"📍 {auditory}"
        return message

    def get_week_schedule_text(self, schedule_data):
        parsed = self.parse_schedule_data(schedule_data)
        if not parsed:
            return "❌ Ошибка обработки расписания"

        cw = self.get_current_week()

        parts = [f"📅 Расписание группы {parsed['group_name']} на неделю"]
        course_str = f" | {parsed['course']} курс" if parsed.get('course') else ""
        parts.append(f"🏛 {parsed['faculty']}{course_str}")
        parts.append(f"📌 {cw}-я неделя")

        for day in WEEKDAYS_ORDER:
            day_schedule = parsed['schedules'].get(day, [])
            day_schedule = self._filter_by_week(day_schedule, cw)

            parts.append("------------------------------")
            parts.append(f"{day}:")

            if not day_schedule:
                parts.append("Пар нет 🎉")
            else:
                for i, lesson in enumerate(day_schedule, 1):
                    start_time = lesson.get('startLessonTime', '?:?')
                    subject = lesson.get('subject', 'Не указано')

                    less_type = lesson.get('lessonTypeAbbrev', '')
                    less_type_full = LESSON_TYPES.get(less_type, less_type)

                    auditories = lesson.get('auditories', [])
                    auditory = ", ".join(auditories) if auditories else ''

                    groups = lesson.get('studentGroups', [])
                    group_names = ", ".join(g.get("name", "") for g in groups) if groups else ""

                    line = f"{i}. {start_time} - {subject}"
                    if less_type_full:
                        line += f" ({less_type_full})"
                    parts.append(line)
                    if auditory:
                        parts.append(auditory)
                    if group_names:
                        parts.append(f"👥 {group_names}")

        return "\n".join(parts)
