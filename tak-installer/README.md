# TAK Installer

Manages the installation of TAK node runtime components, including nginx and certificates. The installer handles certificate installation, verification, and nginx reloading.

Certificates are provided by the orchestrator.

## takctl web UI

### Tabs
- Users
- Clients
- Onboarding (wires `components/Onboarding.js` into the static UI)
- CRL
- Certs

### Instance branding (logos + slogan)
Uploads live in runtime state:
- `/opt/tak/tools/takctl/user-uploads/` (user-provided originals, e.g. `logo1.svg`, `logo3.png`, `slogan.txt`)

The installer exposes stable asset paths for the UI:
- `/takctl/assets/logoN.svg` (always exists; may be a wrapper that references the underlying raster)
- `/takctl/assets/topbar/logoN.png` (derived 360×96 banner PNG for topbar usage; generated without overwriting uploads)

Notes:
- Derived topbar PNGs are created by `tak-installer apply` (action: `takctl-user-uploads`).
- The UI prefers topbar-derived PNGs first, then falls back to SVG/raster assets.

