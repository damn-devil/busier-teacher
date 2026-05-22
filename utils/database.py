import os
import json
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


class Database:
    def _request(self, method, table, params=None, data=None):
        url = f"{SUPABASE_URL}/rest/v1/{table}"
        headers = SUPABASE_HEADERS.copy()
        if method == "PATCH":
            headers["Prefer"] = "return=minimal"
        try:
            resp = requests.request(method, url, headers=headers, params=params, json=data, timeout=15)
            if resp.status_code >= 400:
                print(f"Supabase error {resp.status_code}: {resp.text}")
            return resp
        except requests.RequestException as e:
            print(f"Supabase request failed: {e}")
            return None

    def save_teacher_settings(self, chat_id: int, teacher_url_id: str,
                              teacher_name: str = None,
                              department: str = None,
                              position: str = None,
                              username: str = None):
        self._request("POST", "teachers", params={"on_conflict": "telegram_chat_id"}, data=[{
            "telegram_chat_id": chat_id,
            "teacher_url_id": teacher_url_id,
            "teacher_name": teacher_name,
            "department": department,
            "position": position,
            "username": username,
        }])

    def get_teacher_settings(self, chat_id: int):
        resp = self._request("GET", "teachers", params={
            "telegram_chat_id": f"eq.{chat_id}",
            "select": "*",
        })
        if resp is None:
            return None
        rows = resp.json() if resp.status_code == 200 else []
        data = rows[0] if rows else None
        if data:
            data.setdefault("notifications_enabled", True)
            data.setdefault("morning_schedule", True)
            data.setdefault("lesson_notifications", True)
            data.setdefault("break_notifications", True)
        return data

    def update_teacher_setting(self, chat_id: int, setting: str, value: bool):
        self._request("PATCH", "teachers", params={
            "telegram_chat_id": f"eq.{chat_id}",
        }, data={setting: value})

    def get_total_teachers(self) -> int:
        resp = self._request("GET", "teachers", params={"select": "telegram_chat_id"})
        if resp is None:
            return 0
        return len(resp.json()) if resp.status_code == 200 else 0

    def get_all_teachers(self):
        resp = self._request("GET", "teachers", params={
            "select": "telegram_chat_id,teacher_url_id,teacher_name,department,position,username",
        })
        if resp is None:
            return []
        return resp.json() if resp.status_code == 200 else []

    get_active_teachers = get_all_teachers

    def save_schedule(self, teacher_url_id: str, schedule_data: dict):
        self._request("POST", "teacher_schedules", params={"on_conflict": "teacher_url_id"}, data=[{
            "teacher_url_id": teacher_url_id,
            "schedule_data": schedule_data,
            "updated_at": datetime.utcnow().isoformat(),
        }])

    def get_schedule(self, teacher_url_id: str):
        resp = self._request("GET", "teacher_schedules", params={
            "teacher_url_id": f"eq.{teacher_url_id}",
            "select": "schedule_data",
        })
        if resp is None:
            return None
        rows = resp.json() if resp.status_code == 200 else []
        return rows[0]["schedule_data"] if rows else None

    def log_notification(self, chat_id: int, ntype: str, message: str):
        pass
