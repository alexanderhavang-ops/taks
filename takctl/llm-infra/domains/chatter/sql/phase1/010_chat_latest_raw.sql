-- Latest chat messages (full fidelity; budget applied later)
-- NOTE: Do NOT LIMIT here.

SELECT
  to_char(servertime AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS ts_utc,
  chat_room,
  sender_callsign,
  chat_content
FROM public.cot_router_chat
WHERE chat_content IS NOT NULL
  AND chat_content <> ''
  AND servertime >= (now() - make_interval(days => {{CHATTER_HISTORY_DAYS}}))
  AND COALESCE(sender_callsign, '') <> 'Martine'
  AND COALESCE(chat_room, '') <> 'Martine'
ORDER BY servertime DESC NULLS LAST, id DESC;
