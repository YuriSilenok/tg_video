from datetime import datetime, timedelta
from typing import List
from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from common import get_due_date, get_user
from models import TASK_STATUS, Course, Role, Task, Theme, User, UserCourse, UserRole, Video
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



@router.message(Command('show_courses'))
async def show_courses(message: Message):
    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    
    user_role = await get_admin_user_role(message.bot, user)
    if not user_role:
        return

    # Подсчет количества тем в каждом курсе с разбивкой по статусу задачи
    task_counts = (
        Task.select(
            Theme.course,
            Task.status,
            fn.COUNT(Task.id).alias("task_count")
        )
        .join(Theme)
        .group_by(Theme.course, Task.status)
    )

    # Подсчет количества тем в каждом курсе, у которых нет задач
    themes_without_tasks = (
        Theme.select(
            Theme.course,
            fn.COUNT(Theme.id).alias("no_task_count")
        )
        .where(~Theme.id.in_(Task.select(Task.theme).group_by(Task.theme)))  # Темы без задач
        .group_by(Theme.course)
    )

    # Собираем количество задач по статусу
    task_count_dict = {}
    for row in task_counts.dicts():
        course_id = row["course"]
        status = row["status"]
        count = row["task_count"]
        if course_id not in task_count_dict:
            task_count_dict[course_id] = {s: 0 for s in [-2, -1, 0, 1, 2, 3]}
        task_count_dict[course_id][status] = count

    # Собираем количество тем без задач
    no_task_count_dict = {row["course"]: row["no_task_count"] for row in themes_without_tasks.dicts()}

    # Запрос списка курсов
    # courses = Course.select().dicts()

    # Формируем финальный результат
    result = '\n\n'.join(
        [''.join([
            f'{course.title}\n',
            *[f'{i}={task_count_dict.get(course.id, {i:0})[i]}'.ljust(5, ' ') for i in [-2, -1, 0, 1, 2, 3]],
            f'no={no_task_count_dict.get(course.id, 0)}',
        ]) for course in Course.select()]
    )
    # for course in courses:
    #     course_id = course["id"]
    #     course["task_counts"] = task_count_dict.get(course_id, {s: 0 for s in [-2, -1, 0, 1, 2, 3]})
    #     course["no_task_count"] = no_task_count_dict.get(course_id, 0)
    #     results.append(course)

    # Вывод результата
    print(result)



    await message.answer(
        text=result
    )
    
@router.message(Command('show_themes'))
async def show_themes(message: Message):
    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    
    user_role = await get_admin_user_role(message.bot, user)
    if not user_role:
        return

    course_title = message.text.split(maxsplit=1)[1].strip()
    course = Course.get_or_none(
        title=course_title
    )
    if course is None:
        await message.answer(
            text='Курс с таким названием не найден'
        )
        return
    
    query = (
        Theme
        .select(
            Theme.title,
            fn.MAX(Task.status).alias('status_max')
        )
        .join(
            Task,
            JOIN.LEFT_OUTER,
        )
        .where(
            Theme.course_id==course.id
        )
        .group_by(
            Theme.id
        )
    )

    result = (
        '\n\n'.join([
            f'{i.title}\n{"Не выдавалась" if i.status_max is None else TASK_STATUS[i.status_max]}' for i in query
        ])
    )

    print(query.sql()[0])

    # for row in query.dicts():
    #     print(row)
    
    # # Подсчет количества тем в каждом курсе с разбивкой по статусу задачи
    # task_counts = (
    #     Task.select(
    #         Theme.id.alias("theme_id"),
    #         Task.status,
    #         fn.COUNT(Task.id).alias("task_count")
    #     )
    #     .join(Theme)
    #     .where(Theme.course_id == course.id)
    #     .group_by(Theme.id, Task.status)
    # )

    # # Подсчет количества тем в каждом курсе, у которых нет задач
    # themes_without_tasks = (
    #     Theme.select(
    #         Theme.id.alias("theme_id"),
    #         fn.COUNT(Theme.id).alias("no_task_count")
    #     )
    #     .where(
    #         (Theme.course_id == course.id) &
    #         (~Theme.id.in_(
    #             Task
    #             .select(Task.theme)
    #             .group_by(Task.theme))))
    #     .group_by(Theme.id)
    # )

    # # Собираем количество задач по статусу
    # task_count_dict = {}
    # for row in task_counts.dicts():
    #     theme_id = row["theme_id"]
    #     status = row["status"]
    #     count = row["task_count"]
    #     if theme_id not in task_count_dict:
    #         task_count_dict[theme_id] = {s: 0 for s in [-2, -1, 0, 1, 2, 3]}
    #     task_count_dict[theme_id][status] = count

    # # Собираем количество тем без задач
    # no_task_count_dict = {row["theme_id"]: row["no_task_count"] for row in themes_without_tasks.dicts()}

    # # Запрос списка курсов
    # # courses = Course.select().dicts()

    # # Формируем финальный результат
    # result = '\n\n'.join(
    #     [''.join([
    #         f'{theme.title}\n',
    #         *[f'{i}={task_count_dict.get(theme.id, {i:0})[i]}'.ljust(5, ' ') for i in [-2, -1, 0, 1, 2, 3]],
    #         f'no={no_task_count_dict.get(theme.id, 0)}',
            
    #     ]) for theme in Theme.select().where(Theme.course_id==course.id)]
    # )
    # # for course in courses:
    # #     course_id = course["id"]
    # #     course["task_counts"] = task_count_dict.get(course_id, {s: 0 for s in [-2, -1, 0, 1, 2, 3]})
    # #     course["no_task_count"] = no_task_count_dict.get(course_id, 0)
    # #     results.append(course)

    # # Вывод результата
    
    print(result)
    await message.answer(
        text=result
    )
    
