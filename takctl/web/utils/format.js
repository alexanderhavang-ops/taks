function fmtTs(ts) {
  if (!ts) return "";
  // accept ISO strings or epoch-ish numbers
  const d = (typeof ts === "number") ? new Date(ts) : new Date(String(ts));
  if (isNaN(d.getTime())) return String(ts);
  return d.toISOString().replace("T", " ").replace("Z", "Z");
}
