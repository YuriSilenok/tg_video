from typing import Union
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from models import *

class IsUser(BaseFilter):
    async def __call__(self, subject: Union[Message, CallbackQuery]):

        user: User = User.get_or_none(
            tg_id=subject.from_user.id
        )

        if user is None:
            user = User.create(
                tg_id=subject.from_user.id,
                username=subject.from_user.username,
            )

        if subject.from_user.username is None:
            await subject.answer(
                text='У Вас не задан username, '
                'для продолжения работы с ботом, укажите его в своём профиле'
            )
            return False
        
        if subject.from_user.username != user.username:
            user.username = subject.from_user.username
            user.save()

        if user.comment is None:
            await subject.answer(
                text = (
                    "Представьтесь, указав свои ФИО. "
                    "Отправьте команду в следующем формате "
                    "<b>/set_fio Иванов Иван Иванович</b>"
                ),
                parse_mode='HTML',
            )
            return False

        return user is not None


class IsAdmin(IsUser):

    role = Role.get(name='Админ')    

    async def __call__(self, message: Message) -> bool:
        is_user = await super().__call__(message)
        if not is_user:
            return False

        user_role = UserRole.get_or_none(
            user=User.get(tg_id=message.from_user.id),
            role=self.role
        )
        return user_role is not None


class IsBloger(IsUser):

    role = Role.get(name='Блогер')    

    async def __call__(self, message: Message) -> bool:
        is_user = await super().__call__(message)
        if not is_user:
            return False

        user_role = UserRole.get_or_none(
            user=User.get(tg_id=message.from_user.id),
            role=self.role
        )
        return user_role is not None


class WaitVideo(BaseFilter):
    """Ожидает получение видео по задаче"""

    async def __call__(self, message: Message) -> bool:
        user = User.get(tg_id=message.from_user.id)
        task = Task.get_or_none(
            implementer=user,
            status=0
        )
        return task is not None


class IsReviewer(IsUser):
    """Проверяет что польователь проверяющий"""

    role = Role.get(name='Проверяющий')    

    async def __call__(self, message: Message) -> bool:
        is_user = await super().__call__(message)
        if not is_user:
            return False

        user_role = UserRole.get_or_none(
            user=User.get(tg_id=message.from_user.id),
            role=self.role
        )
        return user_role is not None


class IsReview(IsReviewer):
    """Проверяет что у проверяющего есть задача"""
    async def __call__(self, message: Message) -> bool:
        check = await super().__call__(message)
        if not check:
            return False
        
        if not isinstance(message, Message):
            return False
        
        user = User.get(tg_id=message.from_user.id)
        rr = (
            ReviewRequest
            .select(ReviewRequest)
            .where(
                (ReviewRequest.reviewer==user) &
                (ReviewRequest.status==0)
            )
            .first()
        )
        return rr is not None

