# Security model and review

Review date: 30 October 2026. Changes ship in 0.5.1.

This is a code review, regression testing and vulnerability scan, not an
independent penetration test or a guarantee that every issue has been found.

## Access and credentials

The setup page accepts connections only from Supervisor's ingress proxy. A
forwarding header cannot bypass the TCP-peer check. The app also checks the
current HA user's administrator rights through the Core WebSocket API, using
the authenticated `X-Remote-User-Id` header that Supervisor sets. Missing identity,
a non-admin user or a failed lookup denies access.

`panel_admin: true` controls the frontend panel, so it is not sufficient API
authorization by itself. Each write rechecks current permissions. Read checks
are cached for at most 15 seconds, with a bounded cache. Demoting a user therefore
blocks their next write even if a read was recently allowed. This requires a
current HA OS/Supervisor that supplies the authenticated ingress user header.

Writes also require the page's random CSRF token and JSON. Requests have a 16 KiB
body limit. The page uses a nonce-based Content Security Policy and text-only
rendering for device, button and target names. Ingress prefixes cannot change
the request origin. The Supervisor token stays on the server; Core HTTP requests
ignore proxy environment settings and reject redirects. The WebSocket access
check rejects redirects before sending its authentication message.

The app needs `homeassistant_api` to publish events and manage its own ordinary
HA automations. That is powerful access: it is not a per-entity permission. It
has no host-file or Docker-socket mounts and requests no extra Supervisor role.

## Receiver and network boundary

BeoCore/XMPP on this TV has no password exchange or TLS. The receiver checks the
selected TV's IPv4 address and both peer identities, but these are not
cryptographic authentication. Use it on a trusted LAN; do not expose its XMPP
port to the internet or an untrusted network.

XML parsing rejects DTDs and entities and limits size, depth and attributes.
At most four connections from the selected address are accepted. An incomplete
frame has a fixed deadline; sending occasional bytes cannot keep extending it.
An established idle TV connection can stay open normally.

The event queue is bounded. Old events expire, uncertain writes are not retried,
and generated automations check freshness when a queued run actually starts.
Learning withholds the captured press. Saving never executes the chosen action.
The app preserves customized HA rules instead of replacing their contents.

## Issues found and addressed

| Finding | Result in 0.5.1 |
| --- | --- |
| Ingress and panel visibility were treated as sufficient user authorization. | Verify current administrator status before serving the page or API; recheck every write and deny failed checks. |
| A failed switch could keep the previous TV's receiver active. | Close it on failure; keep the new selection and retry it. |
| An unhealthy background task could stay broken without Watchdog. | Rebuild the receiver when the selected TV is rediscovered. |
| A trickling peer could renew the incomplete-frame timeout indefinitely. | Enforce one deadline for the whole partial frame. |
| The event publisher inherited HTTP proxy settings. | Connect directly to the internal Core proxy, without forwarding its token to an environment-configured proxy. |
| Predictable temporary filenames could follow a pre-existing local symlink. | Use exclusive, randomly named files with private permissions and atomic replacement. Exploitation required filesystem access inside the app container. |
| Storage errors produced an unhelpful server error. | Return a bounded, generic error without private filesystem details; preserve the previous settings. |

The protocol's SHA-1 capability hash is compatibility metadata, not authentication.
It is explicitly marked as non-security use; the hash is unchanged.

## Dependency and container results

`pip-audit 2.10.1` found no known vulnerabilities in the 15 resolved runtime and
development Python dependencies checked. Bandit 1.9.4 was also run over the runtime
code. Remaining reports concern the fixed heartbeat path, XML construction and
intentional interface binding; these were reviewed rather than blindly suppressed.
The actual untrusted XML input goes through the bounded Expat parser above.
CI now audits Python requirements and rejects high-severity Bandit findings.

