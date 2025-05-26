"""Бот для записи видео."""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from config import TG_TOKEN

from admin import router as admin_router
from bloger import loop as bloger_loop
from bloger import router as bloger_router
from channel import loop as channel_loop
from channel import router as channel_router
from common import router as common_router
from reviewer import loop as reviewer_loop
from reviewer import router as reviewer_router
from user import router as user_router

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TG_TOKEN)
dp = Dispatcher()


async def sleep():
    """Рассчитывает время до следующего часа и приостанавливает выполнение."""
    now = datetime.now()
    sleep_seconds = datetime(
        year=now.year,
        month=now.month,
        day=now.day,
        hour=now.hour,
    ) + timedelta(hours=1)
    sleep_seconds = (sleep_seconds - now).seconds + 1
    await asyncio.sleep(sleep_seconds)


async def loop():
    """Основной цикл выполнения задач."""
    while Singleton.LOOP:
        asyncio.create_task(channel_loop(bot))
        asyncio.create_task(reviewer_loop(bot))
        asyncio.create_task(bloger_loop(bot))
        await sleep()


async def on_startup():
    """Обертка для запуска параллельного процесса."""
    asyncio.create_task(loop())


async def main():
    """Старт бота."""

    dp.startup.register(on_startup)

    dp.include_routers(
        channel_router,
        user_router,
        bloger_router,
        reviewer_router,
        admin_router,
        common_router,
    )

    await dp.start_polling(bot)


class Singleton:
    """Класс для хранения глобального состояния."""
    LOOP = True


if __name__ == "__main__":
    asyncio.run(main())
    Singleton.LOOP = False
