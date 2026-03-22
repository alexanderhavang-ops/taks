-- 30 Invitations (bounded, contract-safe)
SELECT
  id,
  mission_id,
  mission_guid,
  mission_name,
  invitee,
  type,
  creator_uid,
  create_time,
  role_id
FROM public.mission_invitation
ORDER BY create_time DESC NULLS LAST, id DESC
LIMIT 200;
