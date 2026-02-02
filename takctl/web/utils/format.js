/* Global helpers for takctl-web (no build step).
 *
 * - fmtTs(ts): small timestamp formatter
 * - h(...): React.createElement shorthand used across components
 */

function fmtTs(ts) {
  if (!ts) return "";
  // accept ISO strings or epoch-ish numbers
  const d = (typeof ts === "number") ? new Date(ts) : new Date(String(ts));
  if (isNaN(d.getTime())) return String(ts);
  return d.toISOString().replace("T", " ").replace("Z", "Z");
}

// React element helper: h(type, props, ...children)
(function () {
  function h(type, props) {
    const children = [];
    for (let i = 2; i < arguments.length; i++) children.push(arguments[i]);
    return React.createElement.apply(React, [type, props].concat(children));
  }
  window.h = h;
})();
