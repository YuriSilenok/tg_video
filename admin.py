import csv
import functools
from typing import List
from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from peewee import fn, JOIN, Case

from filters import IsAdmin
from common import get_date_time, error_handler
from models import *


router = Router()



class UploadVideo(StatesGroup):
    wait_upload = State()

@error_handler()
async def send_task(bot: Bot):

    '''
select user.username, course.id, course.title, theme.title, user.bloger_rating, ucs.score, CASE WHEN (AVG(ucs.score) IS NULL) THEN user.bloger_rating ELSE AVG(ucs.score) END DESC
from user
inner join usercourse on usercourse.user_id=user.id
inner join course on course.id=usercourse.course_id
inner join theme on theme.course_id=course.id
left join (
    select task.implementer_id as user_id, theme.course_id as course_id, avg(task.score) as score
    from task
    inner join theme on task.theme_id=theme.id
    group by task.implementer_id, theme.course_id
) as ucs on ucs.user_id=user.id and ucs.course_id=course.id
where not theme.id IN (
    SELECT theme.id 
    FROM theme 
    INNER JOIN task ON task.theme_id=theme.id 
    WHERE task.status >= 0)
AND NOT user.id IN (
    SELECT user.id
    FROM user
    INNER JOIN task ON task.implementer_id=user.id
    WHERE task.status BETWEEN 0 and 1)
AND NOT course.id IN (
    SELECT theme.course_id
    from theme
    inner join task on task.theme_id=theme.id
    where task.status between 0 and 1
    group by theme.course_id)
GROUP BY user.id, course.id
ORDER BY user.bloger_rating DESC, 
CASE WHEN (AVG(ucs.score) IS NULL) THEN user.bloger_rating ELSE AVG(ucs.score) END DESC
'''

    # Исполнители, которые заняты
    '''
AND NOT user.id IN (
    SELECT user.id
    FROM user
    INNER JOIN task ON task.implementer_id=user.id
    WHERE task.status BETWEEN 0 and 1)
    '''
    subquery = (
        User
        .select(User.id)
        .join(Task, on=(Task.implementer == User.id))
        .where(Task.status.between(0, 1))
    )

    # Темы которые выданы, на проверке, готовы к публикации, опубликованы
    '''
where not theme.id IN (
    SELECT theme.id 
    FROM theme 
    INNER JOIN task ON task.theme_id=theme.id 
    WHERE task.status >= 0)
    '''
    subquery2 = (
        Theme
        .select(Theme.id)
        .join(Task)
        .where(Task.status >= 0)
    )

    # Подстчет средних оценко у блогеров по каждому курсу
    '''
    select task.implementer_id as user_id, theme.course_id as course_id, avg(task.score) as score
    from task
    inner join theme on task.theme_id=theme.id
    group by task.implementer_id, theme.course_id
    '''
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


    ''' занятые курсы
AND NOT course.id IN (
    SELECT theme.course_id
    from theme
    inner join task on task.theme_id=theme.id
    where task.status between 0 and 1
    group by theme.course_id)
    '''
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

    due_date = get_date_time(hours=73)
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


@error_handler()
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
    points = []
    blogers = (
        User
        .select(User)
        .where(User.bloger_score > 0)
        .order_by(User.bloger_rating.desc())
    )
    for bloger in blogers:
        point = [f'{bloger.bloger_score}|{round(bloger.bloger_rating * 100, 2)}|{bloger.comment}']
        
        task = (
            Task
            .select(Task)
            .where(
                (Task.implementer == bloger.id) &
                (Task.status.in_([0, 1]))
            )
            .first()
        )
        if task:
            point.append(
                '|'.join([
                    task.theme.course.title,
                    task.theme.title,
                    *([TASK_STATUS[task.status], str(task.due_date)] if task.status==0 else [TASK_STATUS[task.status]])
                ])
            )
        
        line = [uc.course.title for uc in
            UserCourse
            .select(UserCourse)
            .where((UserCourse.user_id == bloger.id))
        ]
        if line:
            point.append('Подписки: ' + '|'.join(line))
        points.append(
            '\n'.join(point)
        )

    text = '\n\n'.join(points)
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


