import sqlite3
from datetime import date
from flask import (Blueprint, render_template, request, redirect, url_for, flash, abort, g, session)
from werkzeug.security import generate_password_hash, check_password_hash
from models.database import q, ex, get_db
from models.queries import *
from controllers.helpers import role_required, in_window, home_for

bp = Blueprint('admin', __name__)


@bp.route('/admin')
@role_required('admin')
def admin_dashboard():
    c = lambda s: q(s, (), True)[0]
    stats = {'Courses': c("SELECT COUNT(*) FROM courses"), 'Examinations': c("SELECT COUNT(*) FROM exams"),
             'Examiners': c("SELECT COUNT(*) FROM users WHERE role='examiner'"),
             'Students': c("SELECT COUNT(*) FROM users WHERE role='student'"),
             'Slots': c("SELECT COUNT(*) FROM slots"), 'Bookings': c("SELECT COUNT(*) FROM bookings"),
             'Pending Examiners': c("SELECT COUNT(*) FROM users WHERE role='examiner' AND status='Pending'")}
    return render_template('admin_dashboard.html', stats=stats)

@bp.route('/admin/courses', methods=['GET', 'POST'])
@role_required('admin')
def admin_courses():
    if request.method == 'POST':
        f = request.form
        try:
            ex("INSERT INTO courses(code,name,description,credits,status) VALUES(?,?,?,?,?)",
               (f['code'].strip(), f['name'].strip(), f.get('description'), f.get('credits') or 3, f.get('status', 'Active')))
            flash('Course created', 'success')
        except sqlite3.IntegrityError:
            flash('Course code already exists', 'danger')
        return redirect(url_for('admin.admin_courses'))
    return render_template('admin_courses.html', courses=q("SELECT * FROM courses ORDER BY id DESC"), course=None)

@bp.route('/admin/courses/<int:cid>/edit', methods=['GET', 'POST'])
@role_required('admin')
def admin_course_edit(cid):
    c = q("SELECT * FROM courses WHERE id=?", (cid,), True) or abort(404)
    if request.method == 'POST':
        f = request.form
        try:
            ex("UPDATE courses SET code=?,name=?,description=?,credits=?,status=? WHERE id=?",
               (f['code'], f['name'], f.get('description'), f.get('credits') or 3, f['status'], cid))
            flash('Course updated', 'success'); return redirect(url_for('admin.admin_courses'))
        except sqlite3.IntegrityError:
            flash('Course code already exists', 'danger')
    return render_template('admin_courses.html', courses=q("SELECT * FROM courses ORDER BY id DESC"), course=c)

@bp.route('/admin/courses/<int:cid>/delete', methods=['POST'])
@role_required('admin')
def admin_course_delete(cid):
    if q("SELECT 1 FROM exams WHERE course_id=?", (cid,), True):
        flash('Cannot delete: course has examinations. Set it Inactive instead.', 'danger')
    else:
        ex("DELETE FROM courses WHERE id=?", (cid,)); flash('Course removed', 'success')
    return redirect(url_for('admin.admin_courses'))

@bp.route('/admin/exams')
@role_required('admin')
def admin_exams():
    rows = q("""SELECT e.*, c.code, c.name cname FROM exams e JOIN courses c ON c.id=e.course_id ORDER BY e.id DESC""")
    return render_template('admin_exams.html', exams=rows)

@bp.route('/admin/exams/new', methods=['GET', 'POST'])
@bp.route('/admin/exams/<int:eid>/edit', methods=['GET', 'POST'])
@role_required('admin')
def admin_exam_form(eid=None):
    e = q("SELECT * FROM exams WHERE id=?", (eid,), True) if eid else None
    if eid and not e: abort(404)
    if request.method == 'POST':
        f = request.form
        vals = [f['course_id'], f['name'], f['exam_type'], f['duration'], f['max_marks'],
                f.get('slot_start'), f.get('slot_end'), f.get('book_start'), f.get('book_end'), f.get('venue'), f.get('instructions')]
        if f.get('slot_start') and f.get('slot_end') and f['slot_end'] < f['slot_start'] or \
           f.get('book_start') and f.get('book_end') and f['book_end'] < f['book_start']:
            flash('End date cannot be before start date', 'danger')
        else:
            if e:
                ex("""UPDATE exams SET course_id=?,name=?,exam_type=?,duration=?,max_marks=?,slot_start=?,slot_end=?,
                      book_start=?,book_end=?,venue=?,instructions=? WHERE id=?""", vals + [eid])
            else:
                eid = ex("""INSERT INTO exams(course_id,name,exam_type,duration,max_marks,slot_start,slot_end,
                      book_start,book_end,venue,instructions) VALUES(?,?,?,?,?,?,?,?,?,?,?)""", vals)
            flash('Examination saved', 'success'); return redirect(url_for('admin.admin_exam_detail', eid=eid))
    return render_template('admin_exam_form.html', e=e, courses=q("SELECT * FROM courses WHERE status='Active'"), types=EXAM_TYPES)

