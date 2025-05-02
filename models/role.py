from peewee import CharField

from models.base import Table


class Role(Table):
    name = CharField()
