SELECT "t1"."id", "t1"."tg_id", "t1"."username", "t1"."bloger_rating", "t1"."bloger_score", "t1"."reviewer_rating", "t1"."reviewer_score", "t1"."comment" 
FROM "user" AS "t1" 
INNER JOIN (
    SELECT "t1"."id", "t1"."tg_id", "t1"."username", "t1"."bloger_rating", "t1"."bloger_score", "t1"."reviewer_rating", "t1"."reviewer_score", "t1"."comment" 
    FROM "user" AS "t1" 
    INNER JOIN "userrole" AS "t2" ON ("t2"."user_id" = "t1"."id") 
    INNER JOIN "role" AS "t3" ON ("t2"."role_id" = "t3"."id") 
    WHERE ("t3"."name" = ?)) AS "t4" ON ("t1"."id" = "t4"."id") 
LEFT OUTER JOIN "reviewrequest" AS "t5" ON ("t4"."id" = "t5"."reviewer_id") 
INNER JOIN "video" AS "t6" ON ("t6"."id" = "t5"."video_id") 
INNER JOIN "task" AS "t7" ON ("t7"."id" = "t6"."task_id") 
WHERE (("t7"."status" = ?) AND ("t5"."reviewer_id" IS NULL)) 
ORDER BY "t1"."reviewer_rating"