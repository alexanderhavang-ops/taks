-- Mission invitations (compact; drop invitee/creator_uid)
SELECT
  mission_guid,
  mission_name,
  type,
  to_char(create_time AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS created_utc,
  role_id
FROM public.mission_invitation
ORDER BY create_time DESC NULLS LAST
LIMIT 200;
