import sqlite3
from datetime import date
from flask import (Blueprint, render_template, request, redirect, url_for, flash, abort, g, session)
from werkzeug.security import generate_password_hash, check_password_hash
from models.database import q, ex, get_db
from models.queries import *
from controllers.helpers import role_required, in_window, home_for

bp = Blueprint('auth', __name__)

@bp.route('/')
def index():
    return redirect(home_for(g.user)) if g.user else redirect(url_for('auth.login'))

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = q("SELECT * FROM users WHERE email=?", (request.form['email'].strip().lower(),), True)
        if u and check_password_hash(u['password'], request.form['password']):
            session.clear(); session['uid'] = u['id']
            return redirect(home_for(u))
        flash('Invalid email or password', 'danger')
    return render_template('login.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        f = request.form
        role = f.get('role')
        if role not in ('student', 'examiner'): abort(400)
        email = f['email'].strip().lower()
        if len(f['password']) < 6:
            flash('Password must be at least 6 characters', 'danger')
        elif q("SELECT 1 FROM users WHERE email=?", (email,), True):
            flash('Email already registered', 'danger')
        else:
            ex("INSERT INTO users(name,email,password,role,status,department,contact,roll_no) VALUES(?,?,?,?,?,?,?,?)",
               (f['name'].strip(), email, generate_password_hash(f['password']), role,
                'Pending' if role == 'examiner' else 'Active', f.get('department'), f.get('contact'), f.get('roll_no')))
            flash('Registered! ' + ('Await Admin approval after login.' if role == 'examiner' else 'Please log in.'), 'success')
            return redirect(url_for('auth.login'))
    return render_template('register.html')

@bp.route('/logout')
def logout():
    session.clear(); return redirect(url_for('auth.login'))

@bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if not g.user: return redirect(url_for('auth.login'))
    if request.method == 'POST':
        f = request.form
        ex("UPDATE users SET name=?, contact=?, department=?, roll_no=? WHERE id=?",
           (f['name'], f.get('contact'), f.get('department'), f.get('roll_no'), g.user['id']))
        if f.get('password'):
            if len(f['password']) < 6: flash('Password too short', 'danger'); return redirect(url_for('auth.profile'))
            ex("UPDATE users SET password=? WHERE id=?", (generate_password_hash(f['password']), g.user['id']))
        flash('Profile updated', 'success'); return redirect(url_for('auth.profile'))
    return render_template('profile.html')

