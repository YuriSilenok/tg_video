"""Взаимодействие с блогером"""

import traceback
from datetime import datetime, timedelta
from typing import List

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from common import (
    error_handler,
    get_date_time,
    get_id,
    send_message_admins,
    send_new_review_request,
    send_task,
    check_user_role,
)
from filters import IsBloger, WaitVideo, IsBanned
from models import (
    TASK_STATUS,
    Table,
    Task,
    Theme,
    User,
    UserCourse,
    UserRole,
    Video,
)

# pylint: disable=no-member

router = Router()


@error_handler()
@router.message(F.document, IsBloger(), WaitVideo(), ~IsBanned())
async def upload_file(message: Message):
    """Уведомляет пользователя о необходимости отправки видео"""
    await message.answer(
        text="📹🔜📨📹🚫📁.Видео нужно отправить как видео, а не как файл"
    )


@error_handler()
async def get_bloger_user_role(bot: Bot, user: User):
    """Проверяем наличие привилегии блогера"""
    return await check_user_role(
        bot=bot,
        user=user,
        role_name="Блогер",
        error_message=(
            "🕴🔑🚫🔎Роль блогера не найдена! "
            "Это проблема администратора! "
            "Cообщите ему всё, что Вы о нем думаете. @YuriSilenok"
        ),
        notify_if_no_role=False,
    )


@error_handler()
async def drop_bloger(bot: Bot, user: User):
    """Снимает роль блогера с пользователя, если она была выдана."""
    user_role = await get_bloger_user_role(bot, user)
    if user_role is None:
        await bot.send_message(
            chat_id=user.tg_id, text="✔️👆🛠🔑🕴Вам не выдавалась роль блогера."
        )
        return

    # Наличие выданной темы
    task = Task.get_or_none(
        implementer=user,
        status=0,
    )

    if task:
        await bot.send_message(
            chat_id=user.tg_id,
            text=f'👆💭👆💚☑👅❓У Вас выдана задача на тему "{task.theme.title}", '
            "Вы уверены что хотите отказаться?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="👌Да",
                            callback_data=f"del_task_yes_{task.id}",
                        )
                    ]
                ]
            ),
        )
        return

    if user_role:
        user_role.delete_instance(recursive=True)

    await bot.send_message(chat_id=user.tg_id, text="Роль блогера с Вас снята")

    await send_message_admins(
        bot=bot, text=f"Блогер {user.link} отказался от роли."
    )

    await send_task(bot)


@router.message(Command("bloger_off"), IsBloger(), ~IsBanned())
@error_handler()
async def bloger_off(message: Message):
    """Отключает пользователя из режима блогера."""
    user = User.get(tg_id=message.from_user.id)
    await drop_bloger(message.bot, user)


