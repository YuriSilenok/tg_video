from datetime import datetime, timedelta
import functools
from typing import List, Union
from aiogram import Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import BaseFilter

from models import Course, Task, Theme, User, UserCourse, Role, UserRole
from peewee import fn, JOIN

class IsUser(BaseFilter):
    async def __call__(self, subject: Union[Message, CallbackQuery]):
        user = User.get_or_none(
            tg_id=subject.from_user.id
        )
        if user is None:
            await subject.answer(
                text='Пользователь не зарегистрирован, отправьте команду /start'
            )
        return user is not None

def get_id(text):
    return int(text[(text.rfind('_')+1):])

async def get_user(bot: Bot, tg_id: int) -> User:
    user = User.get_or_none(tg_id=tg_id)
    if user is None:
        await bot.send_message(
            chat_id=tg_id,
            text='Пользователь не найден, ведите команду /start'
        )
    return user

def get_due_date(hours:int):
    due_date = datetime.now()
    due_date = datetime(
        year=due_date.year,
        month=due_date.month,
        day=due_date.day,
        hour=due_date.hour,
    )
    due_date += timedelta(
        hours=hours
    )
    return due_date
