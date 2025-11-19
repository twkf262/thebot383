import os
from datetime import datetime

from sqlalchemy import (
    select,
    Column,
    Integer,
    BigInteger,
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

from fastapi import (
    FastAPI,
    Request
)
from fastapi.responses import JSONResponse

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
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
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

# ------------------ CRUD functions (async + safe) ------------------ #

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

"""
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
"""

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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Conversation cancelled.")
    return ConversationHandler.END

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

async def report_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please send me the location as an attachment or by forwarding. Only send it using the built-in location (maps) tool. Don't send me typed coordinates or What3Words.")

    if not update.message or not update.message.location:
        await update.message.reply_text("Please tap the *Share Location* button or forward me a location.")
        return

    tg_id = str(update.effective_user.id)
    tg_dt = datetime.utcfromtimestamp(update.message.date.timestamp())
    lat = update.message.location.latitude
    lon = update.message.location.longitude

#    await upsert_user(tg_id, tg_dt, latitude, longitude, )
#    await update.message.reply_text(f"Rave at coordinates: {latitude} N, {longitude} W reported.")
    
"""
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
    
    await update.message.reply_text(f"Rave at coordinates: {latitude} N, {longitude} W reported.")
    return ConversationHandler.END"""

async def report_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Report cancelled.")
    return ConversationHandler.END

report_handler = ConversationHandler(
    entry_points=[CommandHandler("report", report_start)],
    states=[MessageHandler(filters.TEXT & ~filters.COMMAND, report_get_location)],
    fallbacks=[CommandHandler("cancel", report_cancel)],
)

telegram_app.add_handler(report_handler)
