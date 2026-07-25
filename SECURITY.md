# Security Policy

Security fixes are provided for the latest release. Report suspected
vulnerabilities with **Report a vulnerability** in the repository's Security
section. If that form is unavailable, open a non-sensitive issue asking for a
private contact channel without including vulnerability details.

Do not open a public issue containing an exploitable vulnerability,
credentials, private network configuration, or identifying client data.

Never include bearer tokens, authorization headers, router configuration,
diagnostic bundles, or raw client identity lists in reports. Rotate an observer
token immediately if it may have been exposed.

The integration rejects URL syntax and credentials in host input, does not
follow REST redirects, bounds protocol input, verifies TLS by default when TLS
is selected, and never silently downgrades to HTTP. The reference observer uses
HTTP by default, so operators must protect the bearer token with a trusted
management network or a correctly configured TLS endpoint.
