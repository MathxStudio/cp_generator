# Security Policy

## Supported versions

The actively maintained lines are:

- `main`
- the latest tagged `0.2.x` release

Older tags may not receive fixes.

## Reporting a vulnerability

Please do **not** disclose security problems in public commits, pull requests, or discussions.

Use one of these private paths instead:

1. GitHub private vulnerability reporting or a private security advisory, if it is enabled for the repository.
2. Direct contact with the maintainer through the email address or private contact channel published on the repository owner's GitHub profile.

When reporting, include:

- a concise description of the issue
- reproduction steps or a proof of concept
- affected files, workflows, or release assets
- any suggested mitigations

## Scope notes

This project ships desktop bundles, Android debug artifacts, and Python packaging metadata. Security reports are especially useful for:

- malicious or unsafe release artifacts
- workflow or supply-chain weaknesses
- code execution paths involving imported session data
- vulnerabilities in update-channel or release-discovery behavior
