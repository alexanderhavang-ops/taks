# Default bundle content

This directory is the **built-in base bundle** shipped with the orchestrator source.

When the orchestrator builds a node bundle, it layers content in this order:

1. `default_bundle/` (this directory)
2. `state/roles/<role>/bundle/` (optional)
3. `state/units/<unit_path>/bundle/` (optional override)

Goal: ensure every bundle has a predictable runner script:

- `install/install.sh`

So cloud-init can extract and run it deterministically.

