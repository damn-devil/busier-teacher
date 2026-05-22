import os
import json
from datetime import datetime
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self):
        self.conn = psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")
        self.conn.autocommit = True

    def _dict_row(self, row, columns):
        if not row:
            return None
        return dict(zip(columns, row))

    def save_teacher_settings(self, chat_id: int, teacher_url_id: str,
                              teacher_name: str = None,
                              department: str = None,
                              position: str = None):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO teachers (telegram_chat_id, teacher_url_id, teacher_name, department, position, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (telegram_chat_id) DO UPDATE SET
                    teacher_url_id = EXCLUDED.teacher_url_id,
                    teacher_name = EXCLUDED.teacher_name,
                    department = EXCLUDED.department,
                    position = EXCLUDED.position,
                    updated_at = NOW()
            """, (chat_id, teacher_url_id, teacher_name, department, position))

    def get_teacher_settings(self, chat_id: int):
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM teachers WHERE telegram_chat_id = %s", (chat_id,))
            columns = [desc[0] for desc in cur.description]
            data = self._dict_row(cur.fetchone(), columns)
        if data:
            data.setdefault("notifications_enabled", True)
            data.setdefault("morning_schedule", True)
            data.setdefault("lesson_notifications", True)
            data.setdefault("break_notifications", True)
        return data

    def update_teacher_setting(self, chat_id: int, setting: str, value: bool):
        with self.conn.cursor() as cur:
            cur.execute(
                f"UPDATE teachers SET {setting} = %s, updated_at = NOW() WHERE telegram_chat_id = %s",
                (value, chat_id)
            )

    def get_total_teachers(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM teachers")
            return cur.fetchone()[0]

    def get_all_teachers(self):
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT telegram_chat_id, teacher_url_id, teacher_name, department, position FROM teachers"
            )
            return [dict(r) for r in cur.fetchall()]

    get_active_teachers = get_all_teachers

    def save_schedule(self, teacher_url_id: str, schedule_data: dict):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO teacher_schedules (teacher_url_id, schedule_data, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (teacher_url_id) DO UPDATE SET
                    schedule_data = EXCLUDED.schedule_data,
                    updated_at = EXCLUDED.updated_at
            """, (teacher_url_id, json.dumps(schedule_data), datetime.utcnow().isoformat()))

    def get_schedule(self, teacher_url_id: str):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT schedule_data FROM teacher_schedules WHERE teacher_url_id = %s",
                (teacher_url_id,)
            )
            row = cur.fetchone()
        return row[0] if row else None

    def log_notification(self, chat_id: int, ntype: str, message: str):
        pass

    def close(self):
        self.conn.close()
