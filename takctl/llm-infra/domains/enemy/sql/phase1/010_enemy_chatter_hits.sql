SELECT
  to_char(time AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS ts_utc,
  chat_room,
  sender_callsign,
  chat_content
FROM public.cot_router_chat
WHERE
  chat_content IS NOT NULL
  AND time >= (now() - make_interval(days => {{ENEMY_HISTORY_DAYS}}))
  AND (
       lower(chat_content) LIKE '%enemy%'
    OR lower(chat_content) LIKE '%fiend%'
    OR lower(chat_content) LIKE '%hostile%'
    OR lower(chat_content) LIKE '%armor%'
    OR lower(chat_content) LIKE '%infantry%'
  )
ORDER BY time DESC
LIMIT 200;
