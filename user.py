from typing import List
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, BotCommand

from common import IsUser
from models import ReviewRequest, User, Video, update_bloger_score_and_rating

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



@router.message(Command('report'), IsUser())
async def report(message: Message):
    user: User = User.get(tg_id=message.from_user.id)
    rev_bloger: List[ReviewRequest] = (
        ReviewRequest
        .select(ReviewRequest)
        .join(Video, on=(Video.id==ReviewRequest.video))
        .where(
            (ReviewRequest.status == 1) &
            (ReviewRequest.reviewer == user)
        )
    )
    if len(rev_bloger) > 0:
        text = ['<b>Отчёт проверяющего</b>']
        sum_score = 0
        for t in rev_bloger:
            score = t.video.duration / 1200
            text.append(
                f'{t.video.task.theme.title}:{t.video.duration}c.|{round(score, 2)} балла'
            )
            sum_score += score
        text.append(f'ИТОГ: {user.reviewer_score}')
        await message.answer(
            text='\n'.join(text),
            parse_mode='HTML',
        )

    if user.bloger_score > 0:
        await message.answer(
            text=update_bloger_score_and_rating(user)
        )