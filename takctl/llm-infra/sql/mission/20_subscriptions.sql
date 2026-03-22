-- 20 Subscriptions (bounded, contract-safe)
SELECT
  mission_id,
  uid,
  username,
  client_uid,
  create_time,
  role_id
FROM public.mission_subscription
ORDER BY create_time DESC NULLS LAST, mission_id DESC
LIMIT 200;
