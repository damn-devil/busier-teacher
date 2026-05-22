-- Таблица преподавателей
CREATE TABLE IF NOT EXISTS teachers (
  telegram_chat_id BIGINT PRIMARY KEY,
  teacher_url_id TEXT NOT NULL,
  teacher_name TEXT,
  department TEXT,
  position TEXT,
  notifications_enabled BOOLEAN DEFAULT TRUE,
  morning_schedule BOOLEAN DEFAULT TRUE,
  lesson_notifications BOOLEAN DEFAULT TRUE,
  break_notifications BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Таблица кеша расписаний
CREATE TABLE IF NOT EXISTS teacher_schedules (
  teacher_url_id TEXT PRIMARY KEY,
  schedule_data JSONB,
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Индекс для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_teachers_url_id ON teachers (teacher_url_id);
