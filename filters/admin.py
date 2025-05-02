"""Модуль фиьтрации админа"""
from aiogram.types import Message
from filters.user import IsUser
from models import User, UserRole, Role


class IsAdmin(IsUser):
    """Фильтр зарегистрированных пользователей с админской ролью"""

    role = Role.get(name='Админ')

    async def __call__(self, message: Message) -> bool:
        """Иистина если пользователь имеет роль админа"""
        is_user = await super().__call__(message)
        if not is_user:
            return False

        user_role = UserRole.get_or_none(
            user=User.get(tg_id=message.from_user.id),
            role=self.role
        )
        return user_role is not None
