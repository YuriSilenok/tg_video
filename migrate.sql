PRAGMA foreign_keys = 0;

CREATE TABLE sqlitestudio_temp_table AS SELECT *
                                          FROM user;

DROP TABLE user;

CREATE TABLE user (
    id              INTEGER       NOT NULL
                                  PRIMARY KEY,
    tg_id           INTEGER       NOT NULL,
    username        VARCHAR (255) UNIQUE,
    bloger_rating   REAL          NOT NULL
                                  DEFAULT (0.8),
    bloger_score    REAL          NOT NULL
                                  DEFAULT (0),
    reviewer_score  REAL          DEFAULT (0) 
                                  NOT NULL,
    comment         VARCHAR (255),
    reviewer_rating REAL          NOT NULL
                                  DEFAULT (0) 
);

INSERT INTO user (
                     id,
                     tg_id,
                     username,
                     bloger_rating,
                     bloger_score,
                     reviewer_score,
                     comment
                 )
                 SELECT id,
                        tg_id,
                        username,
                        bloger_rating,
                        bloger_score,
                        reviewer_score,
                        comment
                   FROM sqlitestudio_temp_table;

DROP TABLE sqlitestudio_temp_table;

PRAGMA foreign_keys = 1;
