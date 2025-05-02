"""Обработчики на незарегистрированные действия"""
from aiogram.types import Router, Message
from models import User


router = Router()


@router.message()
async def other_messag_handler(message: Message):
    """Если пользователь неожиданно написал сообщение"""
    if message.from_user.username is None:
        await message.answer(
            text='У Вас не задан username, '
            'для продолжения работы с ботом, '
            'укажите его в своём профиле'
        )
        return
    user: User = User.get_or_none(
        tg_id=message.from_user.id
    )
    if user.comment is None:
        await message.answer(
            text=(
                "Представьтесь, указав свои ФИО. "
                "Отправьте команду в следующем формате \n"
                "<b>/set_fio Иванов Иван Иванович</b>ы"
            ),
            parse_mode='HTML',
        )
        return