RR_STATUS = {
    -1: '❌',
    0: '⚡' ,
    1: '✅',
}


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
            User.bloger_rating.alias('bloger_rating'),
            Task.due_date.alias('due_date'),
            Video.id.alias('video'),
            Video.at_created.alias('video_at_created')
        )
        .join(User, on=(Task.implementer == User.id))
        .join(Theme, on=(Task.theme == Theme.id))
        .join(Course, on=(Course.id==Theme.course))
        .join(Video, JOIN.LEFT_OUTER, on=(Task.id == Video.task))
        .join(ReviewRequest, JOIN.LEFT_OUTER, on=(ReviewRequest.video == Video.id))
        .where(Task.status.between(0, 1))
        .group_by(Task.id)
        .order_by(
            Task.status.desc(),
            User.bloger_rating.desc(),
            Case(None, [(Task.status==0, Task.due_date)], Video.at_created)
        )
    )
    points = []
    for row in query.dicts():
        point = []
        line = [
            '📹' if row["status"]==0 else '👀',
            (row["due_date"] if row['status'] == 0 else row['video_at_created']).strftime("%Y-%m-%d %H:%M"),
        ]
        point.append('|'.join(line))
        point.append(
            '|'.join([
                '📜',
                row["course"],
                row["theme"],
            ])
        )
        point.append(
            '|'.join([
                '👤',
                row["user"].split(maxsplit=1)[0],
                str(round(row["bloger_rating"], 2)),
            ])
        )

        query2: List[ReviewRequest] = (
            ReviewRequest
            .select(
                ReviewRequest
            )
            .join(Review, JOIN.LEFT_OUTER, on=(Review.review_request==ReviewRequest.id))
            .where(
                (ReviewRequest.video==row['video'])
            )
            .order_by(
                ReviewRequest.status
            )
        )
        for rr in query2:
            point.append(
                '|'.join([
                    RR_STATUS[rr.status],
                    (rr.reviewer.comment.split(maxsplit=1)[0] if rr.reviewer.comment else 'нет ФИО'),
                    str(round(rr.reviewer.reviewer_rating, 2)),
                    rr.due_date.strftime("%Y-%m-%d %H:%M") if rr.status < 1 else rr.reviews.first().at_created.strftime("%Y-%m-%d %H:%M"),
                ])
            )
            if rr.status == 1:
                point[-1] += f'|{rr.reviews.first().score}'

      
        points.append('\n'.join(point))

    await message.answer(
        text='\n\n'.join(points),
        parse_mode='HTML',
    )


@router.message(F.document.file_name.endswith(".csv"), IsAdmin())
@error_handler()
async def add_course(message: Message, state: FSMContext):

    file = await message.bot.download(message.document.file_id)
    try:
        file.seek(0)  # Устанавливаем указатель в начало
        table = csv.reader(file.read().decode("utf-8").splitlines())  # Читаем строки
        
        load_videos = []
        for row in table:
            course_title = row[0]
            if not course_title:
                break

            course, _ = Course.get_or_create(
                title=course_title
            )
            theme_title = row[1]
            theme_url = row[2]
            theme, _ = Theme.get_or_create(
                course=course,
                title=theme_title,
                url=theme_url
            )

            theme_complexity = float(row[3].replace(',', '.'))
            if theme.complexity != theme_complexity:
                theme.complexity = theme_complexity
                theme.save()

            if len(row) > 4 and row[4] != '':
                score = 0.0
                status = 1

                if len(row) > 5 and row[5] != '':
                    score = float(row[5].replace(',', '.'))
                    if score  >= 0.8:
                        status = 2
                    else:
                        status = -2

                load_videos.append({
                    'theme': theme.id,
                    'title': theme.title,
                    'implementer': row[4].replace('@', ''),
                    'score': score,
                    'status': status,
                })

        if len(load_videos) == 0:
            await message.answer(
                text='Темы курса загружены. Загрузка видео не требуется',
            )
            for user in User.select():
                update_bloger_score_and_rating(user)

        else:            
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
        due_date=get_date_time(0)
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
