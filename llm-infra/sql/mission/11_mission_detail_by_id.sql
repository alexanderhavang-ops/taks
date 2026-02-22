-- Mission detail (deterministic single row, contract-safe)
-- NOTE: Intentionally excludes spatial/large fields (bbox, bounding_polygon, groups, etc).
SELECT
  id,
  guid,
  name,
  creatoruid,
  create_time,
  tool,
  description,
  parent_mission_id,
  default_role_id,
  invite_only,
  expiration,
  last_edited,
  classification
FROM public.mission
ORDER BY last_edited DESC NULLS LAST, create_time DESC NULLS LAST, id DESC
LIMIT 1;
