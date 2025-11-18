import os
from datetime import datetime

from fastapi import (
    FastAPI,
    Request
)
from fastapi.responses import JSONResponse

from sqlalchemy import (
    select,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    UniqueConstraint
)
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker
)

from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBSERVICE_URL")
DATABASE_URL = os.getenv("DATABASE_URL")

# ------------------ database class / table definitions ------------------ #

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    name = Column(String)
    age = Column(Integer)
    latitude = Column (Float)
    longitude = Column (Float)
# for tracking whether they have used up all their reporting opportunities for a session
    lastSubmittedTime = Column(DateTime(timezone=False))
# ditto (session foreign key)
# I don't think we need to index this?
    lastReportedSession = Column(Integer)
# persistent score based on the aggregate score of previous submissions
    score = Column(Float)

    __table_args__ = (UniqueConstraint('telegram_id', name='_telegram_user_uc'),)

# a single report from a user
class reportedLocation(Base):
    __tablename__ = "reported_locations"
    id = Column(Integer, primary_key=True)
# user foreign key
# TODO: column to be indexed so we can get all reports by a user
    submittedBy = (Integer) # primary key from users table
    submittedTime = Column(DateTime(timezone=False))
# Calculated from number of subsequent reports.
# This is just for user score generation,
# later reports dont get confidence increased as much as early ones
# even though logically they should be the same.
# Perhaps 'confidence' is a misnomer and 'score' would be better
# (although comfusable with user's aggregate score)?
    confidence = Column(Float)
    latitude = Column (Float)
    longitude = Column (Float)
# session foreign key
# TODO: column to be indexed so we can get all reports in the session
    session = Column(Integer)

# suspected location calculated from a set of reports
# may not be needed if we're just giving users 'heat maps'
class suspectedLocation(Base):
    __tablename__ = "suspected_locations"
    id = Column(Integer, primary_key=True)
    confidence = Column(Float)
    latitude = Column (Float)
    longitude = Column (Float)

# the session (interval of time) through which a set of reports is considered 'live'
class reportSession(Base):
    __tablename__ = "report_sessions"
    id = Column(Integer, primary_key=True)
    startTime = Column(DateTime(timezone=False))
    endTime = Column(DateTime(timezone=False))

# Known previous locations. For now we are just counting confirmed locations.
# Even if an event had very high confidence from user reports,
# we would only record if checked somehow
# (e.g. be there, phone the line, social media, photos or videos etc).
# Data entry via e.g. a text file (extract from Smash somehow)?
# In later versions maybe we could start integrating user reports.
class historicLocation:
    __tablename__ = "historic_locations"
    id = Column(Integer, primary_key=True)
    latitude = Column (Float)
    longitude = Column (Float)
# Known historical locations with no knowledge of specific events
# will typically be given a numberOfPrevious of 1.
    numberOfPrevious = Column (Integer)

# ------------------ database setup ------------------ #

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,           # good for Render
    max_overflow=10        # prevent starvation
)
# engine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    """Called at startup — safe and non-blocking."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# ------------------ CRUD FUNCTIONS (async + safe) ------------------ #

async def get_user_by_tg_id(tg_id: str) -> User | None:
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == tg_id)
        )
        return result.scalar_one_or_none()

"""
async def upsert_user(tg_id: str, name: str, age: int):
    async with async_session() as session:
        user = await get_user_by_tg_id(tg_id)

        if not user:
            user = User(telegram_id=tg_id, name=name, age=age)
            session.add(user)
        else:
            user.name = name
            user.age = age

        await session.commit()
        return user
"""

async def upsert_user(
    session: AsyncSession,
    telegram_id: int,
    name: str | None = None,
    age: int | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
):
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    if user:
        # Update existing
        if name is not None:
            user.name = name
        if age is not None:
            user.age = age
        if latitude is not None:
            user.latitude = latitude
        if longitude is not None:
            user.longitude = longitude
    else:
        # Insert new
        user = User(
            telegram_id=telegram_id,
            name=name,
            age=age,
            latitude=latitude,
            longitude=longitude,
        )
        session.add(user)

    await session.commit()
    await session.refresh(user)
    return user

# ------------------ bot command handlers ... /start command ------------------ #

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello world! 🎉")

telegram_app.add_handler(CommandHandler("start", start))

