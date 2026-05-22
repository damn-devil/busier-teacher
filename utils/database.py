import os
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self):
        url: str = os.getenv("SUPABASE_URL")
        key: str = os.getenv("SUPABASE_ANON_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL и SUPABASE_ANON_KEY должны быть заданы")
        self.supabase: Client = create_client(url, key)

    # ------------------ Настройки преподавателя ------------------
    def save_teacher_settings(self, chat_id: int, teacher_url_id: str,
                              teacher_name: str = None,
                              department: str = None,
                              position: str = None):
        """Создать или обновить запись преподавателя."""
        data = {
            "telegram_chat_id": chat_id,
            "teacher_url_id": teacher_url_id,
            "teacher_name": teacher_name,
            "department": department,
            "position": position,
        }
        self.supabase.table("teachers").upsert(
            data,
            on_conflict="telegram_chat_id"
        ).execute()

    def get_teacher_settings(self, chat_id: int):
        resp = (
            self.supabase.table("teachers")
            .select("*")
            .eq("telegram_chat_id", chat_id)
            .single()
            .execute()
        )
        data = resp.data if resp.data else None
        if data:
            data.setdefault("notifications_enabled", True)
            data.setdefault("morning_schedule", True)
            data.setdefault("lesson_notifications", True)
            data.setdefault("break_notifications", True)
        return data

    def update_teacher_setting(self, chat_id: int, setting: str, value: bool):
        self.supabase.table("teachers").update({setting: value}).eq(
            "telegram_chat_id", chat_id
        ).execute()

    # ------------------ Статистика ------------------
    def get_total_teachers(self) -> int:
        resp = self.supabase.table("teachers").select("telegram_chat_id", count="exact").execute()
        return resp.count if hasattr(resp, 'count') else len(resp.data or [])

    def get_all_teachers(self):
        resp = (
            self.supabase.table("teachers")
            .select("telegram_chat_id, teacher_url_id, teacher_name, department, position")
            .execute()
        )
        return resp.data or []

    get_active_teachers = get_all_teachers

    # ------------------ Расписание ------------------
    def save_schedule(self, teacher_url_id: str, schedule_data: dict):
        self.supabase.table("teacher_schedules").upsert(
            {
                "teacher_url_id": teacher_url_id,
                "schedule_data": schedule_data,
                "updated_at": datetime.utcnow().isoformat()
            },
            on_conflict="teacher_url_id"
        ).execute()

    def get_schedule(self, teacher_url_id: str):
        resp = (
            self.supabase.table("teacher_schedules")
            .select("schedule_data")
            .eq("teacher_url_id", teacher_url_id)
            .single()
            .execute()
        )
        return resp.data["schedule_data"] if resp.data else None

    def log_notification(self, chat_id: int, ntype: str, message: str):
        pass