Trivy scanned the built aarch64 image with its current database. Moving from
Debian 12 to Debian 13 and removing the build-time pip installer changed the
result from 2 critical, 64 high, 93 medium, 90 low and 2 unknown package/CVE entries
to 0 critical, 44 high, 58 medium, 61 low and 1 unknown. The latter has no Python
package vulnerability findings. Counts include the same CVE against multiple
binary packages; the 44 high entries represent eight distinct CVEs.

These eight remain in the Debian base, with no fixed version offered by the
scanner for the tested stable-release packages:

| CVE | Component and application assessment |
| --- | --- |
| [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642) | util-linux mount hooks; the app does not invoke mount helpers. |
| [CVE-2026-78408](https://security-tracker.debian.org/tracker/CVE-2026-78408) | nsenter/cgroup operations; the app does not invoke nsenter. |
| [CVE-2026-78409](https://security-tracker.debian.org/tracker/CVE-2026-78409) | mount subtree resolution; the app does not perform these mount operations. |
| [CVE-2026-78410](https://security-tracker.debian.org/tracker/CVE-2026-78410) | restricted bind-mount handling; the app does not create bind mounts. |
| [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369) | libacl filesystem operations; the app does not call the affected ACL API. |
| [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720) | ncurses utilities; the app has no terminal UI and does not invoke them. |
| [CVE-2026-16742](https://security-tracker.debian.org/tracker/CVE-2026-16742) | systemd-homed; this app container does not run that service. |
| [CVE-2026-9538](https://security-tracker.debian.org/tracker/CVE-2026-9538) | Perl archive extraction; the app does not run Perl or extract archives. |

Debian's tracker was checked for all eight: it treats them as minor/deferred
stable-release issues. The application assessment is based on reviewed call
paths, not proof that the base image is free of exploitable vulnerabilities.
The app runs as the image's default root user within the container. Host
networking is needed for TV discovery; isolation still depends on HA's app
protections and the trusted LAN. Keep the official base image and HA host updated.

## Validation and limits

Regression checks cover non-admin/missing identity, role revocation, access-check
failure and redirects, proxy credential routing, trickled frames, failed TV
switches, unhealthy workers, temporary-file symlinks and unavailable storage.
All 100 gateway, authorization, automation and source-export tests passed locally.
A real isolated Core fixture allowed owners/admins, denied regular users and
rejected a demoted admin's next write despite previously cached read access.

The public repository's eight existing commits were checked for the project's
credential, private-network, device-identity and personal-path patterns. No
matches were found; author and committer addresses used GitHub's no-reply form.
Pattern scanning cannot prove that no sensitive data exists.

The review used test devices and isolated HA Core 2026.10.4, not attacks against
household equipment. Supervisor's identity-header and WebSocket contracts were
checked in its 2026.10.0 source. A physical button check after upgrading remains
necessary, as does a full test of the deployed Supervisor ingress path.

### Source-extension development candidate

The 0.6.0 development candidate keeps the 0.5.1 administrator, ingress and
write-token boundary. Its new routes accept only a source opt-in boolean or an
empty inventory request; they do not accept an address or free ADB command.
The selected product's native `/BeoDevice` identity is checked before using its
current or remembered receiver IP. This prevents accidental device mix-ups on
the trusted LAN; the TV's HTTP identity is not cryptographic authentication.
Identity replies are bounded, time-limited and read without redirects or proxy
environment settings.

ADB uses a private persistent key and a separate loopback daemon. Only fixed
model, Android-version and package-list commands are offered. Turning off the
extension or closing the app stops its own daemon. No helper APK installer or
TV source writes are implemented yet. The standalone players remain outside
its management. The OS-package scan counts above describe 0.5.1, not the newly
added Debian ADB packages; the candidate has not received a new full image scan.

Relevant upstream code:
[Core ingress session identity](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/hassio/websocket_api.py),
[Supervisor ingress headers](https://github.com/home-assistant/supervisor/blob/2026.10.0/supervisor/api/ingress.py),
[Core user roles](https://github.com/home-assistant/core/blob/2026.10.4/homeassistant/components/config/auth.py).
