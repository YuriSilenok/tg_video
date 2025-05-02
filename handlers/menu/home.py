"""Обработчики команд меню"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from common import error_handler
import keyboards
from filters.user import IsUser

router = Router()


@router.message(Command('menu'), IsUser())
@error_handler()
async def menu_commnad_handler(message: Message):
    """Показать: Меню пользователя"""
    await message.answer(
        **keyboards.menu.HOME
    )


@router.callback_query(F.data == 'menu', IsUser())
@error_handler()
async def menu_handler(callback_query: CallbackQuery):
    """Показать: Меню пользователя"""
    await callback_query.message.edit_text(
        **keyboards.menu.HOME
    )