@bp.route('/admin/exams/<int:eid>')
@role_required('admin')
def admin_exam_detail(eid):
    e = q("SELECT e.*, c.code, c.name cname FROM exams e JOIN courses c ON c.id=e.course_id WHERE e.id=?", (eid,), True) or abort(404)
    rubrics = q("SELECT * FROM rubrics WHERE exam_id=?", (eid,))
    assigned = q("SELECT u.* FROM users u JOIN exam_examiners x ON x.examiner_id=u.id WHERE x.exam_id=?", (eid,))
    avail = q("""SELECT * FROM users WHERE role='examiner' AND status='Approved'
                 AND id NOT IN (SELECT examiner_id FROM exam_examiners WHERE exam_id=?)""", (eid,))
    slots = q("""SELECT s.*, u.name ename FROM slots s JOIN users u ON u.id=s.examiner_id WHERE s.exam_id=? ORDER BY s.date,s.start_time""", (eid,))
    return render_template('admin_exam_detail.html', e=e, rubrics=rubrics, assigned=assigned, avail=avail,
                           slots=slots, statuses=STATUSES, rtotal=sum(r['max_marks'] for r in rubrics))

@bp.route('/admin/exams/<int:eid>/status/<s>', methods=['POST'])
@role_required('admin')
def admin_exam_status(eid, s):
    if s not in STATUSES: abort(400)
    ex("UPDATE exams SET status=? WHERE id=?", (s, eid)); flash('Status set to ' + s, 'success')
    return redirect(url_for('admin.admin_exam_detail', eid=eid))

@bp.route('/admin/exams/<int:eid>/publish', methods=['POST'])
@role_required('admin')
def admin_exam_publish(eid):
    e = q("SELECT published FROM exams WHERE id=?", (eid,), True) or abort(404)
    ex("UPDATE exams SET published=? WHERE id=?", (0 if e['published'] else 1, eid))
    flash('Results ' + ('unpublished' if e['published'] else 'published'), 'success')
    return redirect(url_for('admin.admin_exam_detail', eid=eid))

@bp.route('/admin/exams/<int:eid>/delete', methods=['POST'])
@role_required('admin')
def admin_exam_delete(eid):
    if q("SELECT 1 FROM slots WHERE exam_id=?", (eid,), True):
        flash('Cannot delete: slots/bookings exist for this exam. Close it instead.', 'danger')
        return redirect(url_for('admin.admin_exam_detail', eid=eid))
    ex("DELETE FROM rubrics WHERE exam_id=?", (eid,)); ex("DELETE FROM exam_examiners WHERE exam_id=?", (eid,))
    ex("DELETE FROM exams WHERE id=?", (eid,)); flash('Examination removed', 'success')
    return redirect(url_for('admin.admin_exams'))

@bp.route('/admin/exams/<int:eid>/rubrics', methods=['POST'])
@role_required('admin')
def admin_rubric_add(eid):
    f = request.form
    ex("INSERT INTO rubrics(exam_id,criterion,max_marks,weightage,description) VALUES(?,?,?,?,?)",
       (eid, f['criterion'], f['max_marks'], f.get('weightage') or 0, f.get('description')))
    flash('Rubric added', 'success'); return redirect(url_for('admin.admin_exam_detail', eid=eid))

@bp.route('/admin/rubrics/<int:rid>/delete', methods=['POST'])
@role_required('admin')
def admin_rubric_delete(rid):
    r = q("SELECT * FROM rubrics WHERE id=?", (rid,), True) or abort(404)
    if q("SELECT 1 FROM scores WHERE rubric_id=?", (rid,), True):
        flash('Rubric already used in evaluations; cannot delete', 'danger')
    else:
        ex("DELETE FROM rubrics WHERE id=?", (rid,)); flash('Rubric removed', 'success')
    return redirect(url_for('admin.admin_exam_detail', eid=r['exam_id']))

@bp.route('/admin/exams/<int:eid>/assign', methods=['POST'])
@role_required('admin')
def admin_assign(eid):
    ex("INSERT OR IGNORE INTO exam_examiners VALUES(?,?)", (eid, request.form['examiner_id']))
    flash('Examiner assigned', 'success'); return redirect(url_for('admin.admin_exam_detail', eid=eid))

