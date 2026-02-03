> [!IMPORTANT] Non-authoritative
> This document is **background**. For authoritative contracts, start at:
> - `docs/contracts/README.md`

# TAK Offline Bundle

Goal: install a TAK node on Ubuntu 22.04 with no internet access.

## Contents
- bundle/debs/ : all required Ubuntu .deb packages + dependencies
- bundle/tak/takserver.deb : TAK server .deb (stable name)
- bundle/tools/ : optional tools (takctl offline tarball later)

## Usage (on airgapped node)
1) Copy the bundle to /opt/taks/offline-bundle/
2) Run tak-install with INSTALL_MODE=offline
