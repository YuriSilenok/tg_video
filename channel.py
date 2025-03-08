from datetime import datetime, timedelta
from typing import List, Tuple

from aiogram import Bot, Router
from aiogram.types import Message, Poll
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from config import TG_CHANEL_ID
from models import Course, Task, Theme, Poll as MPoll, Video


router = Router()

async def send_video(bot:Bot, course:Course=None):
    video: Video = (
        Video
        .select()
        .join(Task)
        .join(Theme)
        .where(
            (Task.status == 2) & (Theme.course_id == course.id) if course else (Task.status == 2)
        )
        .order_by(
            Task.theme_id.asc(),
            Task.score.desc(),
        )
        .limit(1)
    ).first()
    if video is None:
        return
    task = video.task
    theme = task.theme
    caption = (
            f'Курс: #{theme.course.title.replace(" ", "_")}\n'
            f'Тема: <a href="{theme.url}">{theme.title}</a>'
    )
    message = await bot.send_video(
        chat_id=TG_CHANEL_ID,
        video=video.file_id,
        caption=caption,
        parse_mode='HTML',
    )
    if video.duration == 0:
        video.duration = message.video.duration
        video.save()
    task.status = 3
    task.save()

async def send_poll(bot: Bot):
    """Отправить опрос"""
    courses = (
        Course
        .select()
        .join(Theme)
        .join(Task)
        .where(Task.status==2)
        .group_by(Course.id)
        .limit(10)
    )

    if courses.count() >= 2:
        options = [c.title for c in courses]
        message: Message = await bot.send_poll(
            chat_id=TG_CHANEL_ID,
            question='Видео по какому курсу Вы хотите увидеть следующим?',
            options=options,
        )
        MPoll.create(
            message_id=message.message_id,
            poll_id=message.poll.id,
            result=str({o:0 for o in options}),
        )
        return True
    return False

def get_poll_course() -> Tuple[MPoll, Course]:
    """Получить опрос и курс из опроса"""
    yesterday = datetime.now() - timedelta(hours=23)

    # выбираем опросы которые были созданы вчера
    polls = (MPoll
        .select()
        .where(
            (MPoll.at_created < yesterday) &
            (MPoll.stop == False)
        )
    )

    for poll in polls:
        poll_result = eval(poll.result)
        course_max = max(poll_result, key=poll_result.get)
        course = Course.get_or_none(title=course_max)
        if course is None:
            print(f'ERROR: Опрос {poll.id}')
        return (poll, course)


async def loop(bot: Bot):
    """Одна итерация вызываемая из бесконечного цикла"""
    now = datetime.now()
    if now.hour >= 0:
        poll_course = get_poll_course()
        if poll_course:
            poll, course = poll_course
            await bot.stop_poll(
                chat_id=TG_CHANEL_ID,
                message_id=poll.message_id
            )
            poll.stop = True
            poll.save()

            await send_video(bot, course)
        else:
            await send_video(bot)
        # await send_poll(bot)

@router.poll()
async def poll_answer(poll: Poll):
    mpoll = MPoll.get_or_none(
        poll_id=poll.id
    )
    if mpoll is None:
        return
    
    mpoll.result = str({o.text:o.voter_count for o in poll.options})
    mpoll.save()

