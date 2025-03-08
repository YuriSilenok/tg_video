'''Бот для записи видео'''
import logging
import asyncio

from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import *
from user import router as user_router
from bloger import router as bloger_router
from admin import router as admin_router
from reviewer import router as reviewer_router
from channel import router as channel_router, loop as channel_loop

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TG_TOKEN)
dp = Dispatcher()

async def sleep():
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
    while Singletone.LOOP:
        await channel_loop(bot)
        await sleep()


async def on_startup():
    """Обертка что бы запустить параллельный процесс"""
    asyncio.create_task(loop())

async def main():
    '''Старт бота'''

    dp.startup.register(on_startup)
    
    dp.include_routers(
        user_router,
        bloger_router,
        admin_router,
        channel_router,
        reviewer_router,
    )

    await dp.start_polling(bot)

class Singletone:
    LOOP = True

if __name__ == '__main__':
    asyncio.run(main())
    Singletone.LOOP = False