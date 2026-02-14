import os
import json
from datetime import datetime
from openpyxl import Workbook, load_workbook

import yadisk

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# ================= НАСТРОЙКИ =================

SUPERUSERS = {805289423, 502894278}

DISK_FOLDER = "/SberBot"
ALLOWED_FILE = "allowed_users.json"

TMP_DIR = os.getcwd()

# ================= YANDEX DISK =================
y = yadisk.YaDisk(token=YANDEX_TOKEN)

if not y.check_token():
    raise Exception("❌ Yandex token недействителен")

if not y.exists(DISK_FOLDER):
    y.mkdir(DISK_FOLDER)

def disk_path(filename):
    return f"{DISK_FOLDER}/{filename}"

def clear_temp_files():
    for f in os.listdir(TMP_DIR):
        if f.endswith(".xlsx") or f.endswith(".json"):
            try:
                os.remove(os.path.join(TMP_DIR, f))
            except:
                pass

def download_file(filename):
    local_path = os.path.join(TMP_DIR, filename)
    if y.exists(disk_path(filename)):
        y.download(disk_path(filename), local_path)
        return True
    return False

def upload_file(filename):
    local_path = os.path.join(TMP_DIR, filename)
    y.upload(local_path, disk_path(filename), overwrite=True)

def list_disk_excels():
    files = y.listdir(DISK_FOLDER)
    return [f["name"] for f in files if f["name"].endswith(".xlsx")]

# ================= ДОСТУП =================
def load_allowed():
    if not download_file(ALLOWED_FILE):
        with open(ALLOWED_FILE, "w", encoding="utf-8") as f:
            json.dump(list(SUPERUSERS), f)
        upload_file(ALLOWED_FILE)
        return set(SUPERUSERS)

    with open(ALLOWED_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f)).union(SUPERUSERS)

def save_allowed(users):
    with open(ALLOWED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(users), f)
    upload_file(ALLOWED_FILE)

ALLOWED_USERS = load_allowed()

def has_access(user_id):
    return user_id in SUPERUSERS or user_id in ALLOWED_USERS

# ================= КЛАВИАТУРА =================
def main_keyboard(user_id):
    buttons = []
    if has_access(user_id):
        buttons += [
            ["📖 Показать записи", "📥 Скачать Excel"],
            ["🧹 Очистить файл", "❌ Удалить строку"],
            ["🗂 Архив Excel"]
        ]
    if user_id in SUPERUSERS:
        buttons += [["👑 Управление доступом"]]

    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, is_persistent=True)

# ================= EXCEL =================
def get_today_filename():
    return f"data_{datetime.now().strftime('%Y-%m-%d')}.xlsx"

def ensure_file(filename):
    if not download_file(filename):
        wb = Workbook()
        ws = wb.active
        ws.append(["Дата", "ВСП", "ИНН", "Наименование", "Бумага/эл", "Добавил"])
        wb.save(filename)
        upload_file(filename)

def append_row(filename, row):
    download_file(filename)
    wb = load_workbook(filename)
    ws = wb.active
    ws.append(row)
    count = ws.max_row - 1
    wb.save(filename)
    upload_file(filename)
    clear_temp_files()
    return count

def get_rows(filename):
    if not download_file(filename):
        return []
    wb = load_workbook(filename)
    ws = wb.active
    rows = [
        f"{i+1}. {' | '.join(map(str, r[1:5]))}"
        for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True))
    ]
    clear_temp_files()
    return rows

def delete_row(filename, idx):
    download_file(filename)
    wb = load_workbook(filename)
    ws = wb.active
    ws.delete_rows(idx + 1)
    wb.save(filename)
    upload_file(filename)
    clear_temp_files()

def clear_file(filename):
    wb = Workbook()
    ws = wb.active
    ws.append(["Дата", "ВСП", "ИНН", "Наименование", "Бумага/эл", "User"])
    wb.save(filename)
    upload_file(filename)
    clear_temp_files()

# ================= СОСТОЯНИЯ =================
WAITING_DELETE = set()
WAITING_CLEAR_CONFIRM = set()
WAITING_ARCHIVE = {}  # user_id -> список файлов

