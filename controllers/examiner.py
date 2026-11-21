import sqlite3
from datetime import date
from flask import (Blueprint, render_template, request, redirect, url_for, flash, abort, g, session)
from werkzeug.security import generate_password_hash, check_password_hash
from models.database import q, ex, get_db
from models.queries import *
from controllers.helpers import role_required, in_window, home_for

bp = Blueprint('examiner', __name__)


@bp.route('/examiner')
@role_required('examiner')
def examiner_dashboard():
    me = g.user['id']
    exams = q("""SELECT e.*, c.name cname FROM exams e JOIN exam_examiners x ON x.exam_id=e.id
                 JOIN courses c ON c.id=e.course_id WHERE x.examiner_id=?""", (me,))
    slots = q("SELECT s.*, e.name ename FROM slots s JOIN exams e ON e.id=s.exam_id WHERE s.examiner_id=? ORDER BY s.date", (me,))
    booked = q("""SELECT COUNT(*) FROM bookings b JOIN slots s ON s.id=b.slot_id WHERE s.examiner_id=? AND b.status IN ('Booked','Completed')""", (me,), True)[0]
    pending = q("""SELECT COUNT(*) FROM bookings b JOIN slots s ON s.id=b.slot_id WHERE s.examiner_id=? AND b.status='Booked'""", (me,), True)[0]
    return render_template('examiner_dashboard.html', exams=exams, slots=slots, booked=booked, pending=pending)

def my_exam(eid):
    return q("""SELECT e.* FROM exams e JOIN exam_examiners x ON x.exam_id=e.id WHERE e.id=? AND x.examiner_id=?""", (eid, g.user['id']), True)

def overlaps(date_, st, en, exclude=None):
    return q("""SELECT 1 FROM slots WHERE examiner_id=? AND date=? AND status!='Cancelled' AND id!=? AND start_time<? AND end_time>?""",
             (g.user['id'], date_, exclude or -1, en, st), True)

@bp.route('/examiner/slots', methods=['GET', 'POST'])
@role_required('examiner')
def examiner_slots():
    me = g.user['id']
    if request.method == 'POST':
        f = request.form
        e = my_exam(f['exam_id'])
        cap = int(f['capacity'])
        if not e: abort(403)
        elif e['status'] != 'Slot Creation' or not in_window(e['slot_start'], e['slot_end']):
            flash('Slot creation is not open for this examination', 'danger')
        elif f['end_time'] <= f['start_time'] or cap < 1:
            flash('Invalid time range or capacity', 'danger')
        elif overlaps(f['date'], f['start_time'], f['end_time']):
            flash('You already have a slot overlapping this time', 'danger')
        else:
            ex("INSERT INTO slots(exam_id,examiner_id,date,start_time,end_time,capacity,available,location) VALUES(?,?,?,?,?,?,?,?)",
               (e['id'], me, f['date'], f['start_time'], f['end_time'], cap, cap, f.get('location') or e['venue']))
            flash('Slot created', 'success')
        return redirect(url_for('examiner.examiner_slots'))
    exams = q("""SELECT e.* FROM exams e JOIN exam_examiners x ON x.exam_id=e.id WHERE x.examiner_id=?""", (me,))
    slots = q("SELECT s.*, e.name ename, e.status estatus FROM slots s JOIN exams e ON e.id=s.exam_id WHERE s.examiner_id=? ORDER BY s.date,s.start_time", (me,))
    return render_template('examiner_slots.html', exams=exams, slots=slots)

def editable_slot(sid):
    s = q("SELECT s.*, e.status estatus FROM slots s JOIN exams e ON e.id=s.exam_id WHERE s.id=? AND s.examiner_id=?", (sid, g.user['id']), True)
    if not s: abort(403)
    return s

