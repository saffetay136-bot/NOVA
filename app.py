import os
import sqlite3
import secrets
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, render_template, request, session

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "nova.db"))
HOST_NAME = os.environ.get("HOST_NAME", "s")
HOST_PASSWORD = os.environ.get("HOST_PASSWORD", "")
AI_API_URL = os.environ.get("AI_API_URL", "")
AI_API_KEY = os.environ.get("AI_API_KEY", "")
AI_MODEL = os.environ.get("AI_MODEL", "gpt-4o-mini")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", secrets.token_hex(32))
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "").lower() == "true",
)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                picture TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS locations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                latitude REAL,
                longitude REAL,
                accuracy REAL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS network_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                ip_address TEXT,
                user_agent TEXT,
                path TEXT,
                created_at TEXT NOT NULL
            );
        """)


def now():
    return datetime.now(timezone.utc).isoformat()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    with db() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def trace_request(user_id=None):
    ip_address = request.remote_addr
    with db() as conn:
        conn.execute(
            "INSERT INTO network_traces(user_id, ip_address, user_agent, path, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, ip_address, request.headers.get("User-Agent", ""), request.path, now()),
        )


def ai_reply(message, history):
    if not AI_API_URL or not AI_API_KEY:
        return (
            "Sistem şu an demo modunda çalışıyor. "
            "Mesajını ve sohbet geçmişini kaydettim; OpenAI uyumlu bir API bağlandığında gerçek yanıt vereceğim."
        )

    messages = [
        {
            "role": "system",
            "content": "Türkçe konuş. Kısa, doğru ve güvenli yanıtlar ver. Kullanıcının geçmişini bağlam olarak kullan.",
        }
    ]
    messages.extend(history[-12:])
    messages.append({"role": "user", "content": message})

    response = requests.post(
        AI_API_URL,
        headers={
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={"model": AI_MODEL, "messages": messages, "temperature": 0.7},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


@app.after_request
def add_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.route("/")
def chat():
    trace_request(session.get("user_id"))
    user = current_user()
    if not user:
        return render_template("login.html", google_client_id=GOOGLE_CLIENT_ID)
    return render_template("chat.html", user=dict(user))


@app.route("/login")
def login():
    trace_request()
    return render_template("login.html", google_client_id=GOOGLE_CLIENT_ID)


@app.route("/api/auth/google", methods=["POST"])
def auth_google():
    trace_request()
    credential = (request.get_json(silent=True) or {}).get("credential", "")
    if not credential:
        return jsonify({"error": "Google kimlik bilgisi eksik"}), 400

    verification = requests.get(
        "https://oauth2.googleapis.com/tokeninfo",
        params={"id_token": credential},
        timeout=10,
    )
    if verification.status_code != 200:
        return jsonify({"error": "Google kimliği doğrulanamadı"}), 401

    profile = verification.json()
    if GOOGLE_CLIENT_ID and profile.get("aud") != GOOGLE_CLIENT_ID:
        return jsonify({"error": "Google Client ID eşleşmiyor"}), 401
    if profile.get("email_verified") != "true":
        return jsonify({"error": "Google e-posta adresi doğrulanmamış"}), 401

    user_id = profile["sub"]
    with db() as conn:
        conn.execute(
            """
            INSERT INTO users(id, email, name, picture, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                email=excluded.email,
                name=excluded.name,
                picture=excluded.picture
            """,
            (user_id, profile["email"], profile.get("name", ""), profile.get("picture", ""), now()),
        )
    session.clear()
    session["user_id"] = user_id
    return jsonify({"ok": True})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@app.route("/api/messages")
def messages():
    user = current_user()
    if not user:
        return jsonify({"error": "Giriş gerekli"}), 401
    trace_request(user["id"])
    with db() as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT 50",
            (user["id"],),
        ).fetchall()
    return jsonify([dict(row) for row in reversed(rows)])


@app.route("/api/chat", methods=["POST"])
def chat_api():
    user = current_user()
    if not user:
        return jsonify({"error": "Giriş gerekli"}), 401
    trace_request(user["id"])
    content = (request.get_json(silent=True) or {}).get("message", "").strip()
    if not content:
        return jsonify({"error": "Mesaj boş olamaz"}), 400
    if len(content) > 4000:
        return jsonify({"error": "Mesaj çok uzun"}), 400

    with db() as conn:
        conn.execute(
            "INSERT INTO messages(user_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
            (user["id"], content, now()),
        )
        history = [
            dict(row)
            for row in conn.execute(
                "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT 24",
                (user["id"],),
            ).fetchall()
        ][::-1]

    try:
        answer = ai_reply(content, history)
    except requests.RequestException:
        answer = "Yapay zekâ sağlayıcısına ulaşılamadı. Lütfen API ayarlarını kontrol edin."

    with db() as conn:
        conn.execute(
            "INSERT INTO messages(user_id, role, content, created_at) VALUES (?, 'assistant', ?, ?)",
            (user["id"], answer, now()),
        )
    return jsonify({"answer": answer})


@app.route("/api/location", methods=["POST"])
def location():
    user = current_user()
    if not user:
        return jsonify({"error": "Giriş gerekli"}), 401
    payload = request.get_json(silent=True) or {}
    latitude = payload.get("latitude")
    longitude = payload.get("longitude")
    accuracy = payload.get("accuracy")
    if latitude is None or longitude is None:
        return jsonify({"error": "Konum bilgisi eksik"}), 400
    trace_request(user["id"])
    with db() as conn:
        conn.execute(
            "INSERT INTO locations(user_id, latitude, longitude, accuracy, created_at) VALUES (?, ?, ?, ?, ?)",
            (user["id"], latitude, longitude, accuracy, now()),
        )
    return jsonify({"ok": True})


@app.route("/host-login")
def host_login():
    trace_request()
    return render_template("host_login.html")


@app.route("/api/host/login", methods=["POST"])
def host_login_api():
    payload = request.get_json(silent=True) or {}
    name = payload.get("name", "")
    password = payload.get("password", "")
    if not HOST_PASSWORD:
        return jsonify({"error": "Host girişi sunucu ayarlarında etkin değil"}), 503
    if not (secrets.compare_digest(name, HOST_NAME) and secrets.compare_digest(password, HOST_PASSWORD)):
        trace_request()
        return jsonify({"error": "Host bilgileri hatalı"}), 401
    session.clear()
    session["host"] = True
    trace_request()
    return jsonify({"ok": True})


@app.route("/host")
def host():
    if not session.get("host"):
        return render_template("host_login.html"), 403
    trace_request()
    with db() as conn:
        users = [dict(row) for row in conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()]
        locations = [dict(row) for row in conn.execute(
            "SELECT locations.*, users.name, users.email FROM locations "
            "LEFT JOIN users ON users.id = locations.user_id ORDER BY locations.id DESC LIMIT 100"
        ).fetchall()]
        traces = [dict(row) for row in conn.execute(
            "SELECT network_traces.*, users.name, users.email FROM network_traces "
            "LEFT JOIN users ON users.id = network_traces.user_id ORDER BY network_traces.id DESC LIMIT 100"
        ).fetchall()]
    return render_template("host.html", users=users, locations=locations, traces=traces)


@app.route("/api/host/messages/<user_id>")
def host_messages(user_id):
    if not session.get("host"):
        return jsonify({"error": "Host girişi gerekli"}), 403
    with db() as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/host/logout", methods=["POST"])
def host_logout():
    session.pop("host", None)
    return jsonify({"ok": True})


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
