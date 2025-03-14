from datetime import datetime
from typing import List
from aiogram import Bot, Router, F
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest
from peewee import fn

from admin import get_admins, send_message_admins
from models import (
    Review, ReviewRequest, Role, User, UserRole, Video,
    update_bloger_score_and_rating, update_reviewer_score, update_reviewers_rating, 
)
from common import get_due_date, get_user


router = Router()


async def get_reviewer_user_role(bot: Bot, user: User):
    """Проверяем наличие привилегии блогера"""
    
    # Наличие роли
    role = Role.get_or_none(name='Проверяющий')
    if role is None:
        await bot.send_message(
            chat_id=user.tg_id,
            text=(
                "Роль проверяющего не найдена! "
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
            text='Вы не являетесь проверяющим!'
        )
        return None

    return user_role


async def send_video(bot: Bot, review_request: ReviewRequest):
    
    text = f'Ваше видео на тему "{review_request.video.task.theme.title}" выдано на проверку'
    try:
        await bot.send_message(
            chat_id=review_request.video.task.implementer.tg_id,
            text=text,
        )
    except TelegramBadRequest as ex:
        print(ex, text)

    caption = (
        f'Это видео нужно проверить до {review_request.due_date}.\n'
        f'Курс: "{review_request.video.task.theme.course.title}"\n'
        f'Тема: "{review_request.video.task.theme.title}"\n'
        f'url: "{review_request.video.task.theme.url}"\n'
        'Для оценки видео напишите одно сообщение '
        'в начале которого будет оценка в интервале [0.0; 5.0], '
        'а через пробел отзыв о видео'
    )
    try:
        await bot.send_video(
            chat_id=review_request.reviewer.tg_id,
            video=review_request.video.file_id,
            caption=caption
        )
    except TelegramBadRequest as ex:
        print(ex, caption, sep='\n')

    await send_message_admins(
        bot=bot,
        text=f'Пользователю @{review_request.reviewer.username} выдана тема "{review_request.video.task.theme.title}"',
    )


@router.message(F.text)
async def get_review(message:Message):
    
    user = await get_user(message.bot, message.from_user.id)
    if user is None:
        return
    
    user_role = await get_reviewer_user_role(message.bot, user)
    if not user_role:
        return
    
    """Поиск запроса на проверку"""
    review_request: ReviewRequest = ReviewRequest.get_or_none(
        reviewer=user,
        status=0 # На проверке
    )

    if review_request is None:
        await message.answer(
            text='Запрос на проверку не найден'
        )
        return

    """Валидация оценки"""
    text = message.text.strip()
    digit = text.find(' ')
    digit = text[:digit] if digit >= 0 else text
    digit = digit.replace(',', '.')
    
    try:
        digit = float(digit)
    except ValueError:
        await message.answer(
            text=f'Не удалось преобразовать {digit} в число'
        )
        return
    
    if digit < 0 or digit > 5:
        await message.answer(
            text=f'{digit} должно быть в пределах [0.0; 5.0]'
        )
        return
    
    """Фиксация отзыва"""
    Review.create(
        review_request=review_request,
        score=digit,
        comment=text,
    )
    review_request.status = 1 # Проверено
    review_request.save()
    
    update_reviewers_rating()
    new_score = update_reviewer_score(user)
    
    await message.answer("Спасибо, ответ записан. "
        f'Баллов за проверку видео {round(review_request.video.duration/1200, 2)}'
        f"Всего заработано баллов {new_score}. "
        "Ожидайте получение нового видео. ")
    
    await message.bot.send_message(
        chat_id=review_request.video.task.implementer.tg_id,
        text=f'Ваше видео оценили\n\n{text}',
    )

    await send_message_admins(
        bot=message.bot,
        text=f'Видео пользователя @{user.username} на тему {review_request.video.task.theme.title} проверено.\n\n{text}',
    )

    await check_job_reviewers(message.bot)

    """Выставление итоговой оценки"""    
    reviews = (
        Review
        .select(Review)
        .join(ReviewRequest)
        .where(
            (ReviewRequest.video==review_request.video) &
            (ReviewRequest.status==1)))
    
    if reviews.count() < 5:
        return

    task_score = sum([review.score for review in reviews]) / 25

    task = review_request.video.task
    task.score = task_score
    task.status = 2 if task_score >= 0.8 else -2
    task.save()
    report = update_bloger_score_and_rating(task.implementer)
    await message.bot.send_message(
        chat_id=task.implementer.tg_id,
        text=f'Закончена проверка вашего видео.\n\n{report}',
    )

    await send_message_admins(
        bot=message.bot,
        text=f'Видео пользователя @{user.username} на тему {task.theme.title} проверено полностью.'
    )


def get_old_reviewe_requests() -> List[ReviewRequest]:
    now = datetime.now()
    # Запрос на выборку записей на проверке старше суток
    return (
        ReviewRequest
        .select()
        .where(
            (ReviewRequest.due_date <= now) &
            (ReviewRequest.status == 0)
        )
    )


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


async def add_reviewer(bot: Bot, video_id: int):
    # Свободные проверяющие
    vacant_reviewer_ids = get_vacant_reviewer_ids()
    
    if len(vacant_reviewer_ids) == 0:
        await send_message_admins(
            bot=bot,
            text=f'Закончились cвободные проверяющие, добавьте нового.',
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
            await send_message_admins(
                bot=bot,
                text=f'Нет кандидатов среди свободных проверяющих, добавьте нового. '
                f'Тема: {Video.get_by_id(video_id).task.theme.title}'
            )
            return

        due_date = get_due_date(hours=25)
        review_request = ReviewRequest.create(
            reviewer_id=candidat_reviewer_ids[0],
            video_id=video_id,
            due_date=due_date
        )
        await send_video(bot, review_request)

async def check_reviewers(bot: Bot):

    """Проверка устаревших задач"""
    old_review_requests = get_old_reviewe_requests()

    for old_review_request in old_review_requests:
        old_review_request.status = -1
        old_review_request.save()
        text = 'Задача на проверку с вас снята, ожидайте новую.'
        try:
            await bot.send_message(
                chat_id=old_review_request.reviewer.tg_id,
                text=text
            )
        except TelegramBadRequest as ex:
            print(ex, text)
        
        await send_message_admins(
            bot=bot,
            text=f'@{old_review_request.reviewer.username} просрочил тему {old_review_request.video.task.theme.title}'
        )

        await add_reviewer(bot, old_review_request.video_id)

async def check_job_reviewers(bot: Bot):
    # проверяющие у котых есть задачи
    reviewer_ids = [u.id for u in
        User
        .select(User)
        .join(ReviewRequest, on=(ReviewRequest.reviewer_id==User.id))
        .where(ReviewRequest.status==0)
    ]
    if len(reviewer_ids) < 5:
        video_ids = [v.id for v in 
            Video
            .select(Video)
            .join(ReviewRequest)
            .where(ReviewRequest.status >= 0)
            .group_by(Video.id)
            .having(fn.COUNT(Video.id) < 5)
        ]
        for video_id in video_ids:
            await add_reviewer(bot, Video.get_by_id(video_id))
            break


async def loop(bot: Bot):
    await check_reviewers(bot)
    await check_job_reviewers(bot)