# ------------------ bot command handlers ... /echo command ------------------ #

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args) if context.args else "(no text)"
    await update.message.reply_text(f"Echo: {text}")

telegram_app.add_handler(CommandHandler("echo", echo))

# ------------------ bot command handlers ... /chat conversation ------------------ #

# Conversation states
ASK_NAME, ASK_AGE, ASK_LOCATION = range(3)

async def chat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hello! What is your name?")
    return ASK_NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    user_id = update.effective_user.id

    async with async_session() as session:
        await upsert_user(session, telegram_id=user_id, name=name)

    await update.message.reply_text("Got it! Now please enter your age.")
    return ASK_AGE


async def ask_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["age"] = int(update.message.text)

    # Create keyboard with location sharing button
    location_button = KeyboardButton("Share Location 📍", request_location=True)
    keyboard = ReplyKeyboardMarkup([[location_button]], resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        "Please share your location:",
        reply_markup=keyboard
    )

    return ASK_LOCATION

async def ask_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Ensure user actually shared location using Telegram UI
    if not update.message or not update.message.location:
        await update.message.reply_text("Please tap the *Share Location* button.", parse_mode="Markdown")
        return ASK_LOCATION

    lat = update.message.location.latitude
    lon = update.message.location.longitude

    user_id = update.effective_user.id

    async with async_session() as session:
        await upsert_user(
            session,
            telegram_user_id=user_id,
            latitude=loc.latitude,
            longitude=loc.longitude
        )
        
    await update.message.reply_text(
        f"Thanks, your information has been saved.\n\n"
        f"Name: {context.user_data['name']}\n"
        f"Age: {context.user_data['age']}\n"
        f"Location: ({lat}, {lon})"
    )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Conversation cancelled.")
    return ConversationHandler.END


def get_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("chat", chat_start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_age)],
            ASK_LOCATION: [
                MessageHandler(filters.LOCATION, ask_location),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_location),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

async def ask_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.location:
        await update.message.reply_text("Please tap the *Share Location* button.", parse_mode="Markdown")
        return ASK_LOCATION
        
    lat = update.message.location.latitude
    lon = update.message.location.longitude

    # Save user data to DB (async SQLAlchemy)
    async with async_session_maker() as session:
        # You may already have a user model row existing — update if so
        user = User(
            telegram_id=update.effective_user.id,
            name=context.user_data["name"],
            age=context.user_data["age"],
            latitude=lat,
            longitude=lon,
        )
        session.add(user)
        await session.commit()

    await update.message.reply_text(
        f"Thanks! Your data has been saved.\n\n"
        f"Name: {context.user_data['name']}\n"
        f"Age: {context.user_data['age']}\n"
        f"Location: ({lat}, {lon})"
    )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Conversation cancelled.")
    return ConversationHandler.END

def get_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("chat", chat_start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_age)],
            ASK_LOCATION: [
                MessageHandler(filters.LOCATION, ask_location),
                MessageHandler(filters.TEXT & ~filters.COMMAND, ask_location),  # fallback to remind user
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

telegram_app.add_handler(get_conversation_handler())

# ------------------ bot command handlers ... /profile command ------------------ #

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

# ------------------ bot command handlers ... /report conversation ------------------ #

ASK_LOCATION = 0

async def report_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please send me the location as an attachment or by forwarding. Only send it using the built-in location (maps) tool. Don't send me typed coordinates or What3Words.")
    return ASK_LOCATION

async def get_location(uprate: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = str(update.effective_user.id)
    tg_dt = datetime.utcfromtimestamp(update.message.date.timestamp())
    name = context.user_data.get("name")
    age = int(update.message.text)

    await upsert_user(tg_id, tg_dt, latitude, longitude, )

    await update.message.reply_text(f"Rave at coordinates: {latitude} N, {longitude} W reported.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Report cancelled.")
    return ConversationHandler.END

report_handler = ConversationHandler(
    entry_points=[CommandHandler("report", report_start)],
    states={
        ASK_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

telegram_app.add_handler(report_handler)

# ------------------ FastAPI setup and lifecycle events ------------------ #

# FastAPI app
app = FastAPI()

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

# ------------------ webhook ------------------ #

# Telegram bot application
telegram_app = Application.builder().token(BOT_TOKEN).build()

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
