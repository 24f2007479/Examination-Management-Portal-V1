import sqlite3
from datetime import date
from flask import (Blueprint, render_template, request, redirect, url_for, flash, abort, g, session)
from werkzeug.security import generate_password_hash, check_password_hash
from models.database import q, ex, get_db
from models.queries import *
from controllers.helpers import role_required, in_window, home_for

bp = Blueprint('student', __name__)


@bp.route('/student')
@role_required('student')
def student_dashboard():
    me = g.user['id']
    avail = q("""SELECT e.*, c.name cname FROM exams e JOIN courses c ON c.id=e.course_id WHERE e.status='Booking Open'""")
    upcoming = q(BOOK_SQL + " WHERE b.student_id=? AND b.status='Booked' ORDER BY s.date", (me,))
    results = q(BOOK_SQL + " WHERE b.student_id=? AND b.status='Completed' AND e.published=1", (me,))
    slots = q(SLOT_SQL + " WHERE e.status='Booking Open' AND s.status='Available' ORDER BY s.date LIMIT 8")
    return render_template('student_dashboard.html', avail=avail, upcoming=upcoming, results=results, slots=slots)

@bp.route('/student/exams')
@role_required('student')
def student_exams():
    t, ty, cid = request.args.get('q', ''), request.args.get('type', ''), request.args.get('course', '')
    sql = "SELECT e.*, c.code, c.name cname FROM exams e JOIN courses c ON c.id=e.course_id WHERE e.status!='Draft' AND (e.name LIKE ? OR c.name LIKE ? OR c.code LIKE ?)"
    a = [f'%{t}%'] * 3
    if ty: sql += " AND e.exam_type=?"; a.append(ty)
    if cid: sql += " AND e.course_id=?"; a.append(cid)
    return render_template('student_exams.html', exams=q(sql + " ORDER BY e.id DESC", a), types=EXAM_TYPES,
                           courses=q("SELECT * FROM courses"), t=t, ty=ty, cid=cid)

@bp.route('/student/exams/<int:eid>')
@role_required('student')
def student_exam(eid):
    e = q("SELECT e.*, c.code, c.name cname FROM exams e JOIN courses c ON c.id=e.course_id WHERE e.id=?", (eid,), True) or abort(404)
    slots = q(SLOT_SQL + " WHERE s.exam_id=? AND s.status!='Cancelled' ORDER BY s.date, s.start_time", (eid,))
    mine = q("SELECT * FROM bookings WHERE student_id=? AND status='Booked' AND slot_id IN (SELECT id FROM slots WHERE exam_id=?)", (g.user['id'], eid), True)
    can_book = e['status'] == 'Booking Open' and in_window(e['book_start'], e['book_end'])
    return render_template('student_exam.html', e=e, slots=slots, mine=mine, can_book=can_book,
                           rubrics=q("SELECT * FROM rubrics WHERE exam_id=?", (eid,)))

@bp.route('/student/book/<int:sid>', methods=['POST'])
@role_required('student')
def student_book(sid):
    s = q(SLOT_SQL + " WHERE s.id=?", (sid,), True) or abort(404)
    e = q("SELECT * FROM exams WHERE id=?", (s['exam_id'],), True)
    me = g.user['id']
    dup = q("""SELECT 1 FROM bookings b JOIN slots t ON t.id=b.slot_id WHERE b.student_id=? AND t.exam_id=? AND b.status IN ('Booked','Completed')""", (me, e['id']), True)
    if e['status'] != 'Booking Open' or not in_window(e['book_start'], e['book_end']): flash('Booking is not open for this exam', 'danger')
    elif dup: flash('You already have a booking for this examination', 'danger')
    elif s['status'] != 'Available' or s['available'] <= 0: flash('Slot is full or unavailable', 'danger')
    else:
        # atomic capacity guard against overbooking
        cur = get_db().execute("UPDATE slots SET available=available-1 WHERE id=? AND available>0", (sid,))
        get_db().commit()
        if cur.rowcount == 0: flash('Slot just filled up', 'danger')
        else:
            ex("INSERT INTO bookings(student_id,slot_id) VALUES(?,?)", (me, sid))
            refresh_slot(sid); flash('Slot booked successfully', 'success')
    return redirect(url_for('student.student_exam', eid=e['id']))

@bp.route('/student/cancel/<int:bid>', methods=['POST'])
@role_required('student')
def student_cancel(bid):
    b = q("SELECT * FROM bookings WHERE id=? AND student_id=?", (bid, g.user['id']), True) or abort(404)
    s = q("SELECT * FROM slots WHERE id=?", (b['slot_id'],), True)
    e = q("SELECT * FROM exams WHERE id=?", (s['exam_id'],), True)
    if b['status'] != 'Booked': flash('Only active bookings can be cancelled', 'danger')
    elif e['status'] != 'Booking Open' or (e['book_end'] and date.today().isoformat() > e['book_end']):
        flash('Booking deadline has passed; cannot cancel', 'danger')
    else:
        ex("UPDATE bookings SET status='Cancelled' WHERE id=?", (bid,)); refresh_slot(s['id']); flash('Booking cancelled', 'success')
    return redirect(url_for('student.student_bookings'))

@bp.route('/student/bookings')
@role_required('student')
def student_bookings():
    return render_template('student_bookings.html', rows=q(BOOK_SQL + " WHERE b.student_id=? ORDER BY b.id DESC", (g.user['id'],)))

@bp.route('/student/results')
@role_required('student')
def student_results():
    rows = q(BOOK_SQL + " WHERE b.student_id=? AND b.status='Completed' AND e.published=1 ORDER BY b.id DESC", (g.user['id'],))
    det = {r['id']: q("SELECT r.criterion, r.max_marks, s.marks FROM scores s JOIN rubrics r ON r.id=s.rubric_id WHERE s.booking_id=?", (r['id'],)) for r in rows}
    mx = {r['id']: q("SELECT max_marks FROM exams WHERE id=?", (r['exam_id'],), True)[0] for r in rows}
    return render_template('student_results.html', rows=rows, det=det, mx=mx)