@bp.route('/examiner/slots/<int:sid>/edit', methods=['GET', 'POST'])
@role_required('examiner')
def examiner_slot_edit(sid):
    s = editable_slot(sid)
    if s['estatus'] not in ('Draft', 'Slot Creation'):
        flash('Slots cannot be modified once booking has started', 'danger'); return redirect(url_for('examiner.examiner_slots'))
    if request.method == 'POST':
        f = request.form; cap = int(f['capacity'])
        n = s['capacity'] - s['available']
        if f['end_time'] <= f['start_time'] or cap < max(n, 1): flash('Invalid time/capacity (capacity below booked count?)', 'danger')
        elif overlaps(f['date'], f['start_time'], f['end_time'], sid): flash('Overlaps another slot', 'danger')
        else:
            ex("UPDATE slots SET date=?,start_time=?,end_time=?,capacity=?,location=? WHERE id=?",
               (f['date'], f['start_time'], f['end_time'], cap, f.get('location'), sid))
            refresh_slot(sid); flash('Slot updated', 'success'); return redirect(url_for('examiner.examiner_slots'))
    return render_template('examiner_slot_edit.html', s=s)

@bp.route('/examiner/slots/<int:sid>/delete', methods=['POST'])
@role_required('examiner')
def examiner_slot_delete(sid):
    s = editable_slot(sid)
    if s['estatus'] not in ('Draft', 'Slot Creation'): flash('Booking has started; cannot remove', 'danger')
    elif q("SELECT 1 FROM bookings WHERE slot_id=? AND status='Booked'", (sid,), True): flash('Slot has bookings', 'danger')
    else: ex("DELETE FROM bookings WHERE slot_id=?", (sid,)); ex("DELETE FROM slots WHERE id=?", (sid,)); flash('Slot removed', 'success')
    return redirect(url_for('examiner.examiner_slots'))

@bp.route('/examiner/slots/<int:sid>/students')
@role_required('examiner')
def examiner_slot_students(sid):
    s = editable_slot(sid)
    rows = q("SELECT b.*, u.name sname, u.email, u.roll_no FROM bookings b JOIN users u ON u.id=b.student_id WHERE b.slot_id=? AND b.status!='Cancelled'", (sid,))
    e = q("SELECT * FROM exams WHERE id=?", (s['exam_id'],), True)
    return render_template('examiner_students.html', s=s, rows=rows, e=e)

@bp.route('/examiner/evaluate/<int:bid>', methods=['GET', 'POST'])
@role_required('examiner')
def examiner_evaluate(bid):
    b = q(BOOK_SQL + " WHERE b.id=?", (bid,), True) or abort(404)
    s = q("SELECT * FROM slots WHERE id=?", (b['slot_id'],), True)
    if s['examiner_id'] != g.user['id']: abort(403)       # only own slots
    if b['status'] == 'Cancelled': abort(400)
    e = q("SELECT * FROM exams WHERE id=?", (b['exam_id'],), True)
    rubrics = q("SELECT * FROM rubrics WHERE exam_id=?", (e['id'],))
    old = {r['rubric_id']: r['marks'] for r in q("SELECT * FROM scores WHERE booking_id=?", (bid,))}
    if request.method == 'POST':
        f = request.form; total = 0; vals = []; ok = True
        if rubrics:
            for r in rubrics:
                try: m = float(f.get(f'r{r["id"]}', ''))
                except ValueError: m = -1
                if m < 0 or m > r['max_marks']: ok = False
                vals.append((bid, r['id'], m)); total += m
        else:
            try: total = float(f.get('total', ''))
            except ValueError: total = -1
            ok = 0 <= total <= (e['max_marks'] or 0)
        if not ok: flash('Marks must be numbers within the allowed maximum', 'danger')
        else:
            for v in vals: ex("INSERT OR REPLACE INTO scores VALUES(?,?,?)", v)
            ex("UPDATE bookings SET marks=?, remarks=?, evaluated=1, status='Completed' WHERE id=?", (total, f.get('remarks'), bid))
            if not q("SELECT 1 FROM bookings WHERE slot_id=? AND status='Booked'", (s['id'],), True):
                ex("UPDATE slots SET status='Completed' WHERE id=?", (s['id'],))
            flash('Evaluation saved', 'success'); return redirect(url_for('examiner.examiner_slot_students', sid=s['id']))
    return render_template('examiner_evaluate.html', b=b, e=e, rubrics=rubrics, old=old)

