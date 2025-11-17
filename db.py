import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from models import Base, User

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,           # good for Render
    max_overflow=10        # prevent starvation
)

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
