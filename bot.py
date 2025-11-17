import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from telegram.ext import ConversationHandler, MessageHandler, filters

from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import select

from db import init_db, get_user_by_tg_id, upsert_user

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
Base = declarative_base()
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True)
    name = Column(String)
    age = Column(Integer)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBSERVICE_URL")

# FastAPI app
app = FastAPI()

# Telegram bot application
telegram_app = Application.builder().token(BOT_TOKEN).build()

# ----- Telegram Start Command Handler ----- #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello world! 🎉")

telegram_app.add_handler(CommandHandler("start", start))

# ----- Echo Command ----- #

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else "(no text)"
    await update.message.reply_text(f"Echo: {text}")

telegram_app.add_handler(CommandHandler("echo", echo))

# ----- Telegram Conversation Handler ----- #

# Conversation states
ASK_NAME, ASK_AGE = range(2)

async def chat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! What's your name?")
    return ASK_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text(f"Nice to meet you, {update.message.text}! How old are you?")
    return ASK_AGE

async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    name = context.user_data.get("name")
    age = int(update.message.text)

    await upsert_user(tg_id, name, age)

    await update.message.reply_text(f"Saved! You are {name}, {age} years old 😊")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Conversation cancelled.")
    return ConversationHandler.END

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("chat", chat_start)],
    states={
        ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
        ASK_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

telegram_app.add_handler(conv_handler)

# ----- Profile Command ----- #

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    user = await get_user_by_tg_id(tg_id)

    if user:
        await update.message.reply_text(
            f"👤 Profile\n\n"
            f"Name: {user.name}\n"
            f"Age: {user.age}"
        )
    else:
        await update.message.reply_text("No profile found. Run /chat to create one.")

telegram_app.add_handler(CommandHandler("profile", profile))

# ----- FastAPI Lifecycle Events ----- #

@app.on_event("startup")
async def on_startup():
    await init_db()                              # async & safe
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/webhook")

@app.on_event("shutdown")
async def on_shutdown():
    await telegram_app.stop()
    await telegram_app.shutdown()

# ----- Webhook Route ----- #

@app.post("/webhook")
async def process_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return JSONResponse({"status": "ok"})


@app.get("/")
async def root():
    return {"message": "Bot running"}

"""
import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- Environment variables (store these on Render) ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")                 # your bot token
RENDER_URL = os.getenv("WEBSERVICE_URL")       # e.g. https://your-app.onrender.com
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}"

# --- Create FastAPI app ---
app = FastAPI()

# --- Create Telegram Bot Application ---
application = Application.builder().token(TOKEN).build()


# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello, World from FastAPI!")


application.add_handler(CommandHandler("start", start))


# --- Webhook endpoint ---
@app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, application.bot)
    asyncio.create_task(application.process_update(update))
    return {"ok": True}


# --- Initialize bot and set webhook ---
async def init_bot():
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(WEBHOOK_URL)
    print("Webhook set to:", WEBHOOK_URL)


# --- Entry point ---
if __name__ == "__main__":
    # Initialize bot before starting FastAPI
    asyncio.get_event_loop().run_until_complete(init_bot())

    # Run FastAPI via Uvicorn (Render will use $PORT)
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
"""

"""from flask import Flask, request
#from telegram import Bot
#from telegram.ext import CommandHandler, Updater, Dispatcher, Update, MessageHandler, Filters

import psycopg2, os, telegram, json, requests

app = Flask(__name__)

# This is the old 'hello world' code
#@app.route('/')
#def hello():
#    return "Hello, World!"

webhook_url_suffix = '/webhook'
webhook_url = os.getenv('WEBSERVICE_URL') + webhook_url_suffix

telegram_bot_api_url = os.getenv('TELEGRAM_API_URL') + '/bot' + os.getenv('TELEGRAM_BOT_TOKEN')

app = Flask(__name__)

# Set webhook with Telegram
def set_webhook():
    response = requests.post(telegram_bot_api_url + '/setWebhook', data={'url': webhook_url})
    if response.status_code == 200:
        print("Webhook successfully set.")
    else:
        print("Failed to set webhook.", response.text)

@app.route(webhook_url_suffix, methods=['POST'])
def webhook():
    json_str = request.get_data(as_text=True)
    update = Update.de_json(json_str, bot)
    # Handle the update (e.g., respond to the bot message)

    print(update)  # Log the incoming update for debugging

    # Get message details
    message = update.get('message')
    if message:
        chat_id = message['chat']['id']
        text = message.get('text')

        # If a message exists, echo it back
        if text:
            send_message(chat_id, text)

    return 'OK', 200

def send_message(chat_id, text):
    #Send a message back to the user.
    url = telegram_bot_api_url + '/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        print("Message sent successfully.")
    else:
        print("Failed to send message.", response.text)

if __name__ == '__main__':
    print("Main func")
    set_webhook()
    app.run(debug=True)
#    app.run(debug=True, host='0.0.0.0', port=5000)

# Replace with your bot's token
bot = telegram.Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))

# Set the webhook to Render's URL
bot.set_webhook(url=os.getenv('WEBSERVICE_URL') + webhook_url_suffix)

# Connect to the PostgreSQL database using the connection string
conn = psycopg2.connect(os.getenv('DATABASE_URL'))

# Use a cursor to interact with the database
cursor = conn.cursor()

# Example: Insert data into the database
#cursor.execute("INSERT INTO users (user_id, username) VALUES (%s, %s)", (user_id, username))
conn.commit()

# Close the connection
cursor.close()
conn.close()"""
"""
import os
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Replace with your bot token
TOKEN = '8510965294:AAHI9aKl2ik_l6BM2rVD61UR26xLgrqz8DY'

# Create Flask app
app = Flask(__name__)

# Create the Application instance for handling Telegram updates
application = Application.builder().token(TOKEN).build()

# Command handler for /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("start")
    await update.message.reply_text("Hello! I'm your Telegram bot. Send me any text and I'll echo it back!")

# Echo handler function
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("echo")
    # Echo the message back to the user
    await update.message.reply_text(update.message.text)

# Set up Flask route to handle incoming webhook requests
@app.route('/webhook', methods=['POST'])
async def webhook():
    print("webhook")
    json_str = request.get_data().decode('UTF-8')
    update = Update.de_json(json_str, application.bot)
    await application.process_update(update)
    return '', 200

# Set webhook URL for Telegram
async def set_webhook():
    print("set_webhook")
    webhook_url = 'https://thebot383.onrender.com/webhook'  # Change this to your deployed app URL
    await application.bot.set_webhook(webhook_url)

# Register command handlers and message handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))  # Echo all text messages

if __name__ == '__main__':
    print("main")
    # Set webhook when the bot starts
    import asyncio
    asyncio.run(set_webhook())

    # Gunicorn will handle serving the Flask app, no need for app.run() here
"""