# ================= БОТ =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.reply_text(
        "🤖 Бот учёта сообщений.\n\n"
        "Отправь сообщение из 4 строк:\n"
        "1 — ВСП\n2 — ИНН\n3 — Наименование\n4 — Бумага/эл",
        reply_markup=main_keyboard(user_id),
    )

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id

    if not has_access(user_id):
        await update.message.reply_text("❌ Нет доступа.")
        clear_temp_files()
        return

    filename = get_today_filename()
    ensure_file(filename)

    # --- Админ ---
    if user_id in SUPERUSERS:
        if text == "👑 Управление доступом":
            await update.message.reply_text("+ ID — дать доступ\n- ID — забрать доступ")
            clear_temp_files()
            return

        if text.startswith("+"):
            uid = int(text[1:].strip())
            ALLOWED_USERS.add(uid)
            save_allowed(ALLOWED_USERS)
            await update.message.reply_text(f"Доступ выдан: {uid}")
            clear_temp_files()
            return

        if text.startswith("-"):
            uid = int(text[1:].strip())
            ALLOWED_USERS.discard(uid)
            save_allowed(ALLOWED_USERS)
            await update.message.reply_text(f"Доступ забран: {uid}")
            clear_temp_files()
            return

    # --- Кнопки ---
    if text == "📖 Показать записи":
        rows = get_rows(filename)
        msg = "\n".join(rows) if rows else "Нет записей."
        await update.message.reply_text(msg, reply_markup=main_keyboard(user_id))
        clear_temp_files()
        return

    if text == "📥 Скачать Excel":
        if download_file(filename):
            with open(filename, "rb") as f:
                await update.message.reply_document(f, reply_markup=main_keyboard(user_id))
            clear_temp_files()
        return

    if text == "🧹 Очистить файл":
        WAITING_CLEAR_CONFIRM.add(user_id)
        await update.message.reply_text("Напишите ДА для подтверждения.")
        clear_temp_files()
        return

    if user_id in WAITING_CLEAR_CONFIRM:
        if text.upper() == "ДА":
            clear_file(filename)
            await update.message.reply_text("Файл очищен.")
        else:
            await update.message.reply_text("Файл не очищен.")
        WAITING_CLEAR_CONFIRM.discard(user_id)
        clear_temp_files()
        return

    if text == "❌ Удалить строку":
        WAITING_DELETE.add(user_id)
        await update.message.reply_text("Введите номер строки:")
        clear_temp_files()
        return

    if user_id in WAITING_DELETE:
        try:
            idx = int(text)
            delete_row(filename, idx)
            await update.message.reply_text(f"Удалена строка {idx}.")
        except:
            await update.message.reply_text("Введите число.")
        WAITING_DELETE.discard(user_id)
        clear_temp_files()
        return

    # --- Архив Excel ---
    if text == "🗂 Архив Excel":
        files = list_disk_excels()
        if not files:
            await update.message.reply_text("Архив пуст.")
            clear_temp_files()
            return
        WAITING_ARCHIVE[user_id] = files
        msg = "\n".join([f"{i+1}. {f}" for i, f in enumerate(files)])
        await update.message.reply_text("Список файлов:\n" + msg + "\n\nВведите номер для скачивания.")
        clear_temp_files()
        return

    if user_id in WAITING_ARCHIVE:
        try:
            idx = int(text) - 1
            files = WAITING_ARCHIVE[user_id]
            if 0 <= idx < len(files):
                fname = files[idx]
                if download_file(fname):
                    with open(fname, "rb") as f:
                        await update.message.reply_document(f, reply_markup=main_keyboard(user_id))
            else:
                await update.message.reply_text("Неверный номер файла.")
        except:
            await update.message.reply_text("Введите число.")
        WAITING_ARCHIVE.pop(user_id, None)
        clear_temp_files()
        return

    # --- Добавление записи ---
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) != 4:
        await update.message.reply_text(f"❌ Нужно 4 строки, получено {len(lines)}.")
        clear_temp_files()
        return

    username = update.message.from_user.username or update.message.from_user.full_name
    count = append_row(
        filename,
        [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *lines, username]
    )

    await update.message.reply_text(f"Добавлено. Всего строк: {count}")
    clear_temp_files()

# ================= ЗАПУСК =================
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
