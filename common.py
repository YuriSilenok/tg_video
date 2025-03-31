from datetime import datetime, timedelta
import functools
import traceback
from typing import List
from aiogram import Bot, Router
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from peewee import fn, Case, JOIN

from models import *


router = Router()

@router.message()
async def other_message(message: Message):
    await message.answer(
        text='Вы совершили незарегистрированное действие, обратитесь к администратору'
    )

@router.callback_query()
async def other_callback(callback: CallbackQuery):
    await callback.message.answer(
        text='Вы совершили незарегистрированное действие, обратитесь к администратору'
    )

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

def get_date_time(hours:int=0):
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



def error_handler():
    """Декоратор для обработки ошибок в хэндлерах и отправки сообщения админу"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                traceback.print_exc()
                if len(args) == 0:
                    return None
                bot: Bot = None
                message: Message = None
                if isinstance(args[0], Message) or isinstance(args[0], CallbackQuery):
                    bot = args[0].bot
                    message = args[0]
                elif isinstance(args[0], Bot):
                    bot = args[0]
                
                if bot is None:
                    return None
                 
                error_text = (f'🚨{traceback.format_exc()}')
                # Отправляем сообщение админу
                try:
                    await send_message_admins(
                        bot=bot,
                        text=error_text
                    )
                except TelegramAPIError:
                    print("Не удалось отправить сообщение админу.")
                
                if message:
                    await message.answer(
                        text="❌ Произошла ошибка. Администратор уже уведомлён."
                    )
        return wrapper
    return decorator


@error_handler()
async def send_task(bot: Bot):
    # Исполнители, которые заняты
    subquery = (
        User
        .select(User.id)
        .join(Task, on=(Task.implementer == User.id))
        .where(Task.status.between(0, 1))
    )

    # Темы которые выданы, на проверке, готовы к публикации, опубликованы
    subquery2 = (
        Theme
        .select(Theme.id)
        .join(Task)
        .where(Task.status >= 0)
    )

    # Подстчет средних оценко у блогеров по каждому курсу
    subquery3 = (
        Task
        .select(
            Task.implementer.alias('user_id'),
            Theme.course.alias('course_id'),
            fn.AVG(Task.score).alias('score'),
        )
        .join(Theme)
        .group_by(Task.implementer, Theme.course)
    )

    subquery4 = (
        Theme
        .select(Theme.course)
        .join(Task)
        .where(Task.status.between(0, 1))
        .group_by(Theme.course)
    )

    bloger_role = Role.get(name='Блогер')

    query = (
        User
        .select(
            User.id.alias('user_id'),
            Course.id.alias('course_id'),
            fn.MIN(Theme.id).alias('theme_id')
        )
        .join(UserRole, on=(User.id==UserRole.user))
        .join(UserCourse, on=(User.id==UserCourse.user))
        .join(Course, on=(Course.id==UserCourse.course))
        .join(Theme, on=(Theme.course==Course.id))
        .join(
            subquery3,
            JOIN.LEFT_OUTER,
            on=( # ucs.user_id=user.id and ucs.course_id=course.id
                (subquery3.c.user_id==User.id) &
                (subquery3.c.course_id==Course.id)
            )
        )
        .where(
            (~(Theme.id << subquery2)) &
            (~(User.id << subquery)) &
            (~(Course.id << subquery4)) &
            (UserRole.role==bloger_role)
        )
        .group_by(User.id, Course.id)
        .order_by(
            User.bloger_rating.desc(),
            # CASE WHEN (AVG(ucs.score) IS NULL) THEN user.bloger_rating ELSE AVG(ucs.score) END DESC
            Case(None, [(fn.AVG(subquery3.c.score).is_null(), User.bloger_rating)], fn.AVG(subquery3.c.score)).desc()
        )
    )

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

        theme: Theme = Theme.get_by_id(theme_id)
        user = User.get_by_id(user_id)

        hours = int(theme.complexity*72+1)
        if hours < 72:
            hours = 72

        task = Task.create(
            implementer=user,
            theme=theme,
            due_date=get_date_time(hours=hours)
        )

        try:
            await bot.send_message(
                chat_id=user.tg_id,
                text=f'Курс: {theme.course.title}\n'
                    f'Тема: <a href="{theme.url}">{theme.title}</a>\n'
                    f'Срок: {task.due_date}\n'
                    'Когда работа будет готова, вы должны отправить ваше видео',
                parse_mode='HTML'
            )
        except TelegramBadRequest as ex:
            await send_message_admins(
                bot=bot,
                text=str(ex)
            )
        
        await send_message_admins(
            bot=bot,
            text=f'''<b>Блогер получил тему</b>
Блогер: {task.implementer.comment}
Курс: {theme.course.title}
Тема: <a href="{theme.url}">{theme.title}</a>
'''
                )


@error_handler()
async def send_message_admins(bot:Bot, text: str, reply_markup = None):
    for admin in get_admins():
        try:
            await bot.send_message(
                chat_id=admin.tg_id,
                text=text,
                parse_mode='HTML',
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
        except Exception as ex:
            print(ex)
            await bot.send_message(
                chat_id=admin.tg_id,
                text=text,
                reply_markup=reply_markup,
            )


def get_admins() -> List[User]:
    return (
        User
        .select(User)
        .join(UserRole)
        .where(UserRole.role==Role.get(name='Админ').id)
    )


@error_handler()
async def send_new_review_request(bot: Bot):
    """Выдать новый запрос на проверку"""
    # проверяющие у котых есть задачи
    reviewer_ids = [u.id for u in
        User
        .select(User)
        .join(ReviewRequest, on=(ReviewRequest.reviewer_id==User.id))
        .where(ReviewRequest.status==0)
        
    ]
    reviewer_ids_len = len(reviewer_ids)
    task_count_status_1 = (
        Task
        .select(fn.COUNT(Task.id))
        .where(Task.status == 1)
        .scalar()
    )
    if reviewer_ids_len < 5 or reviewer_ids_len < task_count_status_1:
        # видео у которых не хватает проверяющих
        video_ids = [v.id for v in 
            Video
            .select(Video)
            .join(ReviewRequest, JOIN.LEFT_OUTER, on=(ReviewRequest.video==Video.id))
            .join(Task, on=(Task.id==Video.task))
            .join(User, on=(User.id==Task.implementer))
            .where(
                (Task.status == 1) &
                ((ReviewRequest.status >= 0) |
                (ReviewRequest.status.is_null()))
            )
            .group_by(Video.id)
            .order_by(User.bloger_rating.desc())
            .having(fn.COUNT(Video.id) < 5)
        ]
        for video_id in video_ids:
            await add_reviewer(bot, Video.get_by_id(video_id))
            await send_new_review_request(bot)
            break



@error_handler()
async def add_reviewer(bot: Bot, video_id: int):
    # Свободные проверяющие
    vacant_reviewer_ids: List[int] = get_vacant_reviewer_ids()
    
    video: Video = Video.get_by_id(video_id)
    task: Task = video.task
    theme: Theme = task.theme
    
    if task.implementer_id in vacant_reviewer_ids:
        vacant_reviewer_ids.remove(task.implementer_id)
    
    if len(vacant_reviewer_ids) == 0:
        await send_message_admins(
            bot=bot,
            text=f'''<b>Закончились cвободные проверяющие</b>
Курс: {theme.course.title}
Тема: {theme.title}'''
        )
        return
    else:
        # те кто уже работали над видео
        reviewer_ids = [ rr.reviewer_id for rr in
            ReviewRequest
            .select(ReviewRequest.reviewer)
            .where(ReviewRequest.video_id==video_id)
            .group_by(ReviewRequest.reviewer)
        ]

        candidat_reviewer_ids = [i for i in vacant_reviewer_ids if i not in reviewer_ids]
        if len(candidat_reviewer_ids) == 0:
            # все проверяющие
            all_reviewer_ids = get_reviewer_ids()
            # занятые над других видео
            other_job_reviews = ', '.join([f'@{u.username}' for u in
                User
                .select(User)
                .where(
                    User.id.in_([i for i in all_reviewer_ids if i not in reviewer_ids])
                )
            ])
            

            theme = Video.get_by_id(video_id).task.theme
            await send_message_admins(
                bot=bot,
                text=f'''<b>Нет кандидатов среди свободных проверяющих</b>
Курс: {theme.course.title}
Тема: {theme.title}
Пнуть проверяющих: {other_job_reviews}
'''
            )

            return

        due_date = get_date_time(hours=25)
        review_request = ReviewRequest.create(
            reviewer_id=candidat_reviewer_ids[0],
            video_id=video_id,
            due_date=due_date
        )
        await send_video(bot, review_request)


@error_handler()
async def send_video(bot: Bot, review_request: ReviewRequest):
    
    text = f'Ваше видео на тему "{review_request.video.task.theme.link}" выдано на проверку'
    try:
        await bot.send_message(
            chat_id=review_request.video.task.implementer.tg_id,
            text=text,
            parse_mode='HTML',
            disable_web_page_preview=True,
        )
    except TelegramBadRequest as ex:
        print(ex, text)

    caption = (
        f'Это видео нужно проверить до {review_request.due_date}.\n'
        f'Тема: "{review_request.video.task.theme.course.title}|{review_request.video.task.theme.link}"\n'
        'Для оценки видео напишите одно сообщение '
        'в начале которого будет оценка в интервале [0.0; 5.0], а через пробел отзыв о видео'
    )
    try:
        await bot.send_video(
            chat_id=review_request.reviewer.tg_id,
            video=review_request.video.file_id,
            caption=caption,
            parse_mode='HTML',
        )
    except TelegramBadRequest as ex:
        print(ex, caption, sep='\n')

    await send_message_admins(
        bot=bot,
        text=f'''<b>Проверяющий получил видео</b>
Проверяющий: {review_request.reviewer.comment}
Блогер: {review_request.video.task.implementer.comment}
Курс: {review_request.video.task.theme.course.title}
Тема: {review_request.video.task.theme.title}'''
    )



def update_task_score(task: Task):

    task_score = sum([review.score for review in 
        Review
        .select(Review)
        .join(ReviewRequest)
        .join(Video)
        .join(Task)
        .where(Task.id==task.id)
    ]) / 25

    task.score = task_score
    task.status = 2 if task_score >= 0.8 else -2
    task.save()


def get_vacant_reviewer_ids() -> List[User]:
    reviewer_ids = get_reviewer_ids()
    # проверяющие у которых есть что проверить
    jobs_ids = [ u.id for u in
        User
        .select(User)
        .join(ReviewRequest)
        .where(
            (ReviewRequest.status==0)
        )
        .group_by(ReviewRequest.reviewer)
        .order_by(User.reviewer_rating)
    ]
    return [i for i in reviewer_ids if i not in jobs_ids]


def get_reviewer_ids() -> List[User]:
    """Пользователи с ролью проверяющий"""
    return [ u.id for u in
        User
        .select(User)
        .join(UserRole)
        .join(Role)
        .where(Role.name=='Проверяющий')
        .order_by(User.reviewer_rating)
    ]

