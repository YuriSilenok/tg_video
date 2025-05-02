"""Логика для работы с моделью Role"""
from typing import Set
from models import Role, UserRole, User


def select_users_where_role(role: Role) -> Set[User]:
    '''Список пользователей у которых есть роль блогера'''
    return {
        user_role.user for user_role in
        UserRole
        .select(UserRole.user)
        .where(UserRole.role == role)
        .execute()
    }
