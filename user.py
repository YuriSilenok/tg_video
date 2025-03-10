from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, BotCommand

from models import User

router = Router()

@router.message(Command('start'))
async def start(message: Message):
    user = User.get_or_none(
        tg_id=message.from_user.id
    )
    if user is None:
        User.create(
            tg_id=message.from_user.id,
            username=message.from_user.username,
        )
    elif user.username != message.from_user.username:
        user.username = message.from_user.username
        user.save()

    await message.bot.set_my_commands(
        commands=[
            BotCommand(
                command='/bloger_on',
                description='Хочу записать видео'
            ),
            BotCommand(
                command='/bloger_off',
                description='Не хочу записывать видео'
            ),
            BotCommand(
                command='/courses',
                description='Список незавершенных курсов'
            ),
        ]
    )
    await message.answer(
        text = (
            "Здравствуйте, воспользуйтесь командами, для участия в кружке видеоблогеров\n"
            "/bloger_on - Хочу записать видео\n"
            "/bloger_off - Не хочу записывать видео\n"
            "/courses - Показать список курсов\n"
        )
    )