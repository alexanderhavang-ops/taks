SELECT
  MAX(time) AS latest_time_utc,
  COUNT(*) AS total_rows,
  COUNT(DISTINCT uid) AS distinct_uids,
  COUNT(DISTINCT cot_type) AS distinct_types
FROM latestcot
WHERE cot_type LIKE 'a-f-%';
