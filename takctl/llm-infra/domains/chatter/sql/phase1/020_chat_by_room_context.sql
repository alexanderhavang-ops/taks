-- Context by room: newest messages per room (structured); budget applied later
-- NOTE: Avoid hard LIMITs; python fetch cap (max_rows) + phase2 budgeting handles size.

WITH rooms AS (
  SELECT chat_room, MAX(servertime) AS last_seen
  FROM public.cot_router_chat
  WHERE chat_content IS NOT NULL
  AND chat_content <> ''
  AND servertime >= (now() - make_interval(days => {{CHATTER_HISTORY_DAYS}}))
  AND COALESCE(sender_callsign, '') <> 'Martine'
  AND COALESCE(chat_room, '') <> 'Martine'
  GROUP BY chat_room
),
ranked AS (
  SELECT
    c.chat_room,
    c.sender_callsign,
    c.servertime,
    c.id,
    c.chat_content,
    ROW_NUMBER() OVER (
      PARTITION BY c.chat_room
      ORDER BY c.servertime DESC NULLS LAST, c.id DESC
    ) AS rn,
    r.last_seen
  FROM public.cot_router_chat c
  JOIN rooms r
    ON r.chat_room IS NOT DISTINCT FROM c.chat_room
  WHERE c.chat_content IS NOT NULL
    AND c.chat_content <> ''
    AND c.servertime >= (now() - make_interval(days => {{CHATTER_HISTORY_DAYS}}))
    AND COALESCE(c.sender_callsign, '') <> 'Martine'
    AND COALESCE(c.chat_room, '') <> 'Martine'
)
SELECT
  to_char(servertime AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS ts_utc,
  chat_room,
  sender_callsign,
  chat_content
FROM ranked
-- keep a small per-room slice for "context" (not a global LIMIT)
WHERE rn <= 8
ORDER BY last_seen DESC NULLS LAST, chat_room, servertime DESC NULLS LAST, id DESC;
