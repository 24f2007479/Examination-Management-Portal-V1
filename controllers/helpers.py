from datetime import date
from functools import wraps
from flask import g, redirect, url_for, abort, render_template
from models.database import q


def load_user_into_g(session):
    g.user = q("SELECT * FROM users WHERE id=?", (session['uid'],), True) if 'uid' in session else None


def role_required(role):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if not g.user: return redirect(url_for('login'))
            if g.user['role'] != role: abort(403)
            if role == 'examiner' and g.user['status'] != 'Approved':
                return render_template('pending.html')
            return f(*a, **k)
        return w
    return deco

def in_window(start, end):
    t = date.today().isoformat()
    return (not start or start <= t) and (not end or t <= end)

def home_for(u):
    return url_for(u['role'] + '.' + u['role'] + '_dashboard')

