from models.database import q, ex


EXAM_TYPES = ['Viva', 'Practical', 'Project Demo', 'Assessment']
STATUSES = {'Draft': 'Close Slot Creation / Reset to Draft', 'Slot Creation': 'Open Slot Creation',
            'Booking Open': 'Open Student Booking', 'Closed': 'Close Booking', 'Completed': 'Mark Completed'}

SLOT_SQL = """SELECT s.*, e.name ename, e.status estatus, u.name examiner, c.code FROM slots s
              JOIN exams e ON e.id=s.exam_id JOIN users u ON u.id=s.examiner_id JOIN courses c ON c.id=e.course_id"""

BOOK_SQL = """SELECT b.*, u.name sname, u.roll_no, s.date, s.start_time, s.end_time, s.exam_id, e.name ename, x.name examiner
              FROM bookings b JOIN users u ON u.id=b.student_id JOIN slots s ON s.id=b.slot_id
              JOIN exams e ON e.id=s.exam_id JOIN users x ON x.id=s.examiner_id"""

def refresh_slot(sid):
    s = q("SELECT * FROM slots WHERE id=?", (sid,), True)
    n = q("SELECT COUNT(*) FROM bookings WHERE slot_id=? AND status IN ('Booked','Completed')", (sid,), True)[0]
    if s['status'] in ('Cancelled', 'Completed'):
        ex("UPDATE slots SET available=? WHERE id=?", (s['capacity'] - n, sid)); return
    av = s['capacity'] - n
    ex("UPDATE slots SET available=?, status=? WHERE id=?", (av, 'Full' if av <= 0 else 'Available', sid))

