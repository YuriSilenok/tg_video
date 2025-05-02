from peewee import ForeignKeyField
from models.user import User
from models.role import Role
from models.base import Table, CASCADE


class UserRole(Table):
    user: User = ForeignKeyField(
        User,
        backref='user_roles',
        **CASCADE
    )
    role: Role = ForeignKeyField(
        Role,
        **CASCADE
    )
