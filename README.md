# Examination Management Portal (Flask + SQLite + Bootstrap)
Run:
    pip install -r requirements.txt
    python app.py        # http://127.0.0.1:5000
The database (emp.db) is created automatically on first run.
Admin login (pre-seeded): admin@emp.com / admin123
Examiners register themselves and wait for Admin approval. Students register and log in directly.
Typical flow: Admin creates Course -> Exam -> Rubrics -> assigns Examiner -> opens "Slot Creation"
-> Examiner creates slots -> Admin opens "Booking" -> Students book -> Examiner evaluates
-> Admin publishes results -> Students view marks/remarks.
