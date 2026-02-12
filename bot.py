import os
from datetime import datetime
from openpyxl import Workbook, load_workbook

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("BOT_TOKEN")


# ---------- клавиатура ----------
def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["📖 Показать записи"],
            ["📥 Скачать Excel", "🧹 Очистить файл"],
            ["❌ Удалить строку"],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


# ---------- файл дня ----------
def get_today_filename():
    return f"data_{datetime.now().strftime('%Y-%m-%d')}.xlsx"


def ensure_file(filename):
    if not os.path.exists(filename):
        wb = Workbook()
        ws = wb.active
        ws.append(
            [
                "Дата",
                "ВСП",
                "ИНН",
                "Наименование",
                "Бумага/эл",
                "Добавил",
            ]
        )
        wb.save(filename)


# ---------- работа с Excel ----------
def append_row(filename, row):
    wb = load_workbook(filename)
    ws = wb.active
    ws.append(row)
    count = ws.max_row - 1
    wb.save(filename)
    return count


def get_rows(filename):
    wb = load_workbook(filename)
    ws = wb.active
    rows = []

    for i, r in enumerate(ws.iter_rows(min_row=2, values_only=True)):
        rows.append(f"{i+1}. {' | '.join(map(str, r[1:5]))}")

    return rows


def delete_row(filename, idx):
    wb = load_workbook(filename)
    ws = wb.active
    ws.delete_rows(idx + 1)
    wb.save(filename)


def clear_file(filename):
    wb = Workbook()
    ws = wb.active
    ws.append(["Дата", "ВСП", "ИНН", "Наименование", "Бумага/Эл", "User"])
    wb.save(filename)


# ---------- состояния ----------
WAITING_DELETE = set()


# ---------- старт ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Бот учёта сообщений.\n\n"
        "Отправь сообщение из 4 строк — оно попадёт в Excel.\n"
        "1 стр: ВСП; 2 стр: ИНН; 3 стр: наименование; 4 стр: бумага/эл",
        reply_markup=main_keyboard(),
    )


# ---------- текст ----------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    filename = get_today_filename()
    ensure_file(filename)

    # --- кнопки ---
    if text == "📥 Скачать Excel":
        await update.message.reply_document(
            open(filename, "rb"), reply_markup=main_keyboard()
        )
        return

    if text == "📖 Показать записи":
        rows = get_rows(filename)
        msg = "\n".join(rows) if rows else "Нет записей."
        await update.message.reply_text(msg, reply_markup=main_keyboard())
        return

    if text == "🧹 Очистить файл":
        clear_file(filename)
        await update.message.reply_text(
            "Файл очищен.", reply_markup=main_keyboard()
        )
        return

    if text == "❌ Удалить строку":
        WAITING_DELETE.add(update.message.from_user.id)
        await update.message.reply_text(
            "Введи номер строки для удаления:",
            reply_markup=main_keyboard(),
        )
        return

    # --- удаление строки ---
    if update.message.from_user.id in WAITING_DELETE:
        try:
            idx = int(text)
            delete_row(filename, idx)
            WAITING_DELETE.remove(update.message.from_user.id)

            await update.message.reply_text(
                f"Удалена строка {idx}.",
                reply_markup=main_keyboard(),
            )
        except:
            await update.message.reply_text(
                "Нужно число.",
                reply_markup=main_keyboard(),
            )
        return

    # --- добавление записи ---
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    if len(lines) != 4:
        await update.message.reply_text(
            f"❌ Не добавлено.\n"
            f"Получено строк: {len(lines)}\n"
            f"Нужно: 4",
            reply_markup=main_keyboard(),
        )
        return

    username = (
        update.message.from_user.username
        or update.message.from_user.full_name
    )

    count = append_row(
        filename,
        [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), *lines, username],
    )

    rows = "\n".join(get_rows(filename))

    await update.message.reply_text(
        f"Добавлено. Всего строк: {count}\n\n{rows}",
        reply_markup=main_keyboard(),
    )


# ---------- запуск ----------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT, handle))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
