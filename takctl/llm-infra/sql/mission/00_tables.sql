-- List tables in mission microdomain
SELECT * FROM (VALUES
  ('public.mission'),
  ('public.mission_change'),
  ('public.mission_external_data'),
  ('public.mission_feed'),
  ('public.mission_invitation'),
  ('public.mission_keyword'),
  ('public.mission_layer'),
  ('public.mission_log'),
  ('public.mission_log_hash'),
  ('public.mission_log_keyword'),
  ('public.mission_log_mission_name'),
  ('public.mission_resource'),
  ('public.mission_resource_keyword'),
  ('public.mission_subscription'),
  ('public.mission_uid'),
  ('public.mission_uid_keyword'),
  ('public.permission'),
  ('public.role_permission')
) AS tables(table_name);
