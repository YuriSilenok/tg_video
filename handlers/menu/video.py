"""Модуль обработки обработчиков связанных с видео"""
from aiogram import Router, F
from aiogram.types import CallbackQuery
from filters.user import IsUser
from common import error_handler, get_id, send_message_admins, send_task
from models import User, Course, UserCourse
import keyboards

router = Router()


@router.callback_query(F.data == 'menu_video', IsUser())
@error_handler()
async def menu_video_handler(callback_query: CallbackQuery):
    """Показать: меню видео"""
    await callback_query.message.edit_text(
        **keyboards.menu.VIDEO
    )


@router.callback_query(F.data == 'course_subscriptions', IsUser())
@error_handler()
async def send_video_themes(callback_query: CallbackQuery):
    """Показать список подписок на курсы"""
    await callback_query.message.edit_text(
        **keyboards.menu.get_course_subscriptions(
            user=User.get(
                tg_id=callback_query.from_user.id
            )
        )
    )


@router.callback_query(F.data.startswith('add_user_course_'), IsUser())
@error_handler()
async def add_user_course_handler(callback_query: CallbackQuery):
    """Подписать блогера на курс"""
    user: User = User.get(tg_id=callback_query.from_user.id)
    course = Course.get_by_id(
        get_id(callback_query.data)
    )
    UserCourse.get_or_create(
        user=user,
        course=course,
    )

    await callback_query.message.edit_text(
        **keyboards.menu.get_course_subscriptions(
            user=user
        )
    )

    await send_message_admins(
        bot=callback_query.bot,
        text=f'Пользователь {user.link} подписался на курс {course.title}'
    )
    await send_task(callback_query.bot)


@router.callback_query(F.data.startswith('del_user_course_'), IsUser())
@error_handler()
async def del_user_course_handler(callback_query: CallbackQuery):
    """Отписать блогера от курса"""
    user: User = User.get(tg_id=callback_query.from_user.id)
    course = Course.get_by_id(
        get_id(callback_query.data)
    )

    user_course = UserCourse.get_or_none(
        user=user,
        course=course,
    )

    if user_course:
        user_course.delete_instance(recursive=True)

    await callback_query.message.edit_text(
        **keyboards.menu.get_course_subscriptions(
            user=user
        )
    )

    await send_message_admins(
        bot=callback_query.bot,
        text=f'Пользователь {user.link} отписался от курса {course.title}'
    )
