from datetime import datetime, timedelta
from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from common import get_due_date
from config import ADMIN_ID
from models import Course, Task, Theme, User, UserCourse
from peewee import JOIN, fn


router = Router()

async def send_task(bot: Bot):
    # subquery = (
    #     Course
    #     .select(Course.id)
    #     .join(Theme, on=(Theme.course == Course.id))
    #     .join(Task, JOIN.LEFT_OUTER, on=(Task.theme == Theme.id))
    #     .where((Task.status < 0) | (Task.status.is_null()))
    #     .group_by(Course.id)
    # )
    subquery2 = (
        User
        .select(User.id)
        .join(Task, on=(Task.implementer == User.id))
        .where((Task.status >= 0) & (Task.status <= 1))
    )

    query = (
        User
        .select(
            User.id.alias('user_id'),
            Course.id.alias('course_id'),
            # Theme.title,
            # Task.implementer,
        )
        .join(UserCourse, on=(UserCourse.user == User.id))
        .join(Course, on=(UserCourse.course == Course.id))
        .join(Theme, on=(Theme.course == Course.id))
        .switch(User)  # Переключаем контекст обратно на User
        .join(Task, JOIN.LEFT_OUTER, on=(Task.theme == Theme.id))
        .where(
            ((Task.status < 0) | (Task.status.is_null())) &
            (~(User.id << subquery2))
        )
        .group_by(User.id, Course.id)
        .order_by(User.bloger_rating.desc(), fn.AVG(Task.score).desc())
        
    )

    due_date = get_due_date(hours=73)
    user_ids = []
    course_ids = []
    table = query.dicts()
    for row in table:
        user_id = row['user_id']
        course_id = row['course_id']
        
        if (user_id in user_ids or 
            course_id in course_ids):
            continue
        
        user_ids.append(user_id)
        course_ids.append(course_id)

        theme = (
            Theme
            .select()
            .join(Course)
            .join(Task, JOIN.LEFT_OUTER, on=(Task.theme_id == Theme.id))
            .where(
                (Course.id == course_id) &
                (
                    (Task.status.is_null()) |
                    (Task.status < 0)
                )
            )
            .order_by(Theme.id)
            .first()
        )
        
        user = User.get_by_id(user_id)

        task = Task.create(
            implementer=user,
            theme=theme,
            due_date=due_date
        )

        await bot.send_message(
            chat_id=user.tg_id,
            text=f'Курс: {theme.course.title}\n'
                f'Тема: {theme.title}\n'
                f'url: {theme.url}\n'
                f'Срок: {task.due_date}\n'
                'Когда работа будет готова, вы должны отправить файл '
                'с вашим видео'
        )

        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f'Тема "{theme.title}" выдана пользователю '
            f'tg_id={user.tg_id}, username=@{user.username}'
        )

        


    if len(table) == 0:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text='Нет свобоных тем'
        )


@router.message(Command('add_task'))
async def set_implementer(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer(
            text='А че это мы не админ, а пользуем админские команды?'
        )
        return
    
    await send_task(message.bot)