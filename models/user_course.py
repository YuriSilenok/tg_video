from peewee import ForeignKeyField
from models.user import User
from models.course import Course
from models.base import Table, CASCADE


class UserCourse(Table):
    """Желание пользователя записывать видео по этому курсу"""
    user = ForeignKeyField(
        User,
        **CASCADE
    )
    course = ForeignKeyField(
        Course,
        backref='user_course',
        **CASCADE)
