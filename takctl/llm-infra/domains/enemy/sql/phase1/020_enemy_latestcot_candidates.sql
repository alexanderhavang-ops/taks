SELECT
  uid,
  cot_type,
  how,
  to_char(time AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SSOF') AS time_utc,
  to_char(stale AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SSOF') AS stale_utc,
  event_pt::text AS point_wkb_hex,
  detail AS detail_xml
FROM public.latestcot
WHERE
  time >= (now() - make_interval(days => {{ENEMY_HISTORY_DAYS}}))
  AND (
       lower(coalesce(detail, '')) LIKE '%enemy%'
    OR lower(coalesce(detail, '')) LIKE '%fiend%'
    OR lower(coalesce(detail, '')) LIKE '%hostile%'
    OR lower(coalesce(detail, '')) LIKE '%armor%'
    OR lower(coalesce(detail, '')) LIKE '%infantry%'
    OR lower(coalesce(detail, '')) LIKE '%landstigningsstyrka%'
    OR lower(coalesce(detail, '')) LIKE '%rysk%'
  )
  AND lower(coalesce(detail, '')) NOT LIKE '%martine%'
  AND lower(coalesce(detail, '')) NOT LIKE '%where is martine state stored%'
  AND lower(coalesce(detail, '')) NOT LIKE '%var lagras martines state%'
ORDER BY time DESC
LIMIT 500;
