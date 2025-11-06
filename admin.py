"""Модуль обработки административных команд и функций"""

import csv

from typing import List
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from peewee import JOIN, Case

from common import (
    add_reviewer,
    error_handler,
    get_date_time,
    get_id,
    send_task,
)
from filters import IsAdmin
from models import (
    Course,
    Review,
    ReviewRequest,
    Role,
    Task,
    Theme,
    User,
    UserRole,
    Video,
)

# pylint: disable=no-member

router = Router()


class UploadVideo(StatesGroup):  # pylint: disable=too-few-public-methods
    """Класс состояний для загрузки видео администратором."""

    wait_upload = State()


@router.callback_query(F.data.startswith("del_rr_"))
@error_handler()
async def del_rr(callback: CallbackQuery):
    """Обработчик удаления запроса на проверку (ReviewRequest)."""
    rr_id = get_id(callback.data)
    rr: ReviewRequest = ReviewRequest.get_or_none(id=rr_id)

    if not rr:
        await callback.answer(text="Запрос на проверку не найден")
        return

    r: Review = rr.reviews.first()
    if not r:
        await callback.answer(text="Не найден отзыв")
        return
    video: Video = rr.video
    task: Task = video.task
    if task.status != 1:
        task.status = 1
        task.save()
        await callback.message.reply(
            text="Проверка по задаче возобновлена",
        )

    await callback.message.reply(text="Запрос на проверку и отзыв удалён")

    await callback.bot.send_message(
        chat_id=rr.reviewer.tg_id,
        text="Ваш отзыв и запрос на проверку видео удален. "
        "Ожидайте следующее видео на проверку. "
        "Возможно бот выдаст видео на проверку повторно.\n\n"
        f"{r.comment}",
    )

    await callback.bot.send_message(
        chat_id=task.implementer.tg_id,
        text=f"Отзыв по вашему видео удален.\n\n{r.comment}",
    )

    rr.delete_instance(recursive=True)
    await add_reviewer(callback.bot, video.id)


@router.message(Command("send_task"), IsAdmin())
@error_handler()
async def st(message: Message):
    """Ручной запуск выдачи задач блогерам."""
    await send_task(message.bot)


