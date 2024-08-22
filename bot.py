import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher.filters import Text
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
import sqlite3
from contextlib import contextmanager
from datetime import datetime

API_TOKEN = '7167037752:AAFxCLPZi_qCyyIafYkZq4c4AtOPD6YBM9U'

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot and dispatcher
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Database setup
conn = sqlite3.connect('finances.db', check_same_thread=False)
cursor = conn.cursor()

# Create a table for user data including phone numbers and registration dates
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    phone_number TEXT,
    registered DATE DEFAULT (date('now'))
)''')

# Create a table for financial transactions which includes both income and expenses
cursor.execute('''
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount REAL,
    type TEXT,  -- 'income' or 'expense'
    category TEXT,
    date DATE DEFAULT (date('now'))
)''')

# Commit changes and close the connection to the database
conn.commit()
conn.close()

@contextmanager
def get_db_connection():
    conn = sqlite3.connect('finances.db', check_same_thread=False)
    try:
        yield conn.cursor()
    finally:
        conn.commit()
        conn.close()

@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    with get_db_connection() as cursor:
        cursor.execute('SELECT phone_number FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
    if user and user[0]:
        await message.reply("Welcome back!\n"
                            "Commands:\n/add_income amount category - Add income\n"
                            "/add_expense amount category - Add expense\n"
                            "/report - Show summary of income and expenses\n"
                            "/day - Today's financial summary\n"
                            "/month - This month's financial summary\n"
                            "/year - This year's financial summary")
    else:
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        button_phone = KeyboardButton(text="Send phone number", request_contact=True)
        markup.add(button_phone)
        await message.reply("Welcome! Please register by sharing your phone number.", reply_markup=markup)
# Handler to register user phone number
@dp.message_handler(content_types=['contact'])
async def handle_contact(message: types.Message):
    if message.from_user.id == message.contact.user_id:  # Ensures that the contact is the user's own
        phone_number = message.contact.phone_number
        user_id = message.from_user.id

        # Use the context manager for database operations
        with get_db_connection() as cursor:
            cursor.execute('INSERT OR IGNORE INTO users (user_id, phone_number) VALUES (?, ?)', (user_id, phone_number))

        await message.reply("Thank you for registering!\n"
                            "Commands:\n/add_income amount category - Add income\n"
                            "/add_expense amount category - Add expense\n"
                            "/report - Show summary of income and expenses\n"
                            "/day - Today's financial summary\n"
                            "/month - This month's financial summary\n"
                            "/year - This year's financial summary", reply_markup=ReplyKeyboardRemove())
    else:
        await message.reply("Please send your own contact.", reply_markup=ReplyKeyboardRemove())

@dp.message_handler(commands=['add_income'])
async def add_income(message: types.Message):
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("Please use the format: /add_income amount category\n\n"
                            "Example: /add_income 1800000 SMM")
        return
    amount, category = args
    try:
        amount = float(amount)
        # Using the context manager to ensure proper database handling
        with get_db_connection() as cursor:
            cursor.execute('INSERT INTO transactions (user_id, amount, type, category) VALUES (?, ?, "income", ?)',
                           (message.from_user.id, amount, category))
        await message.reply("Income added successfully!")
    except ValueError:
        await message.reply("Amount must be a number.")

@dp.message_handler(commands=['add_expense'])
async def add_expense(message: types.Message):
    args = message.get_args().split()
    if len(args) != 2:
        await message.reply("Please use the format: /add_expense amount category\n\n"
                            "Example: /add_expense 12000 Taxi")
        return
    amount, category = args
    try:
        amount = float(amount)
        with get_db_connection() as cursor:
            cursor.execute('INSERT INTO transactions (user_id, amount, type, category) VALUES (?, ?, "expense", ?)',
                           (message.from_user.id, amount, category))
        await message.reply("Expense added successfully!")
    except ValueError:
        await message.reply("Amount must be a number.")


@dp.message_handler(commands=['report'])
async def report(message: types.Message):
    with get_db_connection() as cursor:
        cursor.execute('''SELECT type, SUM(amount) FROM transactions WHERE user_id = ? GROUP BY type''',
                       (message.from_user.id,))
        results = cursor.fetchall()
    income = sum(amount for (type_, amount) in results if type_ == 'income')
    expense = sum(amount for (type_, amount) in results if type_ == 'expense')
    balance = income - expense
    response = f"Total Income: {income}\nTotal Expenses: {expense}\nBalance: {balance}"
    await message.reply(response)


# Handler to calculate expenses for today
@dp.message_handler(commands=['day', 'month', 'year'])
async def financial_summary(message: types.Message):
    period = message.get_command().lstrip('/')
    if period == 'day':
        date_filter = "date = date('now')"
    elif period == 'month':
        date_filter = "strftime('%Y-%m', date) = strftime('%Y-%m', 'now')"
    elif period == 'year':
        date_filter = "strftime('%Y', date) = strftime('%Y', 'now')"

    with get_db_connection() as cursor:
        cursor.execute(f'''SELECT type, category, SUM(amount) FROM transactions 
                           WHERE user_id = ? AND {date_filter}
                           GROUP BY type, category ORDER BY type, SUM(amount) DESC''', (message.from_user.id,))
        results = cursor.fetchall()

    if not results:
        await message.reply(f"No transactions recorded for this {period}.")
        return

    # Prepare the response
    response = f"{period.capitalize()}'s summary:\n"
    current_type = None
    for type_, category, amount in results:
        if current_type != type_:
            if current_type is not None:
                response += "\n"
            response += f"Total {type_.capitalize()}s:\n"
            current_type = type_
        response += f" - {category}: {amount:.2f}\n"

    total_income = sum(amount for (type_, category, amount) in results if type_ == 'income')
    total_expense = sum(amount for (type_, category, amount) in results if type_ == 'expense')
    balance = total_income - total_expense

    response += f"\nTotal Income: {total_income:.2f}\nTotal Expenses: {total_expense:.2f}\nBalance: {balance:.2f}"
    await message.reply(response)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
