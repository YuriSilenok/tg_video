PRAGMA foreign_keys = 0;

CREATE TABLE sqlitestudio_temp_table AS SELECT *
                                          FROM theme;

DROP TABLE theme;

CREATE TABLE theme (
    id         INTEGER       NOT NULL
                             PRIMARY KEY,
    course_id  INTEGER       NOT NULL,
    title      VARCHAR (255) NOT NULL,
    url        VARCHAR (255) NOT NULL,
    complexity REAL          NOT NULL
                             DEFAULT (1),
    FOREIGN KEY (
        course_id
    )
    REFERENCES course (id) ON DELETE CASCADE
                           ON UPDATE CASCADE
);

INSERT INTO theme (
                      id,
                      course_id,
                      title,
                      url,
                      complexity
                  )
                  SELECT id,
                         course_id,
                         title,
                         url,
                         complexity
                    FROM sqlitestudio_temp_table;

DROP TABLE sqlitestudio_temp_table;

CREATE INDEX theme_course_id ON theme (
    "course_id"
);

PRAGMA foreign_keys = 1;
