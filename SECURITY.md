# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Respectlytics, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### Contact

Email: [respectlytics@loheden.com](mailto:respectlytics@loheden.com)

Subject line: `[SECURITY] Brief description`

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

### Response Timeline

- **Acknowledgment:** Within 48 hours
- **Assessment:** Within 7 days
- **Fix timeline:** Depends on severity, typically within 30 days

### Scope

In scope:
- Authentication and authorization bypasses
- Data exposure (analytics data leaking between apps)
- SQL injection, XSS, CSRF vulnerabilities
- Rate limiting bypasses
- API key security issues

Out of scope:
- Denial of service attacks (volumetric)
- Social engineering
- Issues in third-party dependencies (report upstream)
- Issues requiring physical access to the server

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest release | Yes |
| Previous release | Security fixes only |
| Older versions | No |

## Acknowledgments

We appreciate security researchers who help keep Respectlytics safe. With your permission, we'll credit you in our release notes.
