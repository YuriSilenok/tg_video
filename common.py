from datetime import datetime, timedelta
import functools
from aiogram import Bot, Router
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramAPIError

from models import User


router = Router()

@router.message()
async def other_message(message: Message):
    await message.answer(
        text='Вы совершили незарегистрированное действие, обратитесь к администратору'
    )

@router.callback_query()
async def other_callback(callback: CallbackQuery):
    await callback.message.answer(
        text='Вы совершили незарегистрированное действие, обратитесь к администратору'
    )

def get_id(text):
    return int(text[(text.rfind('_')+1):])

async def get_user(bot: Bot, tg_id: int) -> User:
    user = User.get_or_none(tg_id=tg_id)
    if user is None:
        await bot.send_message(
            chat_id=tg_id,
            text='Пользователь не найден, ведите команду /start'
        )
    return user

def get_date_time(hours:int=0):
    due_date = datetime.now()
    due_date = datetime(
        year=due_date.year,
        month=due_date.month,
        day=due_date.day,
        hour=due_date.hour,
    )
    due_date += timedelta(
        hours=hours
    )
    return due_date



def error_handler():
    """Декоратор для обработки ошибок в хэндлерах и отправки сообщения админу"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                print(f"Ошибка в хэндлере {func.__name__}: {e}")
                if len(args) == 0:
                    return None
                bot: Bot = None
                message: Message = None
                if isinstance(args[0], Message) or isinstance(args[0], CallbackQuery):
                    bot = args[0].bot
                    message = args[0]
                elif isinstance(args[0], Bot):
                    bot = args[0]
                
                if bot is None:
                    return None
                 
                error_text = f"🚨 <b>Ошибка в боте</b>\n\n📌 В хэндлере <b>{func.__name__}</b>\n❗ </b>Ошибка:</b>\n<b>{e}</b>"
                # Отправляем сообщение админу
                try:
                    from admin import send_message_admins
                    await send_message_admins(
                        bot=bot,
                        text=error_text
                    )
                except TelegramAPIError:
                    print("Не удалось отправить сообщение админу.")
                
                if message:
                    await message.answer(
                        text="❌ Произошла ошибка. Администратор уже уведомлён."
                    )
        return wrapper
    return decorator

