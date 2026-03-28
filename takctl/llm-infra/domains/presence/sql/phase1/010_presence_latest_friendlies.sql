SELECT
  time AS time_utc,
  stale AS stale_utc,
  uid,
  cot_type,
  how,
  event_pt::text AS event_pt,
  left(detail, 1200) AS detail_xml
FROM latestcot
WHERE cot_type LIKE 'a-f-%'
  AND time >= (now() - make_interval(hours => {{PRESENCE_HISTORY_HOURS}}))
ORDER BY time DESC NULLS LAST
LIMIT 50;
