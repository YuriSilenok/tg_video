PRAGMA foreign_keys = 0;

CREATE TABLE sqlitestudio_temp_table AS SELECT *
                                          FROM poll;

DROP TABLE poll;

CREATE TABLE poll (
    id         INTEGER       NOT NULL
                             PRIMARY KEY,
    message_id INTEGER       NOT NULL,
    poll_id    VARCHAR (255) NOT NULL,
    result     VARCHAR (255) NOT NULL,
    at_created DATETIME      NOT NULL,
    stop       INTEGER       DEFAULT (0) 
                             NOT NULL,
    is_delete  INTEGER       DEFAULT (0) 
                             NOT NULL
);

INSERT INTO poll (
                     id,
                     message_id,
                     poll_id,
                     result,
                     at_created,
                     stop
                 )
                 SELECT id,
                        message_id,
                        poll_id,
                        result,
                        at_created,
                        stop
                   FROM sqlitestudio_temp_table;

DROP TABLE sqlitestudio_temp_table;

PRAGMA foreign_keys = 1;

PRAGMA foreign_keys = 0;

CREATE TABLE sqlitestudio_temp_table AS SELECT *
                                          FROM poll;

DROP TABLE poll;

CREATE TABLE poll (
    id         INTEGER       NOT NULL
                             PRIMARY KEY,
    message_id INTEGER       NOT NULL,
    poll_id    VARCHAR (255) NOT NULL,
    result     VARCHAR (255) NOT NULL,
    at_created DATETIME      NOT NULL,
    is_stop    INTEGER       DEFAULT (0) 
                             NOT NULL,
    is_delete  INTEGER       DEFAULT (0) 
                             NOT NULL
);

INSERT INTO poll (
                     id,
                     message_id,
                     poll_id,
                     result,
                     at_created,
                     is_stop,
                     is_delete
                 )
                 SELECT id,
                        message_id,
                        poll_id,
                        result,
                        at_created,
                        stop,
                        is_delete
                   FROM sqlitestudio_temp_table;

DROP TABLE sqlitestudio_temp_table;

PRAGMA foreign_keys = 1;
