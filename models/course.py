from peewee import CharField
from models.base import Table


class Course(Table):
    """Курсы"""
    title = CharField()
