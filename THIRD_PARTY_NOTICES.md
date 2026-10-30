# Third-party software

The MIT license applies to project-owned code and documentation. Dependencies
retain their own licenses and notices:

| Dependency | Version | Upstream |
| --- | --- | --- |
| Python | 3.13 in the container | https://www.python.org/psf/license/ |
| zeroconf | 0.151.5 | https://github.com/python-zeroconf/python-zeroconf |
| ifaddr | 0.2.0 | https://github.com/ifaddr/ifaddr |

The official `python:3.13-slim-bookworm` base image also includes Debian packages
with their own notices. Installed dependency packages retain upstream license
files and metadata. PyYAML and Jinja2 are development dependencies, not runtime
dependencies of the gateway container.

Bang & Olufsen, Beoremote and Beovision are names of their respective owners.
This is an independent community project. No B&O firmware, proprietary libraries,
brand fonts, logos, private device captures or account credentials are distributed.
