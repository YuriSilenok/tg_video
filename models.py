from datetime import datetime
from peewee import Model, SqliteDatabase, JOIN, fn, BooleanField, FloatField, CharField, IntegerField, ForeignKeyField, DateTimeField

db = SqliteDatabase('sqlite.db')

CASCADE = {
    'on_delete': 'CASCADE',
    'on_update': 'CASCADE',
}


TASK_STATUS = {
    -2: "Без публикации",
    -1: "Брошена",
    0: "Выдана",
    1: "На проверке",
    2: "Ожидает публикации",
    3: "Опубликована",
}

REVIEW_REQUEST_STATUS = {
    0: "На проверке",
    1: "Проверено",
    2: "Не проверено",
}

class Table(Model):
    class Meta:
        database = db

class User(Table):
    tg_id = IntegerField()
    username = CharField(null=True)
    # рейтинг блогера/проверющего
    bloger_rating = FloatField(default=0.8)
    bloger_score = FloatField(default=0)
    reviewer_score = FloatField(default=0)

class Role(Table):
    # Блогер, Проверяющий
    name = CharField()

class UserRole(Table):
    user = ForeignKeyField(User, **CASCADE)
    role = ForeignKeyField(Role, **CASCADE)

class Course(Table):
    title = CharField()

class UserCourse(Table):
    """Желание пользователя записывать видео по этому курсу"""
    user = ForeignKeyField(User, **CASCADE)
    course = ForeignKeyField(Course, backref='usercourse', **CASCADE)

class Theme(Table):
    course = ForeignKeyField(Course, **CASCADE)
    title = CharField()
    url = CharField()
    complexity = IntegerField(default=1)

class Task(Table):
    """Тема выданная для записи видео"""
    implementer = ForeignKeyField(User, **CASCADE)
    theme = ForeignKeyField(Theme, **CASCADE)
    at_created = DateTimeField(default=datetime.now)
    due_date = DateTimeField()
    status = IntegerField(default=0)
    score = FloatField(default=0.0)

class Video(Table):
    """Видео которое было прислано на оценку по задаче"""
    task = ForeignKeyField(Task, **CASCADE)
    file_id = IntegerField()
    at_created = DateTimeField(default=datetime.now)
    duration = IntegerField(default=0)

class ReviewRequest(Table):
    """Видео выданное на проверку проверяющему"""
    reviewer = ForeignKeyField(User, **CASCADE)
    video = ForeignKeyField(Video, **CASCADE)
    status = IntegerField(default=0)
    at_created = DateTimeField(default=datetime.now)
    due_date = DateTimeField()

class Review(Table):
    """Результат проверки видео"""
    review_request = ForeignKeyField(ReviewRequest, **CASCADE)
    score = FloatField()
    comment = CharField()
    at_created = DateTimeField(default=datetime.now)

class Poll(Table):
    message_id = IntegerField()
    poll_id = CharField()
    result = CharField()
    stop = BooleanField(default=False)
    at_created = DateTimeField(default=datetime.now)


def get_videos_by_request_review(user: User):
    """Получить все видео, требующие этого проверяющего"""
    subquery = (
        Video
        .select(Video)
        .join(ReviewRequest, JOIN.LEFT_OUTER)
        .group_by(Video.id)
        .having(fn.COUNT(ReviewRequest.id) < 5))

    # Основной запрос, исключающий задачи, которые были проверены конкретным рецензентом (с tg_id = 1)
    query = (
        subquery
        .where(
            ~Video.id.in_(
                Video
                .select(Video.id)
                .join(ReviewRequest)
                .where(ReviewRequest.reviewer == user)))
        .order_by(Video.id))  # Можно настроить порядок сортировки

    return query

def update_bloger_score_and_rating(bloger: User):

    bloger_rating = (Task
        .select(fn.AVG(Task.score).alias('avg_score'))
        .where(Task.implementer == bloger)
        .scalar()
    )
    bloger.bloger_rating = bloger_rating
    result = f'Ваш рейтинг: {bloger_rating}\n'
    
    bloger_score = 0
    tasks = (Task
        .select()
        .where(Task.implementer == bloger)
    )
    result += f'Видео которые Вы записали были оценены:\n'
    i = 0
    for task in tasks:
        for _ in range(task.theme.complexity):
            k = 1.05**i
            score = task.score * k
            bloger_score += score
            i+=1
            result == f'{task.theme.title} {k}*{task.score}={score}\n'
    bloger.bloger_score = bloger_score
    bloger.save()
    result += f'ИТОГО БАЛЛОВ:{bloger_score}'


def update_reviewer_score(reviewer: User):
    review_requests = (
        ReviewRequest
        .select()
        .join(Video)
        .where(ReviewRequest.reviewer_id == reviewer.id)
    )
    
    reviewer_score = 0
    for review_request in review_requests:
        reviewer_score += review_request.video.duration / 1200
    
    reviewer.reviewer_score = reviewer_score
    reviewer.save()
    return reviewer_score



if __name__ == '__main__':
    db.create_tables([
        User, Role, UserRole,
        Course, Theme, Task, 
        Video, ReviewRequest, Review,
        UserCourse, Poll
    ])