---
name: Flask workflow routing
description: Replit port routing behavior for a Python web app added beside the pnpm workspace scaffold.
---

For a root-level Flask webview workflow in this pnpm workspace, add the `.replit` port mapping (`localPort = 5000`, `externalPort = 80`) through the config validator after creating or restarting the workflow.

**Why:** A mapping applied before workflow configuration/restart did not persist, and the shared proxy returned “Backend Not Configured” until the mapping was applied after the workflow was running.

**How to apply:** Configure and start the Python webview first, then validate the root port mapping and confirm the dev domain serves the Flask route.
