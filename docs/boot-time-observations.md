# TAKS cow boot-to-ready observations

Authoritative event timestamps are UTC from the TAKS orchestrator's EC2 launch record and node installer events. `status=online` alone is **not** the ready gate: it can appear while `install/main` is still running.

**Ready means:** latest `install/main` event is `succeeded`, `taks-node-health` is `succeeded`, there are zero failed installer steps, and critical TAK/Martine health checks pass. For SDK-enabled cows, `martine-tests` and `martine-live-tests` must also succeed.

| Date (UTC) | Node / EC2 instance | Instance type | AWS launch | install/main started | install/main succeeded | Launch-to-ready |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-11-09 | taklabs / i-00779097ea6c059cc | t3.medium | 00:48:01 | 00:48:34 | 00:56:40 | **8m39s** |
| 2026-11-09 | taklabs / i-00108e7de0de52e5d | t3.medium | 08:09:48 | 08:10:28 | 08:18:54 | **9m06s** |

For the 08:09 launch: `martine-tests` succeeded at 08:16:51 UTC, `martine-live-tests` succeeded at 08:17:04 UTC, `taks-node-health` at 08:18:54 UTC. Installer summary: 53 completed, zero failed.

**Working expectation:** about **9 minutes** for a fresh t3.medium TAK node to reach installer-complete, based on only two samples (mean 8m52.5s). Start investigating when a boot exceeds **12 minutes** or if the same step stops progressing; this is an operational heuristic, not an SLO. Prefer reading installer event timestamps rather than polling continuously.

The older sample is not evidence that the paid API test ran: its installer had an offline Martine test gate only. These timings exclude client-side DNS propagation delays and any later manually requested onboarding.
