"""Собираем основные классы из всех модулей в один пакет"""
# flake8: noqa: F401
from models.user import User
from models.role import Role
from models.user_role import UserRole
from models.course import Course
from models.theme import Theme
from models.task import Task
from models.video import Video
from models.review_request import ReviewRequest
from models.review import Review
from models.user_course import UserCourse
from models.poll import Poll
