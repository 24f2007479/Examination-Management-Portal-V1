import os
import sqlite3
from flask import g
from werkzeug.security import generate_password_hash

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'emp.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
 id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
 password TEXT NOT NULL, role TEXT NOT NULL, status TEXT DEFAULT 'Active',
 department TEXT, contact TEXT, roll_no TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS courses(
 id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 description TEXT, credits INTEGER DEFAULT 3, status TEXT DEFAULT 'Active');
CREATE TABLE IF NOT EXISTS exams(
 id INTEGER PRIMARY KEY AUTOINCREMENT, course_id INTEGER NOT NULL REFERENCES courses(id),
 name TEXT NOT NULL, exam_type TEXT, duration INTEGER, max_marks INTEGER,
 slot_start TEXT, slot_end TEXT, book_start TEXT, book_end TEXT,
 status TEXT DEFAULT 'Draft', venue TEXT, instructions TEXT, published INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS rubrics(
 id INTEGER PRIMARY KEY AUTOINCREMENT, exam_id INTEGER NOT NULL REFERENCES exams(id),
 criterion TEXT NOT NULL, max_marks REAL NOT NULL, weightage REAL DEFAULT 0, description TEXT);
CREATE TABLE IF NOT EXISTS exam_examiners(
 exam_id INTEGER NOT NULL REFERENCES exams(id), examiner_id INTEGER NOT NULL REFERENCES users(id),
 PRIMARY KEY(exam_id, examiner_id));
CREATE TABLE IF NOT EXISTS slots(
 id INTEGER PRIMARY KEY AUTOINCREMENT, exam_id INTEGER NOT NULL REFERENCES exams(id),
 examiner_id INTEGER NOT NULL REFERENCES users(id), date TEXT, start_time TEXT, end_time TEXT,
 capacity INTEGER NOT NULL, available INTEGER NOT NULL, status TEXT DEFAULT 'Available', location TEXT);
CREATE TABLE IF NOT EXISTS bookings(
 id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL REFERENCES users(id),
 slot_id INTEGER NOT NULL REFERENCES slots(id), booking_date TEXT DEFAULT CURRENT_TIMESTAMP,
 status TEXT DEFAULT 'Booked', marks REAL, remarks TEXT, evaluated INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS scores(
 booking_id INTEGER NOT NULL REFERENCES bookings(id), rubric_id INTEGER NOT NULL REFERENCES rubrics(id),
 marks REAL, PRIMARY KEY(booking_id, rubric_id));
"""


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    d = g.pop('db', None)
    if d:
        d.close()


def q(sql, args=(), one=False):
    rows = get_db().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def ex(sql, args=()):
    db = get_db(); cur = db.execute(sql, args); db.commit(); return cur.lastrowid


def init_db():
    """Create all tables programmatically and seed the pre-existing Admin."""
    db = sqlite3.connect(DB); db.executescript(SCHEMA)
    if not db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
        db.execute("INSERT INTO users(name,email,password,role,status) VALUES(?,?,?,?,?)",
                   ('Administrator', 'admin@emp.com', generate_password_hash('admin123'), 'admin', 'Active'))
    db.commit(); db.close()
