-- Mission change timeline (compact)
SELECT
  mission_guid,
  mission_name,
  to_char(ts AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS ts_utc,
  change_type
FROM public.mission_change
ORDER BY ts DESC NULLS LAST
LIMIT 200;
