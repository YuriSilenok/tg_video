from datetime import datetime, timedelta
from typing import List
from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from common import get_due_date, get_user
from models import TASK_STATUS, Course, Role, Task, Theme, User, UserCourse, UserRole, Video, ReviewRequest
from peewee import JOIN, fn


router = Router()


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


async def send_task(bot: Bot):

    # Исполнители, которые заняты
    subquery = (
        User
        .select(User.id)
        .join(Task, on=(Task.implementer == User.id))
        .where((Task.status >= 0) & (Task.status <= 1))
    )
    # print('Занятые исполнители')
    # for row in subquery.dicts():
    #     print(row)

    # Темы которые выданы, на проверке, готовы к публикации, опубликованы
    subquery2 = (
        Theme
        .select(Theme.id)
        .join(Task)
        .where(Task.status >= 0)
    )
    # print('Занятые темы')
    # for row in subquery2.dicts():
    #     print(row)


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

    # print('Исполнитель и темы')
    # for row in query.dicts():
    #     print(row)

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
                'Когда работа будет готова, вы должны отправить файл '
                'с вашим видео'
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


@router.message(Command('get_video'))
async def get_video(message: Message):
    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    
    user_role = await get_admin_user_role(message.bot, user)
    if not user_role:
        return
    
    video_id = int(message.text.split(maxsplit=1)[1].strip())
    await message.answer_video(
        video=Video.get_by_id(video_id).file_id
    )


@router.message(Command('add_task'))
async def set_implementer(message: Message):
    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    
    user_role = await get_admin_user_role(message.bot, user)
    if not user_role:
        return
    
    await send_task(message.bot)

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