"""Клавиатура для главного меню"""
from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from peewee import fn, JOIN
from models import User, Theme, Task, Course, UserCourse, UserRole
from filters import IsBloger


HOME: dict = {
    'text': (
        "<b>Меню пользователя</b>\n\n"
        "<b>Видео</b> - Запись, проверить, посмотреть видео.\n"
        "<b>Задачи</b> - Предложить, решить, проверить задачу\n"
        "<b>Профиль - Отчеты</b>"
    ),
    'reply_markup':
        InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(
                    text='Видео',
                    callback_data='menu_video',
                ),
                InlineKeyboardButton(
                    text='Задачи',
                    callback_data='menu_task',
                )
            ]]
    ),
    'parse_mode': 'HTML'
}


VIDEO: dict = {
    'text': (
        '<b>Меню видео</b>\n\n'
        '<b>Записать</b> - Подпишитесль на курс и бот выдаст Вам тему, '
        'в порядке очереди\n'
        '<b>Отправить</b> - Когда видео будет записано, '
        'воспользуйтесь этой кнопкой для его отправки\n'
        '<b>Назад</b> - Перейти в меню пользователя\n'
    ),
    'reply_markup': InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text='Записать',
                callback_data='course_subscriptions',
            ),
            InlineKeyboardButton(
                text='Отправить',
                callback_data='send_video',
            ),
            InlineKeyboardButton(
                text='Назад',
                callback_data='menu',
            ),
        ]]
    ),
    'parse_mode': 'HTML'
}


def get_course_subscriptions(user: User):
    """Получить список подписок на курсы"""

    # Список тем, работы над которыми завершены
    themes_done: List[Theme] = (
        Theme
        .select(Theme.id)
        .join(Task)
        .where(Task.status >= 2)
    )

    # Список тем, над которыми требуется провести работы
    themes: List[Theme] = (
        Theme
        .select(Theme)
        .join(
            Course,
            on=Course.id == Theme.course
        )
        .join(
            Task,
            JOIN.LEFT_OUTER,
            on=Task.theme == Theme.id
        )
        .where(
            (~Theme.id << themes_done)
        )
        .group_by(
            Theme.course,
            Theme.id
        )
        .order_by(
            fn.LENGTH(Course.title),
            Theme.id,
        )
    )

    # Список курсов и до трех тем к каждому курсу
    data = {}
    text = '<b>Список курсов</b>\n\n'

    for theme in themes:
        course = theme.course

        if course.id not in data:
            data[course.id] = {
                'enity': course,
                'themes': [],
            }

        if len(data[course.id]['themes']) >= 3:
            continue

        data[course.id]['themes'].append(theme)

    inline_keyboard = []

    for course_id, item in data.items():
        themes = item['themes']
        # пропускаем курсы с постым списком тем
        if len(themes) == 0:
            continue

        # количество блогеров у которых есть роль
        # и они подписаны на этот курс
        bloger_count = (
            UserCourse
            .select(fn.COUNT(UserCourse.id))
            .join(
                UserRole,
                on=UserRole.user == UserCourse.user
            )
            .where(
                (UserCourse.course_id == course_id) &
                (UserRole.role_id == IsBloger.role.id)
            )
            .scalar()
        )

        themes_str = '\n'.join([
            f'<a href="{t.url}">{t.title}</a>|{t.complexity}'
            for t in themes
        ])

        course: Course = item['entity']
        text += f'<b>{course.title}</b>|{bloger_count}\n{themes_str}\n\n'
        row = None

        if len(inline_keyboard) == 0:
            row = []
        elif (
            sum([len(i.text) for i in inline_keyboard[-1]])
            + len(course.title) + 1
        ) < 25:
            row = inline_keyboard.pop()
        else:
            row = []

        # Подписка пользователя на курс
        user_course = UserCourse.get_or_none(
            user=user,
            course=course,
        )

        row.append(
            InlineKeyboardButton(
                text=f'{"✅" if user_course else "❌"}{course.title}',
                callback_data=f'del_user_course_{course.id}'
                if user_course else f'add_user_course_{course.id}'
            )
        )
        inline_keyboard.append(row)
    return {
        'text': text,
        'reply_markup': InlineKeyboardMarkup(
            inline_keyboard=inline_keyboard
        ),
        'parse_mode': "HTML",
        'disable_web_page_preview': True,
    }
