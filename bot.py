import os
import json
import hmac
import hashlib
import threading
from urllib.parse import parse_qsl

from flask import Flask, request, jsonify, send_from_directory
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBAPP_URL = os.getenv("WEBAPP_URL", "")  # Example: https://your-domain.com

if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN environment variable.")
if not WEBAPP_URL.startswith("https://"):
    raise RuntimeError("Set WEBAPP_URL to your HTTPS Web App URL.")

app = Flask(__name__, static_folder="web")

def verify_init_data(init_data: str):
    """Verify Telegram Web App initData and return the authenticated user."""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(pairs.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        calculated = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated, received_hash):
            return None

        user = json.loads(pairs.get("user", "{}"))
        return user if user.get("id") else None
    except Exception:
        return None

@app.get("/")
def index():
    return send_from_directory("web", "index.html")

@app.post("/api/upload")
def upload():
    init_data = request.form.get("initData", "")
    user = verify_init_data(init_data)
    if not user:
        return jsonify(ok=False, error="Invalid Telegram session."), 401

    kind = request.form.get("kind", "file")
    caption = request.form.get("caption", "")
    media = request.files.get("media")

    if not media:
        return jsonify(ok=False, error="No media received."), 400

    chat_id = user["id"]
    filename = media.filename or "capture"

    # Send the user-consented capture directly to their Telegram chat.
    import requests
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    files = {"document": (filename, media.stream, media.mimetype or "application/octet-stream")}
    data = {"chat_id": str(chat_id), "caption": caption[:1024]}
    r = requests.post(url, files=files, data=data, timeout=60)

    if not r.ok:
        return jsonify(ok=False, error="Telegram upload failed."), 502

    return jsonify(ok=True, kind=kind)

@app.post("/api/location")
def location():
    init_data = request.form.get("initData", "")
    user = verify_init_data(init_data)
    if not user:
        return jsonify(ok=False, error="Invalid Telegram session."), 401

    lat = request.form.get("lat")
    lon = request.form.get("lon")
    if not lat or not lon:
        return jsonify(ok=False, error="Missing coordinates."), 400

    import requests
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendLocation"
    r = requests.post(
        url,
        data={"chat_id": str(user["id"]), "latitude": lat, "longitude": lon},
        timeout=30
    )
    if not r.ok:
        return jsonify(ok=False, error="Telegram location send failed."), 502

    return jsonify(ok=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("📸 Open Camera", web_app=WebAppInfo(url=WEBAPP_URL))
    ],[
        InlineKeyboardButton("👤 Profile", callback_data="profile")
    ]]
    await update.message.reply_text(
        "📸 ALI CAMERA BOT\n\n"
        "Camera, microphone and location tools work only after you "
        "explicitly grant the relevant permission.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    username = f"@{u.username}" if u.username else "No username"
    await update.message.reply_text(
        f"👤 Profile\n\n"
        f"Name: {u.full_name}\n"
        f"Username: {username}\n"
        f"Telegram ID: {u.id}"
    )

async def webapp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Open the permission-based camera Web App:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("Open Web App 📸", web_app=WebAppInfo(url=WEBAPP_URL))
        ]])
    )

def run_web():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")), threaded=True)

def main():
    threading.Thread(target=run_web, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("webapp", webapp))
    application.run_polling()

if __name__ == "__main__":
    main()