@bp.route('/admin/exams/<int:eid>/unassign/<int:uid>', methods=['POST'])
@role_required('admin')
def admin_unassign(eid, uid):
    if q("SELECT 1 FROM slots WHERE exam_id=? AND examiner_id=?", (eid, uid), True):
        flash('Examiner has slots for this exam; change slot examiner first', 'danger')
    else:
        ex("DELETE FROM exam_examiners WHERE exam_id=? AND examiner_id=?", (eid, uid))
    return redirect(url_for('admin.admin_exam_detail', eid=eid))

@bp.route('/admin/examiners')
@role_required('admin')
def admin_examiners():
    return render_template('admin_examiners.html', rows=q("SELECT * FROM users WHERE role='examiner' ORDER BY status, id DESC"))

@bp.route('/admin/examiners/<int:uid>/<action>', methods=['POST'])
@role_required('admin')
def admin_examiner_action(uid, action):
    m = {'approve': 'Approved', 'deactivate': 'Deactivated', 'reject': 'Deactivated'}
    if action not in m: abort(400)
    ex("UPDATE users SET status=? WHERE id=? AND role='examiner'", (m[action], uid))
    flash('Examiner ' + m[action].lower(), 'success'); return redirect(url_for('admin.admin_examiners'))

@bp.route('/admin/students')
@role_required('admin')
def admin_students():
    return render_template('admin_students.html', rows=q("""SELECT u.*, (SELECT COUNT(*) FROM bookings b WHERE b.student_id=u.id) nb
                                                          FROM users u WHERE role='student' ORDER BY id DESC"""))

@bp.route('/admin/slots')
@role_required('admin')
def admin_slots():
    return render_template('admin_slots.html', slots=q(SLOT_SQL + " ORDER BY s.date, s.start_time"),
                           examiners=q("SELECT * FROM users WHERE role='examiner' AND status='Approved'"))

@bp.route('/admin/slots/<int:sid>/examiner', methods=['POST'])
@role_required('admin')
def admin_slot_examiner(sid):
    s = q("SELECT * FROM slots WHERE id=?", (sid,), True) or abort(404)
    new = request.form['examiner_id']
    ex("UPDATE slots SET examiner_id=? WHERE id=?", (new, sid))
    ex("INSERT OR IGNORE INTO exam_examiners VALUES(?,?)", (s['exam_id'], new))
    flash('Examiner changed for slot', 'success'); return redirect(url_for('admin.admin_slots'))

@bp.route('/admin/bookings')
@role_required('admin')
def admin_bookings():
    return render_template('admin_bookings.html', rows=q(BOOK_SQL + " ORDER BY b.id DESC"))

@bp.route('/admin/bookings/<int:bid>/reschedule', methods=['GET', 'POST'])
@role_required('admin')
def admin_reschedule(bid):
    b = q(BOOK_SQL + " WHERE b.id=?", (bid,), True) or abort(404)
    if b['status'] != 'Booked': flash('Only active bookings can be rescheduled', 'danger'); return redirect(url_for('admin.admin_bookings'))
    if request.method == 'POST':
        new = q("SELECT * FROM slots WHERE id=? AND exam_id=?", (request.form['slot_id'], b['exam_id']), True)
        if not new or new['available'] <= 0 or new['status'] != 'Available':
            flash('Target slot is unavailable', 'danger')
        else:
            old = b['slot_id']
            ex("UPDATE bookings SET slot_id=? WHERE id=?", (new['id'], bid))
            refresh_slot(old); refresh_slot(new['id'])
            flash('Booking rescheduled', 'success'); return redirect(url_for('admin.admin_bookings'))
    slots = q(SLOT_SQL + " WHERE s.exam_id=? AND s.available>0 AND s.status='Available' AND s.id!=?", (b['exam_id'], b['slot_id']))
    return render_template('admin_reschedule.html', b=b, slots=slots)

@bp.route('/admin/search')
@role_required('admin')
def admin_search():
    t = request.args.get('q', '').strip(); like = f'%{t}%'
    idn = t.lstrip('SsEeBb#') if t else ''
    idn = int(idn) if idn.isdigit() else -1
    return render_template('admin_search.html', t=t,
        students=q("SELECT * FROM users WHERE role='student' AND (name LIKE ? OR roll_no LIKE ? OR id=?)", (like, like, idn)) if t else [],
        examiners=q("SELECT * FROM users WHERE role='examiner' AND (name LIKE ? OR id=?)", (like, idn)) if t else [],
        exams=q("SELECT e.*, c.code FROM exams e JOIN courses c ON c.id=e.course_id WHERE e.name LIKE ? OR c.code LIKE ? OR e.id=?", (like, like, idn)) if t else [],
        bookings=q(BOOK_SQL + " WHERE u.name LIKE ? OR b.id=?", (like, idn)) if t else [])

