PRAGMA foreign_keys = 0;

CREATE TABLE sqlitestudio_temp_table AS SELECT *
                                          FROM task;

DROP TABLE task;

CREATE TABLE task (
    id             INTEGER  NOT NULL
                            PRIMARY KEY,
    implementer_id INTEGER  NOT NULL,
    theme_id       INTEGER  NOT NULL,
    due_date       DATETIME NOT NULL,
    score          REAL     NOT NULL
                            DEFAULT (0),
    at_created     DATETIME NOT NULL,
    status         INTEGER  NOT NULL
                            DEFAULT (0),
    extension      INTEGER  NOT NULL
                            DEFAULT (0),
    FOREIGN KEY (
        implementer_id
    )
    REFERENCES user (id) ON DELETE CASCADE
                         ON UPDATE CASCADE,
    FOREIGN KEY (
        theme_id
    )
    REFERENCES theme (id) ON DELETE CASCADE
                          ON UPDATE CASCADE
);

INSERT INTO task (
                     id,
                     implementer_id,
                     theme_id,
                     due_date,
                     score,
                     at_created,
                     status
                 )
                 SELECT id,
                        implementer_id,
                        theme_id,
                        due_date,
                        score,
                        at_created,
                        status
                   FROM sqlitestudio_temp_table;

DROP TABLE sqlitestudio_temp_table;

CREATE INDEX task_implementer_id ON task (
    "implementer_id"
);

CREATE INDEX task_theme_id ON task (
    "theme_id"
);

PRAGMA foreign_keys = 1;
