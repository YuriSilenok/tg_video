"""Модуль для фильрации обработчиков зарегистрированого пользователя"""
from typing import Union

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from models import User


class IsUser(BaseFilter):
    """Фильтр пользователя с указанноым username и ФИО"""

    async def __call__(self, subject: Union[Message, CallbackQuery]):
        """Вернет истину, если пользователь указал username и ФИО"""
        user: User = User.get_or_none(
            tg_id=subject.from_user.id
        )

        if user is None:
            user = User.create(
                tg_id=subject.from_user.id,
                username=subject.from_user.username,
            )

        if subject.from_user.username is None:
            return False

        if subject.from_user.username != user.username:
            user.username = subject.from_user.username
            user.save()

        if user.comment is None:
            return False

        return True
