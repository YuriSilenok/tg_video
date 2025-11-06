"""модуль пользовательских функций"""

from datetime import datetime, timedelta
from typing import List, Union

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from peewee import fn

from common import (
    error_handler,
    get_date_time,
    get_id,
    get_limit_score,
    send_message_admins,
    send_new_review_request,
    send_task,
    update_task_score,
    check_user_role,
)
from filters import IsReview, IsReviewer, IsBanned
from models import (
    TASK_STATUS,
    Review,
    ReviewRequest,
    Task,
    Theme,
    User,
    UserRole,
)

# pylint: disable=no-member

router = Router()


@router.message(F.text, IsReview(), ~IsBanned())
@error_handler()
async def get_review(message: Message):
    """Получение оценки и отзыва"""
    reviewer: User = User.get(tg_id=message.from_user.id)
    review_request: ReviewRequest = ReviewRequest.get_or_none(
        reviewer=reviewer, status=0  # На проверке
    )

    if review_request is None:
        await message.answer(text="Запрос на проверку не найден")
        return
    text = message.text.strip()
    digit = text.find(" ")
    digit = text[:digit] if digit >= 0 else text
    digit = digit.replace(",", ".")

    try:
        digit = float(digit)
    except ValueError:
        await message.answer(text=f"Не удалось преобразовать {digit} в число")
        return

    if digit < 0 or digit > 5:
        await message.answer(text=f"{digit} должно быть в пределах [0.0; 5.0]")
        return
    Review.create(
        review_request=review_request,
        score=digit,
        comment=text,
    )
    review_request.status = 1  # Проверено
    review_request.save()

    reviewer.update_reviewer_score()
    reviewer.update_reviewer_rating()
    await message.answer(
        text=f"Спасибо, ответ записан.\n\n{reviewer.get_reviewer_report()}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    implementer: User = review_request.video.task.implementer
    await message.bot.send_message(
        chat_id=implementer.tg_id,
        text=f"Ваше видео оценили\n\n{text}",
    )

    await send_message_admins(
        bot=message.bot,
        text=(
            f"Проверяющий {reviewer.link} отправил отзыв "
            f"на видео {review_request.video.task.theme.course.title}|"
            f"{review_request.video.task.theme.link} блогера "
            f"{review_request.video.task.implementer.link}\n\n"
            f"{text}"
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Удалить отзыв и запрос",
                        callback_data=f"del_rr_{review_request.id}",
                    )
                ]
            ]
        ),
    )
    reviews = (
        Review.select(Review)
        .join(ReviewRequest)
        .where(
            (ReviewRequest.video == review_request.video)
            & (ReviewRequest.status == 1)
        )
    )

    if reviews.count() < 5:
        await send_new_review_request(message.bot)
        return

    task: Task = update_task_score(review_request.video.task)

    implementer.update_bloger_score()
    implementer.update_bloger_rating()

    await send_new_review_request(message.bot)

    limit_score = get_limit_score()
    text = f"Закончена проверка Вашего видео по теме {task.theme.link}.\n"
    text += f"Попрош приема работы {(limit_score*5):04.2f}"

    if task.status == 2:
        text += "Оно ❤️достойного❤️ качества и будет опубликовано."
    elif task.status == -2:
        text += "Оно 💩низкого💩 качества и будет отправлено на переделку."
    text += f"\n\n{implementer.get_bloger_report()}"

    await message.bot.send_message(
        chat_id=task.implementer.tg_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


    await send_message_admins(
        bot=message.bot,
        text=(
            "<b>Проверка видео завершена</b>\n"
            f"{task.implementer.link}|{task.theme.link}|"
            f"{(task.score*100):05.2f}|{TASK_STATUS[task.status]}\n"
            f"Порог приёма работы: {(limit_score*100):05.2f}"
        ),
    )

    await send_task(message.bot)

    if (
        implementer.get_bloger_rating_from_scores() >= limit_score
        and Theme.select(fn.SUM(Theme.complexity).alias("th_comp"))
        .join(Task)
        .where(Task.implementer == implementer.id)
        .first()
        .th_comp
        >= 10
        and UserRole.select()
        .where(
            (UserRole.user == implementer.id)
            & (UserRole.role == IsReviewer.role.id)
        )
        .count()
        == 0
    ):
        UserRole.get_or_create(
            user=implementer,
            role=IsReviewer.role,
        )
        await message.bot.send_message(
            chat_id=implementer.tg_id,
            text="Вам выдана роль проверяющего. "
            "Ожидайте видео на проверку. "
            "Если Вы не хотите проверять видео, "
            "игнорируйте выданные задачи на проверку видео.",
        )

        await send_message_admins(
            bot=message.bot,
            text=f"Роль проверяющего выдана {implementer.link}",
        )


@error_handler()
async def get_reviewer_user_role(
    bot: Bot, user: User
) -> Union[UserRole, None]:
    """Проверяем наличие привилегии блогера"""
    return await check_user_role(
        bot=bot,
        user=user,
        role_name="Проверяющий",
        error_message=(
            "Роль проверяющего не найдена! "
            "Это проблема администратора! "
            "Cообщите ему всё, что Вы о нем думаете. @YuriSilenok"
        ),
        notify_if_no_role=True,
    )


def get_reviewe_requests_by_notify() -> List[ReviewRequest]:
    """ПОлучить запросы на проверку у которы подходит срок"""
    due_date = get_date_time(hours=1)
    # Запрос на выборку записей на проверке старше суток
    return ReviewRequest.select().where(
        (ReviewRequest.due_date == due_date) & (ReviewRequest.status == 0)
    )


def get_old_reviewe_requests() -> List[ReviewRequest]:
    """ПОлучить запросы на проверку у которы прошел срок"""
    now = datetime.now()
    # Запрос на выборку записей на проверке старше суток
    return ReviewRequest.select().where(
        (ReviewRequest.due_date <= now) & (ReviewRequest.status == 0)
    )


@error_handler()
async def check_old_reviewer_requests(bot: Bot):
    """Проверка устаревших запросов на проверку"""

    rrs: List[ReviewRequest] = list(get_old_reviewe_requests())

    for rr in rrs:
        rr.status = -1
        rr.save()
        reviewer: User = rr.reviewer
        task: Task = rr.video.task
        reviewer.update_reviewer_rating()

        text = (
            "Задача на проверку с Вас снята, "
            f"ожидайте новую.\n\n{reviewer.get_reviewer_report()}"
        )
        try:
            await bot.send_message(
                chat_id=reviewer.tg_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except TelegramBadRequest as ex:
            print(ex, text)

        await send_message_admins(
            bot=bot,
            text=(
                f"Проверяющий {reviewer.link} просрочил "
                f"тему {task.theme.link} "
                f"блогера {task.implementer.link}"
            ),
        )

        await send_new_review_request(bot)


@router.callback_query(F.data.startswith("rr_to_extend_"), IsReview(), ~IsBanned())
@error_handler()
async def to_extend(callback_query: CallbackQuery):
    """Обработать запрос на продление срока проверки."""
    rr_id = get_id(callback_query.data)
    rr: ReviewRequest = ReviewRequest.get_by_id(rr_id)

    if rr.status != 0:
        await callback_query.message.edit_text(
            text="Срок не может быть продлен. "
            f"Отзыв по теме <b>{rr.video.task.theme.title}</b> уже получен.",
            parse_mode="HTML",
            reply_markup=None,
        )
        return

    rr.due_date += timedelta(hours=1)
    rr.save()

    await callback_query.message.edit_text(
        text=f"Срок сдвинут до {rr.due_date}",
        reply_markup=None,
    )

    await send_message_admins(
        bot=callback_query.bot,
        text=f"""<b>Проверяющий продлил срок</b>
Проверяющий: {rr.reviewer.comment.split(maxsplit=1)[0]}
Курс: {rr.video.task.theme.course.title}
Тема: {rr.video.task.theme.title}
Срок: {rr.due_date}""",
    )


@error_handler()
async def send_notify_reviewers(bot: Bot):
    """Послать напоминалку проверяющему об окончании строка"""

    for rr in list(get_reviewe_requests_by_notify()):
        await bot.send_message(
            chat_id=rr.reviewer.tg_id,
            text="До окончания срока проверки видео остался 1 час. "
            "Воспользуйтесь этой кнопкой, что бы продлить срок на 1 час",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Продлить",
                            callback_data=f"rr_to_extend_{rr.id}",
                        )
                    ]
                ]
            ),
        )


@error_handler()
async def loop(bot: Bot):
    """Основной цикл обработки"""
    now = datetime.now()
    if now.minute == 0:
        await send_notify_reviewers(bot)
        await check_old_reviewer_requests(bot)
