-- Link mission chatrooms to chat stream (structural join); budget applied later
-- NOTE: Do NOT LIMIT here.

SELECT
  m.guid AS mission_guid,
  m.name AS mission_name,
  NULLIF(m.chatroom,'') AS mission_chatroom,
  to_char(c.servertime AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS ts_utc,
  c.sender_callsign,
  c.chat_content
FROM public.mission m
JOIN public.cot_router_chat c
  ON NULLIF(m.chatroom,'') IS NOT NULL
 AND c.chat_room = NULLIF(m.chatroom,'')
WHERE c.chat_content IS NOT NULL AND c.chat_content <> ''
ORDER BY c.servertime DESC NULLS LAST, c.id DESC;
