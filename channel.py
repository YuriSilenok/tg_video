from datetime import datetime, timedelta
from typing import List, Tuple

from aiogram import Bot, Router
from aiogram.types import Message, Poll
from aiogram.filters import Command
from aiogram.exceptions import TelegramBadRequest

from handlers.admin import error_handler
from config import TG_CHANEL_ID
from models import Course, Task, Theme, Poll as MPoll, Video
from peewee import fn


router = Router()

@error_handler()
async def send_video(bot:Bot, video:Video=None):
    if video is None:
        return
    
    task = video.task
    theme = task.theme
    course_title = theme.course.title
    ch = [
        (" ", "_"),
        (".", ""),
        (".", ""),
        ("«", ""),
        ("»", ""),
    ]
    for ch1, ch2 in ch:
        course_title = course_title.replace(ch1, ch2)

    caption = (
            f'Курс: #{course_title}\n'
            f'Тема: <a href="{theme.url}">{theme.title}</a>'
    )
    message = await bot.send_video(
        chat_id=TG_CHANEL_ID,
        video=video.file_id,
        caption=caption,
        parse_mode='HTML',
    )
    if video.duration == 0:
        video.duration= message.video.duration
        video.save()
    task.status = 3
    task.save()

@error_handler()
async def send_poll(bot: Bot):
    """Отправить опрос"""
    themes = (Video
        .select(
            Video.id.alias('video'),
            Theme.title.alias('theme'),
            Course.title.alias('course')
        )
        .join(Task)
        .join(Theme)
        .join(Course)
        .where(Task.status==2)
        .group_by(Course.id)
        .limit(10)
    )
    
    if themes.count() >= 2:
        options = [f'{row["video"]}|{row["course"]}|{row["theme"]}'[:100] for row in themes.dicts()]
        message: Message = await bot.send_poll(
            chat_id=TG_CHANEL_ID,
            question='Видео по каким темам Вы хотите увидеть следующим?',
            options=options,
            allows_multiple_answers=True,
        )
        MPoll.create(
            message_id=message.message_id,
            poll_id=message.poll.id,
            result=str({o:0 for o in options}),
        )
        return True
    return False


def get_poll_theme() -> Tuple[MPoll, Video]:
    """Получить опрос и тему из опроса"""

    # выбираем опросы которые были созданы вчера
    polls = (MPoll
        .select()
        .where(
            (MPoll.stop == False)
        )
    )

    for poll in polls:
        data = sorted(eval(poll.result).items(), key=lambda kv: kv[1], reverse=True)
        for course_theme_max, _ in data:
            video_id = int(course_theme_max.split(sep='|', maxsplit=1)[0])
            video: Video = Video.get_by_id(video_id)
            if video.task.status == 2:
                return (poll, video)

@error_handler()
async def loop(bot: Bot):
    """Одна итерация вызываемая из бесконечного цикла"""

    now = datetime.now()
    if now.hour == 18 and now.minute == 0:
        poll_video = get_poll_theme()
        if poll_video:
            poll, video = poll_video
            poll.stop = True
            poll.save()
            
            try:
                await bot.stop_poll(
                    chat_id=TG_CHANEL_ID,
                    message_id=poll.message_id
                )
            except TelegramBadRequest as e:
                print(e)
            
            await send_video(bot, video)
        else:
            await send_video(bot)
    if now.hour == 8 and now.minute == 0:
        await send_poll(bot)

@router.poll()
@error_handler()
async def poll_answer(poll: Poll):
    mpoll = MPoll.get_or_none(
        poll_id=poll.id
    )
    if mpoll is None:
        return
    
    mpoll.result = str({o.text:o.voter_count for o in poll.options})
    mpoll.save()

if __name__ == '__main__':
    _, video = get_poll_theme()
    print(video.task.theme.link)
