# Business packet diagnostics

Administrator-only Business MCP tools `taks_node_network_capture_start` and `taks_node_network_capture_status` diagnose TAK, XMPP, Mumble or other service connections. Martine has the same start/status tools. Normal users cannot start or read captures.

Start with `ports:[8446,8089]`, `host_ip:""`, `syn_only:true`, `seconds:60` to discover clients attempting connections. Poll the returned capture ID. Repeat with a discovered numeric client IP and `syn_only:false` to see SYN/SYN-ACK/ACK/reset/FIN counts and UDP metadata. A port list is optional with a specific IP; an unfiltered whole-host capture is rejected. Up to 16 ports and 60 seconds are accepted. Default ports cover HTTPS, TAK, XMPP and Mumble.

A socket-activated DynamicUser service invokes tcpdump with CAP_NET_RAW only, validated arguments, no promiscuous mode, no shell and no arbitrary BPF. Its root-owned Unix socket permits root and the TAKS service identity; no sudo rule is installed. There is one capture at a time, a 4,096 packet limit and 128 returned flows. Results include only addresses, ports, flags, counts and times; raw packet payloads, pcap files, names and tcpdump output are not returned or persisted. Jobs are bound to the requesting administrator and expire from storage after 24 hours. Startup/capture errors contain no raw command output.

A SYN without a SYN-ACK suggests a transport/listener/filtering problem; a reset is distinct from an accepted connection. No observed SYN alone cannot distinguish no client attempt, wrong address, upstream filtering, or capture timing. TCP success does not prove certificate enrollment, application authentication or audio delivery; correlate with Marti and native service diagnostics.

## Deployment and validation

The user explicitly approved installing and enabling the non-root CAP_NET_RAW service. The earlier NOPASSWD root-helper design was discarded. The installer action `takctl-network-diagnostics` installs a root-owned helper, a restricted socket and a hardened DynamicUser service. No additional approval for that same capability grant is pending.

Source integration and unit tests do not establish live activation. Before declaring capture operational, update the node bundle source, create and verify a fresh state backup, select it for restore, replace the node, and verify actual SYN discovery plus a client-IP follow-up. Also verify normal users cannot start or read captures. A missing socket returns `setup_required`.
