from datetime import datetime, timedelta
from typing import List
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from peewee import fn, JOIN

from admin import error_handler, send_message_admins, send_task
from models import (
    Review, ReviewRequest, Role, Task, User, UserRole, Video,
    update_bloger_score_and_rating, update_reviewer_score, update_reviewers_rating, 
)
from common import IsUser, get_date_time, get_id, get_user


router = Router()


class IsReviewer(IsUser):

    role = Role.get(name='Проверяющий')    

    async def __call__(self, message: Message) -> bool:
        is_user = await super().__call__(message)
        if not is_user:
            return False

        user_role = UserRole.get_or_none(
            user=User.get(tg_id=message.from_user.id),
            role=self.role
        )
        return user_role is not None


@router.message(F.text, IsReviewer())
@error_handler()
async def get_review(message:Message):
    
    """Поиск запроса на проверку"""
    user = User.get(tg_id=message.from_user.id)
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
        text=f'''<b>Проверяющий отправил отзыв</b>
Проверяющий: {user.comment}
Блогер: {review_request.video.task.implementer.comment}
Курс: {review_request.video.task.theme.course.title}
Тема: {review_request.video.task.theme.title}
Отзыв: {text}'''
    )

    await send_new_review_request(message.bot)

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

    task = review_request.video.task
    update_task_score(task)
    report = update_bloger_score_and_rating(task.implementer)

    await message.bot.send_message(
        chat_id=task.implementer.tg_id,
        text=f'Закончена проверка вашего видео.\n\n{report}',
    )

    await send_message_admins(
        bot=message.bot,
        text=f'''<b>Проверка видео завершена</b>
Блогер: {task.implementer.comment}
Курс: {task.theme.course.title}
Тема: {task.theme.title}'''
    )

    await send_task(message.bot)


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





def get_reviewe_requests_by_notify() -> List[ReviewRequest]:
    '''ПОлучить запросы на проверку у которы прошел срок'''
    due_date = get_date_time(hours=1)
    # Запрос на выборку записей на проверке старше суток
    return (
        ReviewRequest
        .select()
        .where(
            (ReviewRequest.due_date == due_date) &
            (ReviewRequest.status == 0)
        )
    )




def get_old_reviewe_requests() -> List[ReviewRequest]:
    '''ПОлучить запросы на проверку у которы прошел срок'''
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
        theme = Video.get_by_id(video_id).task.theme
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



async def check_old_reviewer_requests(bot: Bot):
    """Проверка устаревших запросов на проверку"""
    
    
    old_review_requests = get_old_reviewe_requests()

    for old_review_request in old_review_requests:
        old_review_request.status = -1
        old_review_request.save()
        text = 'Задача на проверку с Вас снята, ожидайте новую.'
        try:
            await bot.send_message(
                chat_id=old_review_request.reviewer.tg_id,
                text=text
            )
        except TelegramBadRequest as ex:
            print(ex, text)
        
        rr: ReviewRequest = old_review_request
        task: Task = rr.video.task
        await send_message_admins(
            bot=bot,
            text=f'''<b>Проверяющий просрочил тему</b>
Проверяющий: {rr.reviewer.comment}
Блогер: {task.implementer.comment}
Курс: {task.theme.course.title}
Тема: {task.theme.title}'''
        )
        update_reviewers_rating()


async def send_new_review_request(bot: Bot):
    """Выдать новый запрос на проверку"""
    # проверяющие у котых есть задачи
    reviewer_ids = [u.id for u in
        User
        .select(User)
        .join(ReviewRequest, on=(ReviewRequest.reviewer_id==User.id))
        .where(ReviewRequest.status==0)
        
    ]
    if len(reviewer_ids) < 5:
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
            break



@router.callback_query(F.data.startswith('rr_to_extend_'))
async def to_extend(callback_query: CallbackQuery):
    rr_id = get_id(callback_query.data)
    rr: ReviewRequest = ReviewRequest.get_by_id(rr_id)

    if rr.status != 0:
        await callback_query.message.edit_text(
            text='Срок не может быть продлен. '
            f'Отзыв по теме <b>{rr.video.task.theme.title}</b> уже получен.',
            parse_mode='HTML',
            reply_markup=None,
        )
        return

    rr.due_date += timedelta(hours=1)
    rr.save()

    await callback_query.message.edit_text(
        text=f'Срок сдвинут до {rr.due_date}',
        reply_markup=None,
    )

    await send_message_admins(
        bot=callback_query.bot,
        text=f'''<b>Проверяющий продлил срок</b>
Проверяющий: {rr.reviewer.comment.split(maxsplit=1)[0]}
Курс: {rr.video.task.theme.course.title}
Тема: {rr.video.task.theme.title}
Срок: {rr.due_date}'''
    )



async def send_notify_reviewers(bot: Bot):
    '''Послать напоминалку проверяющему об окончании строка'''

    for rr in get_reviewe_requests_by_notify():
        await bot.send_message(
            chat_id=rr.reviewer.tg_id,
            text='До окончания срока проверки видео остался 1 час. '
            'Воспользуйтесь этой кнопкой, что бы продлить срок на 1 час',
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[
                    InlineKeyboardButton(
                        text='Продлить',
                        callback_data=f'rr_to_extend_{rr.id}',
                    )
                ]]
            )
        )




async def loop(bot: Bot):
    await send_notify_reviewers(bot)
    await check_old_reviewer_requests(bot)
    await send_new_review_request(bot)

if __name__ == '__main__':
    rr: List[ReviewRequest] = (
        ReviewRequest
        .select(ReviewRequest)
        .join(Video)
        .join(Task)
        .where(
            (ReviewRequest.status==1) &
            (Task.status==1)
        )
        .group_by(ReviewRequest.video)
        .having(fn.COUNT(ReviewRequest.video) == 5)
    )
    for r in rr:
        print(r.video_id)
        update_task_score(r.video.task)