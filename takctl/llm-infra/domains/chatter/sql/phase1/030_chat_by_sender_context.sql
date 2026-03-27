-- Context by sender: newest messages per sender (structured); budget applied later
-- NOTE: Avoid hard LIMITs; python fetch cap (max_rows) + phase2 budgeting handles size.

WITH senders AS (
  SELECT sender_callsign, MAX(servertime) AS last_seen
  FROM public.cot_router_chat
  WHERE chat_content IS NOT NULL
  AND chat_content <> ''
  AND servertime >= (now() - make_interval(days => {{CHATTER_HISTORY_DAYS}}))
  AND COALESCE(sender_callsign, '') <> 'Martine'
  AND COALESCE(chat_room, '') <> 'Martine'
  GROUP BY sender_callsign
),
ranked AS (
  SELECT
    c.sender_callsign,
    c.chat_room,
    c.servertime,
    c.id,
    c.chat_content,
    ROW_NUMBER() OVER (
      PARTITION BY c.sender_callsign
      ORDER BY c.servertime DESC NULLS LAST, c.id DESC
    ) AS rn,
    s.last_seen
  FROM public.cot_router_chat c
  JOIN senders s
    ON s.sender_callsign IS NOT DISTINCT FROM c.sender_callsign
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
-- keep a small per-sender slice for "context" (not a global LIMIT)
WHERE rn <= 6
ORDER BY last_seen DESC NULLS LAST, sender_callsign, servertime DESC NULLS LAST, id DESC;
