# Security Policy

## Why this matters here

steph reads every command and every output of the shell it wraps, decides what to speak
aloud, and can invoke a local or remote LLM through a proxy. A vulnerability in this
pipeline could leak shell content (including secrets typed or displayed on screen), or let
crafted terminal output influence the model into a harmful action. Report anything of this
shape here rather than in a public issue.

## Reporting a vulnerability

**Do not open a public GitHub issue for a security report.**

Email **luis@lsmdx.com** with:

- a description of the issue and its potential impact;
- steps to reproduce, or a proof of concept;
- the affected version or commit;
- your assessment of severity, if you have one.

You should get an acknowledgment within 5 business days. We aim to confirm the issue and
share a remediation plan within 15 business days of the acknowledgment; complex issues may
take longer, and we will keep you posted.

## Scope

| In scope | Out of scope |
|---|---|
| `src/steph/` (shell integration, proxy, LLM calls, TTS) | Social engineering against the maintainer |
| `bench/matrix/finetune/` (PII handling of the training corpus, `audit_pii.py`, `clean_pii.py`) | Denial of service against a self-hosted model server you control |
| `benchmark/` (data anonymization pipeline) | Findings that require physical access to the user's machine |
| The install script (`scripts/install.sh`) and shell integration files | Vulnerabilities in third-party dependencies already tracked upstream (report to them; ping us if steph should pin around it) |

## Disclosure

We prefer coordinated disclosure: please give us the chance to ship a fix before any
public write-up. We will credit you in the release notes unless you ask not to be named.

## Supported versions

steph does not yet publish stable version branches; security fixes land on `master`
(private repository, `tutozz/steph`) and ship in the next release. This will be revisited
once a public release exists.
