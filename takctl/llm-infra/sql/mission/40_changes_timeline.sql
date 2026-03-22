-- 40 Changes Timeline (bounded, contract-safe)
SELECT
  id,
  mission_id,
  mission_guid,
  mission_name,
  ts,
  change_type,
  creatoruid,
  remote_federated_change,
  servertime
FROM public.mission_change
ORDER BY ts DESC NULLS LAST, id DESC
LIMIT 200;