@router.message(Command("report_reviewers"), IsAdmin())
@error_handler()
async def report_reviewers(message: Message):
    """Формирование отчета по проверяющим."""
    old_date = get_date_time(hours=-24 * 14)
    reviewers: List[User] = (
        User.select(User)
        .where(
            (User.reviewer_score > 0)
            & (
                User.id
                << (
                    ReviewRequest.select(ReviewRequest.reviewer)
                    .join(Review)
                    .where(Review.at_created >= old_date)
                )
            )
        )
        .group_by(User)
        .order_by(User.reviewer_rating.desc())
    )
    result = "👀📄<b>Отчет о проверяющих</b>\n"
    result += "\n".join(
        [
            (
                f"{u.reviewer_score:05.2f}"
                f"|{(u.reviewer_rating*100):05.2f}|{u.link}"
            )
            for u in reviewers
        ]
    )

    await message.answer(
        text=result,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(Command("report_blogers"), IsAdmin())
@error_handler()
async def report_blogers(message: Message):
    """Формирование отчета по блогерам."""
    points = ["📹📄<b>Отчет о блогерах</b>"]
    old_date = get_date_time(hours=-24 * 14)
    blogers = (
        User.select(User)
        .where(
            (User.bloger_score > 0)
            & (
                User.id
                << (
                    Task.select(Task.implementer)
                    .join(Video)
                    .where(Video.at_created >= old_date)
                )
            )
        )
        .order_by(User.bloger_rating.desc())
    )
    for bloger in blogers:

        points.append(
            f"{bloger.bloger_score:05.2f}"
            f"|{(bloger.bloger_rating*100):05.2f}"
            f"|{bloger.link}"
        )

    text = "\n".join(points)
    await message.answer(
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(Command("add_role"), IsAdmin())
@error_handler()
async def add_role(message: Message):
    """Добавление роли пользователю."""
    data = message.text.strip().replace("  ", "").split()
    if len(data) != 3:
        await message.answer(
            text=" ❌🔢🔢Неверное количество параметров. Команда, роль, юзернейм"
        )
        return
    role_name = data[2]
    role = Role.get_or_none(name=role_name)
    if role is None:
        await message.answer(text=f"📤🙅‍♂🔑Нет роли {role_name}")
        return

    username = data[1].replace("@", "").strip()
    user = User.get_or_none(username=username)
    if user is None:
        await message.answer(
            text=f"📤🙅‍♂👩‍💻⏮🆔Нет пользователя с юзернейм {username}"
        )
        return
    UserRole.get_or_create(user=user, role=role)
    await message.answer(text="🔑🚮Роль добавлена")


@router.message(Command("set_comment"), IsAdmin())
@error_handler()
async def set_comment(message: Message):
    """Установка комментария (ФИО) для пользователя."""
    data = message.text.strip().replace("  ", "").split(maxsplit=1)[1]
    data = data.split(maxsplit=1)
    username = data[0].replace("@", "").strip()
    user = User.get_or_none(username=username)
    if user is None:
        await message.answer(
            text="👩‍💻⏮👉🆔🚫🔎Пользователь с таким юзернейм не найден"
        )
        return

    user.comment = data[1]
    user.save()

    await message.answer(text="🏤⏺Комментарий записан")


RR_STATUS = {
    -1: "❌",
    0: "⚡",
    1: "✅",
}

TASK_STATUS = {0: "📹", 1: "👀", 2: "⏱️"}


@router.message(Command("report_tasks"), IsAdmin())
@error_handler()
async def report_tasks(message: Message):
    """Формирование отчета по текущим задачам."""
    tasks: List[Task] = (
        Task.select(Task)
        .where(Task.status.between(0, 2))
        .join(User, on=User.id == Task.implementer)
        .order_by(
            Task.status.desc(),
            Task.due_date.asc(),
        )
    )

    points = [[], [], []]

    for task in tasks:
        implementer: User = task.implementer
        point = [
            "|".join(
                [
                    TASK_STATUS[task.status],
                    f"{task.theme.complexity:5.3f}",
                    task.theme.course.title,
                    task.theme.link,
                    # (
                    #     task.due_date if task.status == 0
                    #     else task.videos.first().at_created
                    # ).strftime("%Y-%m-%d %H:%M"),
                    (
                        f'{task.due_date.strftime("%d %H:%M")}'
                        if task.status == 0
                        else (
                            ""
                            if task.status == 1
                            else f"{(task.score*100):05.2f}"
                        )
                    ),
                    implementer.link,
                    f"{(implementer.bloger_rating*100):05.2f}",
                ]
            )
        ]
        if task.status > 0:
            rrs = (
                task.videos.first()
                .reviewrequests.join(Review, JOIN.LEFT_OUTER)
                .order_by(
                    ReviewRequest.status.desc(),
                    Case(
                        None,
                        [(ReviewRequest.status == 0, ReviewRequest.due_date)],
                        Review.at_created,
                    ),
                )
            )

            line = "".join(
                [
                    (
                        (
                            '<a href="https://t.me/'
                            f'{rr.reviewer.username}">'
                            f"{RR_STATUS[rr.status]}</a>"
                            f"{rr.reviews.first().score:3.1f}"
                        )
                        if rr.status == 1
                        else (
                            (
                                '<a href="https://t.me/'
                                f'{rr.reviewer.username}">'
                                f"{RR_STATUS[rr.status]}</a>"
                                f'{rr.due_date.strftime("%d %H:%M")}'
                            )
                            if rr.status == 0
                            else (
                                '<a href="https://t.me/'
                                f'{rr.reviewer.username}">'
                                f"{RR_STATUS[rr.status]}</a>"
                            )
                        )
                    )
                    for rr in rrs
                ]
            )

            if line:
                point.append(line)

        points[task.status].append("\n".join(point))

    end_points = []
    char_count = 0
    for status in (1, 0, 2):
        for point in points[status]:
            if len(point) + char_count < 4096:
                end_points.append(point)
                char_count += len(point)

    await message.answer(
        text="\n\n".join(end_points),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


@router.message(F.document.file_name.endswith(".csv"), IsAdmin())
@error_handler()
async def add_course(message: Message, state: FSMContext):
    """Загружает курсы и темы из CSV файла."""
    file = await message.bot.download(message.document.file_id)
    try:
        table = _parse_csv_file(file)
        videos_to_upload = _process_theme_rows(table)
        await _send_upload_response(message, state, videos_to_upload)

    except (csv.Error, UnicodeDecodeError, ValueError, IndexError) as e:
        await message.answer(f"Ошибка при чтении CSV: {e}")


def _parse_csv_file(file) -> List[List[str]]:
    """Читает CSV файл и возвращает данные в виде списка строк."""
    file.seek(0)
    return csv.reader(file.read().decode("utf-8").splitlines())


def _process_theme_rows(table: List[List[str]]) -> List[dict]:
    """Обрабатывает строки CSV, создаёт/обновляет курсы и темы."""
    videos_to_upload = []
    for row in table:
        if not row[0]:  # Пустая строка курса → пропуск
            break
        course = _get_or_create_course(row[0])
        theme = _update_or_create_theme(course, row[1:4])
        if len(row) > 4 and row[4]:  # Есть реализатор → добавляем видео
            video_data = _prepare_video_row(theme, row[4:6])
            videos_to_upload.append(video_data)
    return videos_to_upload


def _get_or_create_course(title: str) -> Course:
    """Возвращает существующий курс или создаёт новый."""
    course, _ = Course.get_or_create(title=title)
    return course


def _update_or_create_theme(course: Course, row: List[str]) -> Theme:
    """Обновляет или создаёт тему курса."""
    theme = Theme.get_or_none(course=course, title=row[0])
    if not theme:
        return Theme.create(
            course=course,
            title=row[0],
            url=row[1],
            complexity=float(row[2].replace(",", ".")),
        )
    return _update_theme(theme, row[1], float(row[2].replace(",", ".")))


def _update_theme(theme: Theme, new_url: str, new_complexity: float) -> Theme:
    """Обновляет URL и сложность темы, если они изменились."""
    if theme.url != new_url or theme.complexity != new_complexity:
        theme.url = new_url
        theme.complexity = new_complexity
        theme.save()
    return theme


def _prepare_video_row(theme: Theme, row: List[str]) -> dict:
    """Готовит данные видео для загрузки."""
    score = float(row[1].replace(",", ".")) if len(row) > 1 and row[1] else 0.0
    status = 2 if score >= 0.8 else (-2 if score else 1)
    return {
        "theme": theme.id,
        "title": theme.title,
        "implementer": row[0].replace("@", ""),
        "score": score,
        "status": status,
    }


async def _send_upload_response(
    message: Message,
    state: FSMContext,
    videos_to_upload: List[dict],
) -> None:
    """Отправляет ответ пользователю в зависимости от результата."""
    if not videos_to_upload:
        await message.answer("↗️❔📐 Темы курса загружены. Видео не требуются.")
        _update_user_scores()
    else:
        await state.set_data({"load_videos": videos_to_upload})
        await state.set_state(UploadVideo.wait_upload)
        await message.answer(
            f'📨📹 Отправьте видео на тему "{videos_to_upload[0]["title"]}"'
        )


def _update_user_scores() -> None:
    """Обновляет баллы всех пользователей."""
    for user in User.select():
        user.update_bloger_score()


@router.message(F.video, IsAdmin(), UploadVideo.wait_upload)
@error_handler()
async def upload_video(message: Message, state: FSMContext):
    """Обработчик загрузки видео для тем из CSV."""
    data = await state.get_data()
    load_videos = data["load_videos"]
    if len(load_videos) == 0:
        await message.answer(
            text="🌐📹✔️📂Все видео загружены",
        )
        return

    load_video = load_videos.pop(0)
    implementer: User = User.get(username=load_video["implementer"])
    theme = Theme.get(id=load_video["theme"])
    status = load_video["status"]
    score = load_video["score"]
    task, _ = Task.get_or_create(
        implementer=implementer,
        theme=theme,
        status=status,
        score=score,
        due_date=get_date_time(0),
    )

    Video.get_or_create(
        task=task,
        file_id=message.video.file_id,
        duration=message.video.duration,
    )

    implementer.update_bloger_score()
    await message.bot.send_message(
        chat_id=implementer.tg_id,
        text=(
            f"📹📂👨‍💼Видео на тему {theme.title} загружено администратором."
            f"\n\n{implementer.get_bloger_report()}"
        ),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    if len(load_videos) == 0:
        await state.clear()
        await message.answer(text="🌐📹✔️📂Все видео загружены")
        return

    await state.set_data({"load_videos": load_videos})

    await message.answer(
        text=f'📨📹Отправьте видео на тему "{load_videos[0]["title"]}"'
    )


@router.message(Command("ban_user"), IsAdmin())
@error_handler()
async def ban_user(message: Message):
    """Заблокировать пользователя."""
    data = message.text.strip().replace("  ", " ").split()
    if len(data) != 2:
        await message.answer(
            text="❌ Неверное количество параметров. Используйте: /ban_user @username"
        )
        return

    username = data[1].replace("@", "").strip()
    user = User.get_or_none(username=username)
    if user is None:
        await message.answer(
            text=f"❌ Пользователь с username {username} не найден"
        )
        return

    admin_role = Role.get_or_none(name="Админ")
    if admin_role:
        is_admin = UserRole.get_or_none(user=user, role=admin_role)
        if is_admin:
            await message.answer(
                text="❌ Нельзя заблокировать администратора"
            )
            return

    if user.is_banned:
        await message.answer(
            text=f"⚠️ Пользователь @{username} уже заблокирован"
        )
        return

    user.is_banned = True
    user.save()
    
    bloger_role = Role.get_or_none(name="Блогер")
    reviewer_role = Role.get_or_none(name="Проверяющий")
    
    if bloger_role:
        bloger_user_role = UserRole.get_or_none(user=user, role=bloger_role)
        if bloger_user_role:
            bloger_user_role.delete_instance()
    
    if reviewer_role:
        reviewer_user_role = UserRole.get_or_none(user=user, role=reviewer_role)
        if reviewer_user_role:
            reviewer_user_role.delete_instance()

    active_tasks = Task.select().where(
        (Task.implementer == user) & (Task.status.in_([0, 1]))
    )
    for task in active_tasks:
        task.status = -1
        task.save()

    active_reviews = ReviewRequest.select().where(
        (ReviewRequest.reviewer == user) & (ReviewRequest.status == 0)
    )
    for review_request in active_reviews:
        review_request.status = -1
        review_request.save()

    await message.answer(
        text=f"🔨 Пользователь @{username} ({user.comment or 'Без ФИО'}) заблокирован"
    )

    try:
        await message.bot.send_message(
            chat_id=user.tg_id,
            text="❌ Вы были заблокированы администратором. "
            "Все ваши активные задачи отменены. "
            "Для разблокировки обратитесь к администратору."
        )
    except Exception:
        pass


@router.message(Command("unban_user"), IsAdmin())
@error_handler()
async def unban_user(message: Message):
    """Разблокировать пользователя."""
    data = message.text.strip().replace("  ", " ").split()
    if len(data) != 2:
        await message.answer(
            text="❌ Неверное количество параметров. Используйте: /unban_user @username"
        )
        return

    username = data[1].replace("@", "").strip()
    user = User.get_or_none(username=username)
    if user is None:
        await message.answer(
            text=f"❌ Пользователь с username {username} не найден"
        )
        return

    if not user.is_banned:
        await message.answer(
            text=f"⚠️ Пользователь @{username} не заблокирован"
        )
        return

    user.is_banned = False
    user.save()

    await message.answer(
        text=f"✅ Пользователь @{username} ({user.comment or 'Без ФИО'}) разблокирован"
    )

    try:
        await message.bot.send_message(
            chat_id=user.tg_id,
            text="✅ Вы были разблокированы администратором. "
            "Теперь вы можете снова использовать бота."
        )
    except Exception:
        pass