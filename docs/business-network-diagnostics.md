# Business packet diagnostics

Administrator-only Business MCP tools `taks_node_network_capture_start` and `taks_node_network_capture_status` diagnose TAK, XMPP, Mumble or other service connections. Martine has the same start/status tools. Normal users cannot start or read captures.

Start with `ports:[8446,8089]`, `host_ip:""`, `syn_only:true`, `seconds:60` to discover clients attempting connections. Poll the returned capture ID. Repeat with a discovered numeric client IP and `syn_only:false` to see SYN/SYN-ACK/ACK/reset/FIN counts and UDP metadata. A port list is optional with a specific IP; an unfiltered whole-host capture is rejected. Up to 16 ports and 60 seconds are accepted. Default ports cover HTTPS, TAK, XMPP and Mumble.

A root-owned fixed helper invokes tcpdump with validated arguments, no shell and no arbitrary BPF. There is one capture at a time, a 4,096 packet limit and 128 returned flows. Results include only addresses, ports, flags, counts and times; raw packet payloads, pcap files, names and tcpdump output are not returned or persisted. Jobs are bound to the requesting administrator and expire from storage after 24 hours. Startup/capture errors contain no raw command output.

A SYN without a SYN-ACK suggests a transport/listener/filtering problem; a reset is distinct from an accepted connection. No observed SYN alone cannot distinguish no client attempt, wrong address, upstream filtering, or capture timing. TCP success does not prove certificate enrollment, application authentication or audio delivery; correlate with Marti and native service diagnostics.

Deployment status: the helper and tests are prepared. The installer action and sudo rule are withheld pending explicit approval of the fixed root helper privilege. Without that helper, start returns setup_required and executes no capture.

## Explicit deployment blockers

1. Initial NOPASSWD sudo-helper proposal: rejected by automatic approval review because a persistent root-execution grant had not been explicitly approved. Superseded; do not deploy that design.
2. Revised capability-only proposal: rejected because installing/enabling a persistent systemd socket and DynamicUser service with CAP_NET_RAW had not been explicitly approved. This is the active blocker.

The revised service uses no sudo rule, no root service account, CAP_NET_RAW only, no promiscuous mode, a root-owned Unix socket restricted to the TAKS process, fixed validated filters, 60-second/4,096-packet limits, a read-only system filesystem and no payload/pcap output. It remains uninstalled pending explicit approval. Live capture validation is also pending; parsed-packet and role-isolation tests pass.
