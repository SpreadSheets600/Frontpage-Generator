CREATE TABLE IF NOT EXISTS semesters (
  id INTEGER PRIMARY KEY,
  label TEXT NOT NULL,
  order_index INTEGER NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS streams (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  short_code TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS subjects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  code TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subject_offerings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id INTEGER NOT NULL,
  semester_id INTEGER NOT NULL,
  UNIQUE(subject_id, semester_id),
  FOREIGN KEY (subject_id) REFERENCES subjects(id),
  FOREIGN KEY (semester_id) REFERENCES semesters(id)
);

CREATE TABLE IF NOT EXISTS generation_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  student_name TEXT NOT NULL,
  roll TEXT NOT NULL,
  registration TEXT NOT NULL,
  subject_name TEXT NOT NULL,
  subject_code TEXT NOT NULL,
  stream_label TEXT NOT NULL,
  semester_label TEXT NOT NULL
);

INSERT OR IGNORE INTO semesters (id, label, order_index) VALUES
  (1, '1st', 1),
  (2, '2nd', 2),
  (3, '3rd', 3),
  (4, '4th', 4),
  (5, '5th', 5),
  (6, '6th', 6),
  (7, '7th', 7),
  (8, '8th', 8);
