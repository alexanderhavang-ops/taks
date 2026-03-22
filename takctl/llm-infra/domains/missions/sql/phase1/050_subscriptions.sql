-- Mission subscriptions (compact; drop uid/client_uid/username)
SELECT
  mission_id,
  to_char(create_time AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS created_utc,
  role_id
FROM public.mission_subscription
ORDER BY create_time DESC NULLS LAST, mission_id DESC
LIMIT 200;