@router.callback_query(F.data.startswith("del_task_yes_"), IsBloger(), ~IsBanned())
@error_handler()
async def del_task_yes(query: CallbackQuery):
    """Подтверждение в отказе делать задачу"""

    await query.message.delete()

    task = Task.get_or_none(id=get_id(query.data))

    if task is None:
        await query.message.answer(text="Задача не найдена")
        return

    if task.status != 0:
        await query.message.answer(
            text="От задачи со статусом "
            f'"{TASK_STATUS[task.status]}" нельзя отказаться'
        )
        return

    task.status = -1
    task.save()

    user: User = User.get(tg_id=query.from_user.id)
    user.update_bloger_rating()

    await query.message.answer(
        text=f"Задача cнята\n\n{user.get_bloger_report()}",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    await drop_bloger(query.bot, user)


@router.message(F.video, IsBloger(), WaitVideo(), ~IsBanned())
@error_handler()
async def upload_video(message: Message):
    """Загружает видео пользователя и обновляет статус задачи"""
    user = User.get(tg_id=message.from_user.id)
    tasks = Task.select().where(
        (Task.status == 0) & (Task.implementer == user)
    )

    if tasks.count() == 0:
        await message.answer(
            text="У вас нет выданной темы, я не могу принять это видео"
        )
        return

    task = tasks.first()
    Video.create(
        task=task,
        file_id=message.video.file_id,
        duration=message.video.duration,
    )
    task.status = 1
    task.save()

    await message.answer(
        text=(
            "Видео принято на проверку. "
            "Пока новая тема не выдана, "
            "Вы можете отказаться быть блогером без снижения рейтинга."
        )
    )

    await send_message_admins(
        bot=message.bot,
        text=f"""🕴📨📹<b>Блогер {user.link} прислал видео</b>
Тема: {task.theme.course.title}|{task.theme.link}""",
    )

    await send_new_review_request(message.bot)


@router.callback_query(F.data.startswith("task_to_extend_"), IsBloger(), ~IsBanned())
@error_handler()
async def to_extend(callback_query: CallbackQuery):
    """Обрабатывает запрос на продление срока задачи"""
    task_id = get_id(callback_query.data)
    task: Task = Task.get_by_id(task_id)

    if task.status != 0:
        await callback_query.message.edit_text(
            text="Срок не может быть продлён. "
            f"Видео по теме {task.theme.link} уже получено.",
            parse_mode="HTML",
            reply_markup=None,
        )
        return
    theme: Theme = task.theme
    hours = int(theme.complexity * 72 / 2)
    hours = max(hours, 24)

    task.due_date += timedelta(hours=hours)
    task.extension = 0
    task.save()

    await callback_query.message.edit_text(
        text=f"Срок Вашей задачи продлен до {task.due_date}",
        reply_markup=None,
    )

    await send_message_admins(
        bot=callback_query.bot,
        text=f"""<b>Блогер {task.implementer.link} продлил срок</b>
Тема: {task.theme.course.title}|{task.theme.link}
Срок: {task.due_date}""",
    )


@error_handler()
async def check_expired_task(bot: Bot):
    """Помечает просроченные задачи"""
    dd = get_date_time()
    old_tasks: List[Task] = list(
        Task.select(Task).where((Task.status == 0) & (Task.due_date == dd))
    )
    for task in old_tasks:
        try:
            task.status = -2
            task.save()

            user_role: UserRole = UserRole.get_or_none(
                user=task.implementer, role=IsBloger.role
            )
            if user_role:
                user_role.delete_instance(recursive=True)

            try:
                await bot.send_message(
                    chat_id=task.implementer.tg_id,
                    text="Вы просрочили срок записи видео. "
                    "Тема и Роль блогера с Вас снята. "
                    "Если Вы хотите снова получить темы для видео, "
                    "пошлите команду /bloger_on",
                )
            except TelegramBadRequest:
                await send_message_admins(bot=bot, text=traceback.format_exc())

            await send_message_admins(
                bot=bot,
                text=f"Тему {task.theme.link} "
                f"просрочил {task.implementer.link}",
            )

            await send_task(bot)

            new_task = Task.get_or_none(
                theme=task.theme,
                status=0,
            )
            if new_task:
                continue

            query: List[UserRole] = list(
                UserRole.select().where(
                    (UserRole.role_id == IsBloger.role.id)
                    & (
                        ~UserRole.user_id
                        << (
                            User.select(User.id)
                            .join(UserCourse)
                            .where(
                                UserCourse.course_id == task.theme.course_id
                            )
                        )
                    )
                    & (
                        ~UserRole.user_id
                        << (
                            Task.select(Task.implementer_id).where(
                                Task.status.between(0, 1)
                            )
                        )
                    )
                )
            )
            for user_role in query:
                try:
                    await bot.send_message(
                        chat_id=user_role.user.tg_id,
                        text=f"Для курса {task.theme.course.title} нет "
                        "исполнителя, подпишитесь на него и получите "
                        "задачу на разработку видео",
                    )
                except TelegramBadRequest:
                    await send_message_admins(
                        bot=bot, text=traceback.format_exc()
                    )

        except TelegramBadRequest as ex:
            print(ex, task.implementer.comment)


@error_handler()
async def check_old_task(bot: Bot):
    """Асинхронная функция проверяет старые невыполненные задачи"""
    now = get_date_time()

    old_tasks: List[Task] = list(
        Task.select(Task).where((Task.status == 0) & (Task.extension == 0))
    )
    for task in old_tasks:

        theme: Theme = task.theme
        hours = int(theme.complexity * 72 / 2)
        hours = max(hours, 24)
        reserve_time: timedelta = timedelta(hours=hours)
        left_time: datetime = task.due_date - now
        if left_time > reserve_time:
            continue

        try:
            sql_query = f"""
select u.user_id
from (
    select ur.user_id
    from userrole as ur
    inner join usercourse as uc on ur.user_id=uc.user_id
    where uc.course_id = {task.theme.course_id}
    and ur.role_id={IsBloger.role.id}
) as u
left join task on task.implementer_id=u.user_id and task.status in (0, 1)
where task.id is NULL;
"""
            users: List[int] = [
                r["user_id"] for r in Table.raw(sql_query).dicts()
            ]
            cont = False

            for user_id in users:
                u: User = User.get_by_id(user_id)
                if u.bloger_rating > task.implementer.bloger_rating:
                    cont = True
                    break

            if cont:
                continue

            await bot.send_message(
                chat_id=task.implementer.tg_id,
                text="Воспользуйтесь этой кнопкой, чтобы продлить срок Вашей "
                f"задачи до {task.due_date + reserve_time} ",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Продлить до "
                                f"{task.due_date + reserve_time}",
                                callback_data=f"task_to_extend_{task.id}",
                            )
                        ]
                    ]
                ),
            )
            task.extension = 1
            task.save()
        except TelegramBadRequest as ex:
            print(ex, task.implementer.comment)


def update_rating_all_blogers():
    """Обновляет рейтинг всех блогеров с невыполненными задачами"""
    blogers: List[User] = User.select(User).join(Task).where(Task.status == 0)

    for bloger in blogers:
        bloger.update_bloger_rating()


@error_handler()
async def loop(bot: Bot):
    """Цикл обновляет рейтинги блогеров"""
    update_rating_all_blogers()
    await check_old_task(bot)
    await check_expired_task(bot)
