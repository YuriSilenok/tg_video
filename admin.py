import csv
import functools
from typing import List
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError
from peewee import fn, JOIN, Case

from common import IsUser, get_due_date
from models import Role, User, UserCourse, UserRole, ReviewRequest, Task, Course, Theme, Video, update_bloger_score_and_rating


router = Router()


class IsAdmin(IsUser):

    role = Role.get(name='Админ')    

    async def __call__(self, message: Message) -> bool:
        is_user = await super().__call__(message)
        if not is_user:
            return False

        user_role = UserRole.get_or_none(
            user=User.get(tg_id=message.from_user.id),
            role=self.role
        )
        if user_role is None:
            await message.answer(
                text='У Вас нет привелегии админа.'
            )
        return user_role is not None


class UploadVideo(StatesGroup):
    wait_upload = State()


def error_handler():
    """Декоратор для обработки ошибок в хэндлерах и отправки сообщения админу"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(message: Message, *args, **kwargs):
            try:
                return await func(message, *args, **kwargs)
            except Exception as e:
                print(f"Ошибка в хэндлере {func.__name__}: {e}")
                error_text = f"🚨 <b>Ошибка в боте</b>\n\n📌 В хэндлере `{func.__name__}`\n❗ </b>Ошибка:</b> `{e}`"
                
                # Отправляем сообщение админу
                try:
                    await send_message_admins(
                        bot=message.bot,
                        text=error_text
                    )
                except TelegramAPIError:
                    print("Не удалось отправить сообщение админу.")
                await message.answer("❌ Произошла ошибка. Администратор уже уведомлён.")
        return wrapper
    return decorator


async def send_task(bot: Bot):

    # Исполнители, которые заняты
    subquery = (
        User
        .select(User.id)
        .join(Task, on=(Task.implementer == User.id))
        .where((Task.status >= 0) & (Task.status <= 1))
    )

    # Темы которые выданы, на проверке, готовы к публикации, опубликованы
    subquery2 = (
        Theme
        .select(Theme.id)
        .join(Task)
        .where(Task.status >= 0)
    )

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
                'Когда работа будет готова, вы должны отправить ваше видео'
        )
        
        await send_message_admins(
                    bot=bot,
                    text=f'''<b>Блогер получил тему</b>
Блогер: {task.implementer.comment}
Курс: {theme.course.title}
Тема: {theme.title}'''
                )

    if len(table) == 0:
        await send_message_admins(
            bot=bot,
            text='Нет свобоных тем или блогеров',
        )


def get_admins() -> List[User]:
    return (
        User
        .select(User)
        .join(UserRole)
        .where(UserRole.role==IsAdmin.role)
    )


async def send_message_admins(bot:Bot, text: str):
    for admin in get_admins():
        try:
            await bot.send_message(
                chat_id=admin.tg_id,
                text=text,
                parse_mode='HTML'
            )
        except Exception as ex:
            print(ex)
            await bot.send_message(
                chat_id=admin.tg_id,
                text=text
            )


@router.message(Command('send_task'), IsAdmin())
@error_handler()
async def st(message: Message):
    await send_task(message.bot)


@router.message(Command('report_reviewers'), IsAdmin())
@error_handler()
async def report_reviewers(message: Message):
    reviewers = (
        User
        .select(
            User.comment.alias('fio'),
            User.reviewer_score.alias('score'),
            User.reviewer_rating.alias('rating'),
            fn.COUNT(ReviewRequest).alias('count'),
        )
        .join(UserRole)
        .join(Role)
        .join(ReviewRequest, on=(ReviewRequest.reviewer_id==User.id))
        .where(
            (Role.name == 'Проверяющий') &
            (ReviewRequest.status == 1) # Видео проверено
        )
        .group_by(User)
        .order_by(User.reviewer_rating)
    )
    result = 'Отчет о проверяющих\n\n'
    result += '\n'.join([
        f"{i['count']}|{i['score']}|{round(i['rating'], 2)}|{i['fio']}" for i in reviewers.dicts()
    ])

    await message.answer(
        text=result
    )


@router.message(Command('report_blogers'), IsAdmin())
@error_handler()
async def report_blogers(message: Message):
    text = '\n'.join([f'{u.bloger_score} {u.comment}' for u in
        User
        .select(User)
        .join(UserRole)
        .join(Role)
        .where(Role.name=='Блогер')
    ])
    await message.answer(
        text=text
    )


@router.message(Command('add_role'), IsAdmin())
@error_handler()
async def add_role(message: Message):
    
    data = message.text.strip().replace('  ', '').split()
    if len(data) != 3:
        await message.answer(
            text=' Не верное коичетво параметров. Команда, роль, юзернейм'
        )
        return
    role_name = data[2]
    role = Role.get_or_none(name=role_name)
    if role is None:
        await message.answer(
            text=f'Нет роли {role_name}'
        )
        return
    
    username = data[1].strip()
    user = User.get_or_none(username=username)
    if user is None:
        await message.answer(
            text=f'Нет пользователя с юзернейм {username}'
        )
        return
    UserRole.get_or_create(
        user=user,
        role=role
    )
    await message.answer(
        text='Роль добавлена'
    )


@router.message(Command('set_comment'), IsAdmin())
@error_handler()
async def set_comment(message: Message):
    
    data = message.text.strip().replace('  ', '').split(maxsplit=1)[1]
    data = data.split(maxsplit=1)
    username = data[0]
    user = User.get_or_none(username=username)
    if user is None:
        await message.answer(
            text='Пользователь с таким юзернейм не найден'
        )
        return

    user.comment = data[1]
    user.save()

    await message.answer(
        text='Комментарий записан'
    )


@router.message(Command('report_themes'), IsAdmin())
@error_handler()
async def report_themes(message: Message):
    
    query = (
        Task
        .select(
            Task.status.alias('status'),
            Theme.title.alias('theme'),
            Course.title.alias('course'),
            User.comment.alias('user'),
            Task.due_date.alias('due_date'),
            Video.id.alias('video'),
            fn.COUNT(Case(None, [(ReviewRequest.status == -1, 1)], None)).alias('overdue_count'),
            fn.COUNT(Case(None, [(ReviewRequest.status == 0, 1)], None)).alias('pending_count'),
            fn.COUNT(Case(None, [(ReviewRequest.status == 1, 1)], None)).alias('reviewed_count'),
        )
        .join(User, on=(Task.implementer == User.id))
        .join(Theme, on=(Task.theme == Theme.id))
        .join(Course, on=(Course.id==Theme.course))
        .join(Video, JOIN.LEFT_OUTER, on=(Task.id == Video.task))
        .join(ReviewRequest, JOIN.LEFT_OUTER, on=(ReviewRequest.video == Video.id))
        .where(Task.status.between(0, 1))
        .group_by(Task.id)
        .order_by(Task.status, Task.due_date)
    )
    points = []
    for row in query.dicts():
        point = []
        line = [
            str(row["status"]),
            str(row["due_date"]),
        ]
        if row['status'] == 1:
            line.extend([
                str(row["overdue_count"]),
                str(row["pending_count"]),
                str(row["reviewed_count"]),
            ])
        point.append('|'.join(line))
        point.append(
            '|'.join([
                row["course"],
                row["theme"],
            ])
        )
        point.append(
            ': '.join([
                'Блогер',
                row["user"].split(maxsplit=1)[0],
            ])
        )

        if row['overdue_count'] > 0:
            line = ['<b>Просрочили:</b>']

            query2: List[ReviewRequest] = (
                ReviewRequest
                .select(ReviewRequest)
                .where(
                    (ReviewRequest.video==row['video']) &
                    (ReviewRequest.status==-1)
                )
            )

            for rr in query2:
                line.append(
                    '|'.join([
                        (rr.reviewer.comment.split(maxsplit=1)[0] if rr.reviewer.comment else 'нет ФИО'),
                        str(rr.due_date),
                        str(round(rr.reviewer.reviewer_rating, 2)),
                    ])
                )
            
            point.append(
                '\n'.join(line)
            )

        if row['pending_count'] > 0:
            line = ['<b>Проверяет:</b>']

            query2: List[ReviewRequest] = (
                ReviewRequest
                .select(ReviewRequest)
                .where(
                    (ReviewRequest.video==row['video']) &
                    (ReviewRequest.status==0)
                )
            )

            for rr in query2:
                line.append(
                    '|'.join([
                        (rr.reviewer.comment.split(maxsplit=1)[0] if rr.reviewer.comment else 'нет ФИО'),
                        str(rr.due_date),
                        str(round(rr.reviewer.reviewer_rating, 2)),
                    ])
                )
            
            point.append(
                '\n'.join(line)
            )

        if row['reviewed_count'] > 0:
            line = ['<b>Проверили:</b>']

            query2: List[ReviewRequest] = (
                ReviewRequest
                .select(ReviewRequest)
                .where(
                    (ReviewRequest.video==row['video']) &
                    (ReviewRequest.status==1)
                )
            )

            for rr in query2:
                line.append(
                    '|'.join([
                        (rr.reviewer.comment.split(maxsplit=1)[0] if rr.reviewer.comment else 'нет ФИО'),
                        str(rr.due_date),
                        str(round(rr.reviewer.reviewer_rating, 2)),
                    ])
                )
            
            point.append(
                '\n'.join(line)
            )
        
        points.append('\n'.join(point))

    await message.answer(
        text='\n\n'.join(points),
        parse_mode='HTML',
    )


@router.message(F.document.file_name.endswith(".csv"), IsAdmin())
@error_handler()
async def add_course(message: Message, state: FSMContext):
    doc = message.document
    course_title = doc.file_name[:-4]
    course, _ = Course.get_or_create(
        title=course_title
    )

    file = await message.bot.download(doc.file_id)
    try:
        file.seek(0)  # Устанавливаем указатель в начало
        table = csv.reader(file.read().decode("utf-8").splitlines())  # Читаем строки
        
        load_videos = []
        for row in table:
            theme_title = row[0]
            theme_url = row[1]
            theme, _ = Theme.get_or_create(
                course=course,
                title=theme_title,
                url=theme_url
            )
            if len(row) > 2 and row[2] != '':
                load_videos.append({
                    'theme': theme.id,
                    'title': theme.title,
                    'implementer': row[2].replace('@', ''),
                    'score': float(row[3].replace(',', '.')) if len(row) > 3 and row[3] != '' else 0.0,
                    'status': 2 if len(row) > 3 and row[3] != '' else 1,
                })

        if len(load_videos) == 0:
            await message.answer(
                text='Загрузка видео не требуется',
            )
            return
        
        await state.set_data({
            'load_videos': load_videos
        })
        await state.set_state(UploadVideo.wait_upload)
        await message.answer(
            text=f'Отправьте видео на тему "{load_videos[0]["title"]}"'
        )
        
    except Exception as e:
        await message.answer(f"Ошибка при чтении CSV: {e}")


@router.message(F.video, IsAdmin(), UploadVideo.wait_upload)
@error_handler()
async def upload_video(message: Message, state: FSMContext):

    data = await state.get_data()
    load_videos = data['load_videos']
    if len(load_videos) == 0:
        await message.answer(
            text='Все видео загружены',
        )
        return
    
    load_video = load_videos.pop(0)
    implementer = User.get(username=load_video['implementer'])
    theme = Theme.get(id=load_video['theme'])
    status=load_video['status']
    score=load_video['score']
    task, _ = Task.get_or_create(
        implementer=implementer,
        theme=theme,
        status=status,
        score=score,
        due_date=get_due_date(0)
    )

    Video.get_or_create(
        task=task,
        file_id=message.video.file_id,
        duration=message.video.duration,
    )

    text = update_bloger_score_and_rating(implementer)
    await message.bot.send_message(
        chat_id=implementer.tg_id,
        text=f'Видео на тему {theme.title} загружено администратором.\n\n{text}'
    )

    if len(load_videos) == 0:
        await state.clear()
        await message.answer(
            text='Все видео загружены'
        )
        return

    await state.set_data({
        'load_videos': load_videos
    })

    await message.answer(
        text=f'Отправьте видео на тему "{load_videos[0]["title"]}"'
    )