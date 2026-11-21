from flask import Flask, render_template, session
from models.database import init_db, close_db
from controllers.helpers import load_user_into_g
from controllers import auth, admin, examiner, student

app = Flask(__name__)
app.secret_key = 'emp-dev-secret-change-me'

app.teardown_appcontext(close_db)
app.before_request(lambda: load_user_into_g(session))

for module in (auth, admin, examiner, student):
    app.register_blueprint(module.bp)


@app.errorhandler(403)
def forbidden(e):
    return render_template('error.html', msg='Access denied'), 403


@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', msg='Not found'), 404


init_db()

if __name__ == '__main__':
    app.run(debug=True)
