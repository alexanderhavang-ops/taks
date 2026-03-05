-- Mission list (compact; no uid/creator noise; timestamps shortened)
SELECT
  to_char(create_time AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS created_utc,
  to_char(last_edited AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS edited_utc,
  guid AS mission_guid,
  name AS mission_name,
  tool,
  invite_only,
  expiration
FROM public.mission
ORDER BY create_time DESC NULLS LAST
LIMIT 200;
