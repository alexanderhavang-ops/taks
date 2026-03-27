-- Chatter metadata summary

SELECT
  to_char(MAX(servertime) AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS latest_ts_utc,
  COUNT(*) AS total_msgs,
  COUNT(DISTINCT chat_room) AS distinct_rooms,
  COUNT(DISTINCT sender_callsign) AS distinct_senders
FROM public.cot_router_chat
WHERE chat_content IS NOT NULL
  AND chat_content <> ''
  AND servertime >= (now() - make_interval(days => {{CHATTER_HISTORY_DAYS}}))
  AND COALESCE(sender_callsign, '') <> 'Martine'
  AND COALESCE(chat_room, '') <> 'Martine';
