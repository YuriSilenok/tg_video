from typing import List
from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from common import get_user
from models import Role, User, UserRole, ReviewRequest
from peewee import fn


router = Router()


def get_admins() -> List[User]:
    return (
        User
        .select(User)
        .join(UserRole)
        .join(Role)
        .where(Role.name=='Админ')
    )


async def send_message_admins(bot:Bot, text: str):
    for admin in get_admins():
        await bot.send_message(
            chat_id=admin.tg_id,
            text=text
        )


async def get_admin_user_role(bot: Bot, user: User):
    """Проверяем наличие привилегии блогера"""
    
    # Наличие роли
    role = Role.get_or_none(name='Админ')
    if role is None:
        await bot.send_message(
            chat_id=user.tg_id,
            text=(
                "Роль администратора не найдена! "
                "Это проблема администратора! "
                "Cообщите ему всё, что Вы о нем думаете. @YuriSilenok"
            )
        )
        return None
    
    # Наличие роли у пользователя
    user_role = UserRole.get_or_none(
        user=user,
        role=role,
    )
    if user_role is None:
        await bot.send_message(
            chat_id=user.tg_id,
            text='Вы не являетесь администратором!'
        )
        return None

    return user_role


@router.message(Command('report_reviewers'))
async def report_reviewers(message: Message):
    reviewers = (
        User
        .select(
            User.comment.alias('fio'),
            User.reviewer_score.alias('score'),
            fn.COUNT(ReviewRequest).alias('count')
        )
        .join(UserRole)
        .join(Role)
        .join(ReviewRequest, on=(ReviewRequest.reviewer_id==User.id))
        .where(
            (Role.name == 'Проверяющий') &
            (ReviewRequest.status == 1) # Видео проверено
        )
        .group_by(User)
    )
    result = 'Отчет о проверяющих\n\n'
    result += '\n'.join([
        f"{i['count']} {i['score']} {i['fio']}" for i in reviewers.dicts()
    ])

    await message.answer(
        text=result
    )


@router.message(Command('add_role'))
async def add_role(message: Message):
    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    
    user_role = await get_admin_user_role(message.bot, user)
    if not user_role:
        return
    
    data = message.text.strip().replace('  ', '').split()
    if len(data) != 3:
        await message.answer(
            text=' Не верное коичетво параметров. Команда, роль, юзернейм'
        )
        return
    role_name = data[2]
    role = Role.get_or_none(name=role_name)
    if role is None:
        await message.answer(
            text=f'Нет роли {role_name}'
        )
        return
    
    username = data[1].strip()
    user = User.get_or_none(username=username)
    if user is None:
        await message.answer(
            text=f'Нет пользователя с юзернейм {username}'
        )
        return
    UserRole.get_or_create(
        user=user,
        role=role
    )
    await message.answer(
        text='Роль добавлена'
    )


@router.message(Command('set_comment'))
async def set_comment(message: Message):
    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    
    user_role = await get_admin_user_role(message.bot, user)
    if not user_role:
        return
    
    data = message.text.strip().replace('  ', '').split(maxsplit=1)[1]
    data = data.split(maxsplit=1)
    username = data[0]
    user = User.get_or_none(username=username)
    if user is None:
        await message.answer(
            text='Пользователь с таким юзернейм не найден'
        )
        return

    user.comment = data[1]
    user.save()

    await message.answer(
        text='Комментарий записан'
    )