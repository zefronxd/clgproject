---
name: Python package install manifests
description: Avoid leaving duplicate requirements after installing packages already declared by a Python project.
---

When installing Python packages through the Replit package helper, check the dependency manifest afterward. Installing packages that already exist in `requirements.txt` may append bare duplicate entries even though the project already has version constraints.

**Why:** A redundant manifest edit occurred during a setup install; retaining it weakens the existing version constraints without adding a dependency.

**How to apply:** Keep the runtime installation, but remove duplicate bare package lines and preserve the project's original constraints.
