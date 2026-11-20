"""Smart LMS: small Flask app with a local SQLite database."""
import os
import sqlite3
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, request, session, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "smart_lms.db"))
app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get("SECRET_KEY", "local-development-key-change-before-deploy")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

COURSES = [
    {"id": 1, "name": "HTML and CSS", "description": "Learn website design and development.", "duration": "4 Weeks"},
    {"id": 2, "name": "JavaScript", "description": "Learn programming for interactive websites.", "duration": "6 Weeks"},
    {"id": 3, "name": "Python Programming", "description": "Learn Python from the basics.", "duration": "8 Weeks"},
    {"id": 4, "name": "Data Science", "description": "Explore data analysis and visualization.", "duration": "8 Weeks"},
    {"id": 5, "name": "Database Management", "description": "Learn SQL and database concepts.", "duration": "5 Weeks"},
    {"id": 6, "name": "Machine Learning", "description": "Understand the basics of machine learning.", "duration": "10 Weeks"},
]


def get_db():
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'Student',
            email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
            course TEXT NOT NULL DEFAULT '', photo TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS enrollments (
            user_id INTEGER NOT NULL, course_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, course_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS completed_lessons (
            user_id INTEGER NOT NULL, lesson_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, lesson_id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
            assignment_id INTEGER NOT NULL, filename TEXT NOT NULL,
            submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, assignment_id), FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS quiz_scores (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, score INTEGER NOT NULL,
            submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, message TEXT NOT NULL,
            sender TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY, user_id INTEGER, message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL
        );
    """)
    admin_username = os.environ.get("ADMIN_USERNAME")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if admin_username and admin_password and not db.execute("SELECT 1 FROM users WHERE role='Admin'").fetchone():
        db.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?, 'Admin')",
                   (admin_username.strip(), generate_password_hash(admin_password)))
    db.commit()


def current_user():
    if "user_id" not in session:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return jsonify(error="Please log in first."), 401
        return fn(*args, **kwargs)
    return wrapped


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify(error="Please log in first."), 401
        if user["role"] != "Admin":
            return jsonify(error="Admin access required."), 403
        return fn(*args, **kwargs)
    return wrapped


def user_json(user):
    return {"id": user["id"], "username": user["username"], "role": user["role"],
            "email": user["email"], "phone": user["phone"], "course": user["course"], "photo": user["photo"]}


@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/<path:filename>")
def pages(filename):
    if filename.startswith("api/") or filename.startswith("."):
        return jsonify(error="Not found."), 404
    return send_from_directory(BASE_DIR, filename)


@app.get("/api/me")
def me():
    user = current_user()
    return jsonify(user=user_json(user) if user else None)


@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    username, password = str(data.get("username", "")).strip(), str(data.get("password", ""))
    if len(username) < 2 or len(password) < 6:
        return jsonify(error="Use a username with at least 2 characters and a password with at least 6."), 400
    role = "Admin" if data.get("role") == "Admin" and os.environ.get("ALLOW_ADMIN_REGISTRATION") == "1" else "Student"
    db = get_db()
    try:
        cur = db.execute("INSERT INTO users(username,password_hash,role) VALUES(?,?,?)",
                         (username, generate_password_hash(password), role))
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="That username is already registered."), 409
    session["user_id"] = cur.lastrowid
    return jsonify(user=user_json(current_user())), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    user = get_db().execute("SELECT * FROM users WHERE username=?", (str(data.get("username", "")).strip(),)).fetchone()
    if not user or not check_password_hash(user["password_hash"], str(data.get("password", ""))):
        return jsonify(error="Username or password is incorrect."), 401
    session.clear()
    session["user_id"] = user["id"]
    return jsonify(user=user_json(user))


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    db = get_db()
    return jsonify(enrolled=db.execute("SELECT count(*) FROM enrollments WHERE user_id=?", (uid,)).fetchone()[0],
                   completed=db.execute("SELECT count(*) FROM completed_lessons WHERE user_id=?", (uid,)).fetchone()[0],
                   best_score=db.execute("SELECT coalesce(max(score),0) FROM quiz_scores WHERE user_id=?", (uid,)).fetchone()[0],
                   submissions=db.execute("SELECT count(*) FROM submissions WHERE user_id=?", (uid,)).fetchone()[0])


@app.get("/api/courses")
@login_required
def courses():
    uid = session["user_id"]
    ids = {row[0] for row in get_db().execute("SELECT course_id FROM enrollments WHERE user_id=?", (uid,))}
    return jsonify(courses=[dict(c, enrolled=c["id"] in ids) for c in COURSES])


@app.post("/api/courses/<int:course_id>/enroll")
@login_required
def enroll(course_id):
    if course_id not in {c["id"] for c in COURSES}:
        return jsonify(error="Course not found."), 404
    db = get_db()
    db.execute("INSERT OR IGNORE INTO enrollments(user_id,course_id) VALUES(?,?)", (session["user_id"], course_id))
    db.commit()
    return jsonify(ok=True)


@app.get("/api/lessons")
@login_required
def lessons():
    ids = [r[0] for r in get_db().execute("SELECT lesson_id FROM completed_lessons WHERE user_id=?", (session["user_id"],))]
    return jsonify(completed=ids)


@app.post("/api/lessons/<int:lesson_id>/complete")
@login_required
def complete_lesson(lesson_id):
    if lesson_id not in (1, 2, 3):
        return jsonify(error="Lesson not found."), 404
    db = get_db()
    db.execute("INSERT OR IGNORE INTO completed_lessons(user_id,lesson_id) VALUES(?,?)", (session["user_id"], lesson_id))
    db.commit()
    return jsonify(ok=True)


@app.get("/api/assignments")
@login_required
def assignments():
    rows = get_db().execute("SELECT assignment_id id,filename fileName,submitted_at submittedAt FROM submissions WHERE user_id=?", (session["user_id"],)).fetchall()
    return jsonify(submissions=[dict(row) for row in rows])


@app.post("/api/assignments/<int:assignment_id>")
@login_required
def submit_assignment(assignment_id):
    data = request.get_json(silent=True) or {}
    filename = str(data.get("filename", "")).strip()
    if assignment_id not in (1, 2, 3) or not filename or len(filename) > 255:
        return jsonify(error="Choose a valid assignment and file."), 400
    db = get_db()
    db.execute("INSERT INTO submissions(user_id,assignment_id,filename) VALUES(?,?,?) ON CONFLICT(user_id,assignment_id) DO UPDATE SET filename=excluded.filename, submitted_at=CURRENT_TIMESTAMP",
               (session["user_id"], assignment_id, filename))
    db.commit()
    return jsonify(ok=True)


@app.post("/api/quiz")
@login_required
def save_quiz():
    data = request.get_json(silent=True) or {}
    try:
        score = max(0, min(5, int(data.get("score", -1))))
    except (TypeError, ValueError):
        return jsonify(error="Invalid score."), 400
    db = get_db()
    db.execute("INSERT INTO quiz_scores(user_id,score) VALUES(?,?)", (session["user_id"], score))
    db.commit()
    return jsonify(ok=True)


@app.get("/api/profile")
@login_required
def profile():
    return jsonify(profile=user_json(current_user()))


@app.put("/api/profile")
@login_required
def update_profile():
    data = request.get_json(silent=True) or {}
    fields = {key: str(data.get(key, "")).strip() for key in ("name", "email", "phone", "course", "photo")}
    if not fields["name"]:
        return jsonify(error="Name is required."), 400
    if len(fields["photo"]) > 1_500_000:
        return jsonify(error="Profile photo is too large."), 400
    db = get_db()
    db.execute("UPDATE users SET username=?,email=?,phone=?,course=?,photo=? WHERE id=?",
               (fields["name"], fields["email"], fields["phone"], fields["course"], fields["photo"], session["user_id"]))
    db.commit()
    return jsonify(profile=user_json(current_user()))


@app.get("/api/admin/students")
@admin_required
def admin_students():
    rows = get_db().execute("SELECT id,username name,email FROM users WHERE role='Student' ORDER BY id DESC").fetchall()
    count = get_db().execute("SELECT count(*) FROM submissions").fetchone()[0]
    return jsonify(students=[dict(row) for row in rows], submissions=count)


@app.post("/api/admin/students")
@admin_required
def add_student():
    data = request.get_json(silent=True) or {}
    name, email = str(data.get("name", "")).strip(), str(data.get("email", "")).strip()
    if not name or not email:
        return jsonify(error="Name and email are required."), 400
    db = get_db()
    username = email.split("@")[0].strip() or name
    suffix = 1
    base = username
    while db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
        suffix += 1
        username = f"{base}{suffix}"
    cur = db.execute("INSERT INTO users(username,email,password_hash,role) VALUES(?,?,?,'Student')",
                     (username, email, generate_password_hash(os.urandom(16).hex())))
    db.commit()
    return jsonify(id=cur.lastrowid), 201


@app.delete("/api/admin/students/<int:student_id>")
@admin_required
def delete_student(student_id):
    db = get_db()
    db.execute("DELETE FROM users WHERE id=? AND role='Student'", (student_id,))
    db.commit()
    return jsonify(ok=True)


@app.get("/api/notifications")
@login_required
def get_notifications():
    rows = get_db().execute("SELECT id,message,created_at createdAt FROM notifications WHERE user_id IS NULL OR user_id=? ORDER BY id DESC", (session["user_id"],)).fetchall()
    if not rows:
        return jsonify(notifications=[{"id": 1, "message": "Explore the available courses and enroll to start learning.", "createdAt": "Welcome"},
                                      {"id": 2, "message": "Your HTML Basics assignment is ready in the Assignments page.", "createdAt": "Assignment"},
                                      {"id": 3, "message": "Complete the online quiz to check your knowledge.", "createdAt": "Quiz"}])
    return jsonify(notifications=[dict(row) for row in rows])


@app.get("/api/chat")
@login_required
def chat_history():
    rows = get_db().execute("SELECT message,sender,created_at createdAt FROM chat_messages WHERE user_id=? ORDER BY id", (session["user_id"],)).fetchall()
    return jsonify(messages=[dict(row) for row in rows])


@app.post("/api/chat")
@login_required
def chat_message():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    if not message or len(message) > 2000:
        return jsonify(error="Enter a message up to 2,000 characters."), 400
    db = get_db()
    db.execute("INSERT INTO chat_messages(user_id,message,sender) VALUES(?,?,'You')", (session["user_id"], message))
    reply = "Thanks for your question! Review the lesson notes and try breaking the topic into smaller steps."
    db.execute("INSERT INTO chat_messages(user_id,message,sender) VALUES(?,?,'Assistant')", (session["user_id"], reply))
    db.commit()
    return jsonify(reply=reply)


with app.app_context():
    init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG") == "1")
