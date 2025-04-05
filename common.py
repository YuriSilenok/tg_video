import asyncio
from datetime import datetime, timedelta
import functools
import traceback
from typing import List, Set
from aiogram import Bot, Router
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

from peewee import fn, Case, JOIN

from filters import IsBloger, IsReviewer
from models import *


router = Router()

@router.callback_query()
async def other_callback(callback: CallbackQuery):
    await callback.message.answer(
        text='Вы совершили незарегистрированное действие, обратитесь к администратору'
    )
    user = User.get_or_none(tg_id=callback.from_user.id)
    await send_message_admins(
        bot=callback.bot,
        text=f"other_callback {user.comment}\n{callback.message.text}\n{callback.data}"
    )

@router.message()
async def other_message(message: Message):
    await message.answer(
        text='Вы совершили незарегистрированное действие, обратитесь к администратору'
    )
    user = User.get_or_none(tg_id=message.from_user.id)
    await send_message_admins(
        bot=message.bot,
        text=f"other_message {user.comment}\n{message.text}"
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
    '''Выдать задачу блогеру'''


    # Список пользователей у которых есть роль блогера 
    blogers: Set[User] = {
        user_role.user for user_role in 
        UserRole
        .select(UserRole.user)
        .where(UserRole.role==IsBloger.role.id)
    }

    # Список задач, по которым ведутся работы
    tasks: Set[Task] = set(
        Task
        .select(Task)
        .where(Task.status.in_([0,1]))
    )

    # убрать блогеров у которых идет работа над задачей
    blogers -= {
        task.implementer for task in 
        Task
        .select(Task.implementer)
        .where(Task.status.in_([0,1]))
    }
    
    # Список курсов
    courses: Set[Course] = set(Course.select())

    # Свободные курсы: убираем курсы по которым ведутся работы
    courses -= {task.theme.course for task in tasks}
    course_ids = [course.id for course in courses]


    # получаем список блогеров в порядке их рейтинга
    blogers: List[User] = sorted(blogers, key=lambda user: user.bloger_rating, reverse=True)

    # Отбираем для каждого блогера подходящий курс
    for bloger in blogers:

        # Список курсов на которые подписан блогер
        courses_by_bloger: Set[UserCourse] = {
            user_course.course for user_course in
            UserCourse
            .select()
            .where(
                (UserCourse.user==bloger.id) &
                (UserCourse.course.in_(course_ids))
            )
        }

        # Если у блогера нет подписок, то фиг ему, а не задачу
        if len(courses_by_bloger) == 0:
            continue

        # Пересечение свободных курсов и списка курсов блогера
        courses_by_bloger &= courses
        
        # Нет свободных курсов для блогера, не фартануло
        if len(courses_by_bloger) == 0:
            continue

        # Сортируем курсы в порядке убывания средней оценки
        courses_by_bloger = sorted(
            courses_by_bloger,
            key=lambda course: (
                Task
                .select(fn.AVG(Task.score))
                .join(Theme)
                .where(
                    (Theme.course == course.id) &
                    (Task.implementer == bloger.id)
                )
                .scalar()
            ),
            reverse=True
        )

        # выбранный курс для блогера
        course_by_bloger: Course = courses_by_bloger[0]
        
        # Список тем этого курса
        themes: Set[Theme] = set(Theme.select().where(Theme.course==course_by_bloger.id))

        # Убираем из списка темы, по которым ведутся или удачно закончены работы
        themes -= {
            theme for theme in
            Theme
            .select()
            .join(Task)
            .where(
                (Task.status >= 0) &
                (Theme.course == course_by_bloger.id)
            )
        }

        # Сортируем тыме по ID
        themes: List[Theme] = sorted(themes, key=lambda theme: theme.id)

        # Тема для блогера
        theme_by_bloger: Theme = themes[0]

        hours = int(theme_by_bloger.complexity * 72 + 1)
        if hours < 72:
            hours = 72

        task_by_bloger: Task = Task.create(
            implementer=bloger,
            theme=theme_by_bloger,
            due_date=get_date_time(hours=hours)
        )

        try:
            await bot.send_message(
                chat_id=bloger.tg_id,
                text=f'Вам выдана тема {theme_by_bloger.link}.\n'
                f'Срок: {task_by_bloger.due_date}',
                parse_mode='HTML'
            )
        except TelegramBadRequest as ex:
            await send_message_admins(
                bot=bot,
                text=str(ex)
            )
        
        await send_message_admins(
            bot=bot,
            text=f'Блогеру {bloger.link} выдана тема {theme_by_bloger.link}',
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
        if video_ids:
            video_id = video_ids[0]
            await add_reviewer(bot, Video.get_by_id(video_id))
            await send_new_review_request(bot)



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
            text=(
                f'<b>Закончились cвободные проверяющие</b>'
                f'{theme.course.title}|{theme.link}'
            )
        )
        return
    else:
        # те кто уже работали над видео
        reviewer_ids = [ rr.reviewer_id for rr in
            ReviewRequest
            .select(ReviewRequest.reviewer)
            .join(Video, on=(Video.id == ReviewRequest.video))
            .join(Task, on=(Task.id == Video.task))
            .where(Task.theme == video.task.theme_id)
            .group_by(ReviewRequest.reviewer)
        ]

        candidat_reviewer_ids = [i for i in vacant_reviewer_ids if i not in reviewer_ids]
        if len(candidat_reviewer_ids) == 0:

            theme = Video.get_by_id(video_id).task.theme
            await send_message_admins(
                bot=bot,
                text=(
                    f'<b>Нет кандидатов среди свободных проверяющих</b>'
                    f'{theme.course.title}|{theme.link}'
                )
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



def update_task_score(task: Task) -> Task:

    task_scores = [review.score for review in 
        Review
        .select(Review)
        .join(ReviewRequest)
        .join(Video)
        .join(Task)
        .where(Task.id==task.id)
    ]

    if len(task_scores) == 0:
        return task

    task_score = sum(task_scores) / len(task_scores) / 5
    data = [
        t.score for t in 
        Task
        .select(Task.score)
        .where(Task.status.not_in([0, 1, -1]))
        .order_by(Task.id.desc())
        .limit(100)
    ]
    limit_score = sum(data)/len(data)

    task.score = task_score
    task.status = 2 if task_score >= limit_score else -2
    task.save()

    return task


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


if __name__ == '__main__':
    data = [
        t.score for t in 
        Task
        .select(Task.score)
        .where(Task.status.not_in([0,1,-1]))
        .order_by(Task.id.desc())
        .limit(100)
    ]
    print(sum(data)/len(data))


