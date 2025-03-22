from datetime import datetime, timedelta
from typing import List
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from peewee import fn, JOIN


from filters import IsReview
from models import *
from common import *

router = Router()


@router.message(F.text, IsReview())
@error_handler()
async def get_review(message:Message):
    """Получение оценки и отзыва"""

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
    
    await message.answer(
        text=f"""Спасибо, ответ записан.
Баллов за проверку видео {round(review_request.video.duration/1200, 2)}
Всего заработано баллов {new_score}.
Ожидайте получение нового видео."""
    )
    
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


    """Выставление итоговой оценки"""    
    reviews = (
        Review
        .select(Review)
        .join(ReviewRequest)
        .where(
            (ReviewRequest.video==review_request.video) &
            (ReviewRequest.status==1)))
    
    if reviews.count() < 5:
        await send_new_review_request(message.bot)
        return

    task = review_request.video.task
    update_task_score(task)
    report = update_bloger_score_and_rating(task.implementer)
    await send_new_review_request(message.bot)

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


@error_handler()
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


@error_handler()
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


@router.callback_query(F.data.startswith('rr_to_extend_'), IsReview())
@error_handler()
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


@error_handler()
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


@error_handler()
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