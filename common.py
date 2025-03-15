from datetime import datetime, timedelta
from typing import List
from aiogram import Bot
from admin import send_message_admins
from models import Course, Task, Theme, User, UserCourse, Role, UserRole
from peewee import fn, JOIN


def get_id(text):
    return int(text[(text.rfind('_')+1):])

async def get_user(bot: Bot, tg_id: int) -> User:
    user = User.get_or_none(tg_id=tg_id)
    if user is None:
        await bot.send_message(
            chat_id=tg_id,
            text='Пользователь не найден, ведите команду /start'
        )
    return user

def get_due_date(hours:int):
    due_date = datetime.now()
    due_date = datetime(
        year=due_date.year,
        month=due_date.month,
        day=due_date.day,
        hour=due_date.hour,
    )
    due_date += timedelta(
        hours=hours
    )
    return due_date

async def send_task(bot: Bot):

    # Исполнители, которые заняты
    subquery = (
        User
        .select(User.id)
        .join(Task, on=(Task.implementer == User.id))
        .where((Task.status >= 0) & (Task.status <= 1))
    )

    # Темы которые выданы, на проверке, готовы к публикации, опубликованы
    subquery2 = (
        Theme
        .select(Theme.id)
        .join(Task)
        .where(Task.status >= 0)
    )

    # Курсы по которым ведутся работы
    subquery3 = (
        Course
        .select(Course.id)
        .join(Theme)
        .join(Task)
        .where(
            (Task.status==0) |
            (Task.status==1)
        )
        .group_by(Course)
    )


    query = (
        User
        .select(
            User.id.alias('user_id'),
            Course.id.alias('course_id'),
            fn.MIN(Theme.id).alias('theme_id')
            # Theme.title,
            # Task.implementer,
        )
        .join(UserCourse)
        .join(Course)
        .join(Theme)
        .join(Task, JOIN.LEFT_OUTER, on=(Task.theme_id==Theme.id))
        .where(
            (~(Theme.id << subquery2)) &
            (~(User.id << subquery)) &
            (~(Course.id << subquery3))
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
        theme_id = row['theme_id']
        
        if (user_id in user_ids or 
            course_id in course_ids):
            continue
        user_ids.append(user_id)
        course_ids.append(course_id)

        theme = Theme.get_by_id(theme_id)
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
                'Когда работа будет готова, вы должны отправить ваше видео'
        )
        
        await send_message_admins(
                    bot=bot,
                    text=f'''<b>Блогер получил тему</b>
Блогер: {task.implementer.comment}
Курс: {theme.course.title}
Тема: {theme.title}'''
                )



    if len(table) == 0:
        admins: List[User] = (
            User
            .select()
            .join(UserRole)
            .join(Role)
            .where(Role.name=='Админ')
        )
        for admin in admins:
            await bot.send_message(
                chat_id=admin.tg_id,
                text='Нет свобоных тем или блогеров'
            )