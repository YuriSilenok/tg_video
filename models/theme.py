from peewee import ForeignKeyField, CharField, FloatField
from models.base import Table, CASCADE
from models.course import Course


class Theme(Table):
    course: Course = ForeignKeyField(
        Course,
        backref='themes',
        **CASCADE
    )
    title = CharField()
    url = CharField()
    complexity = FloatField(default=1.0)

    @property
    def link(self):
        return f'<a href="{self.url}">{self.title}</a>'
