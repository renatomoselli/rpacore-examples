# Security Policy

RPA Core Examples contains sample automation code. It is not a sandbox and does
not provide a security boundary around user-authored Python, third-party
websites, local files, desktop applications, or credentials.

## Supported Versions

The examples target the RPA Core release documented in
[README.md](README.md#framework-compatibility). Private forks and local
pre-release edits are not supported release lines.

## Reporting a Vulnerability

If the issue affects the RPA Core framework, generated project defaults, package
contents, persistence, credentials, webhooks, notifications, or public API
behavior, report it through the framework security route:

- <https://github.com/renatomoselli/rpacore/security/advisories/new>

If the issue affects only an example's documentation or sample data, open a
regular issue without secrets, credentials, customer data, or exploit details.

## Sensitive Data

Examples may create transaction databases, logs, reports, screenshots, API
responses, browser artifacts, spreadsheets, PDFs, and output files. Treat these
as potentially sensitive and keep generated outputs out of version control
unless they are intentional test fixtures.
