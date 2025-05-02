"""Модуль фильтрации обработчиков блогера"""
from aiogram.types import Message
from filters.user import IsUser
from models import Role, UserRole, User


class IsBloger(IsUser):
    """Фильтр зарегистрированных пользователей с админской блогера"""

    role = Role.get(name='Блогер')

    async def __call__(self, message: Message) -> bool:
        """Истина, если у польователя есть роль админа"""
        is_user = await super().__call__(message)
        if not is_user:
            return False

        user_role = UserRole.get_or_none(
            user=User.get(tg_id=message.from_user.id),
            role=self.role
        )
        return user_role is not None
