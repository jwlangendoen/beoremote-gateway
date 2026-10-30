# Building a release

Run the checks, then make a source archive:

```sh
.venv/bin/python tools/check_release.py
PYTHONPATH=beoremote_gateway .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/export_release.py .release/beoremote-gateway-0.3.0-source.zip
```

The export includes the source, tests and documentation needed to build the app.
Local settings, captures, backups and Git history stay out. The archive contains a
SHA-256 manifest, with a checksum alongside the ZIP. Review the files before sharing.
The export script won't overwrite an existing archive.

## Check the containers

```sh
docker build --platform linux/arm64 --build-arg BUILD_ARCH=aarch64 -t beoremote-gateway:0.3.0-arm64 beoremote_gateway
bash tools/container_check.sh beoremote-gateway:0.3.0-arm64
docker build --platform linux/amd64 --build-arg BUILD_ARCH=amd64 -t beoremote-gateway:0.3.0-amd64 beoremote_gateway
bash tools/container_check.sh beoremote-gateway:0.3.0-amd64
```

The container check starts the app with empty settings and external networking off.
It checks auto/disabled startup without a selected TV, the ingress access gate,
the heartbeat and a clean shutdown. Running a different CPU architecture
requires emulation. The Python base image uses a maintained tag.

## Release checks

Check a fresh installation, import the blueprint, then try a real LIGHT press in
Dry run. Check the trace before testing a live action. Record the TV model and
firmware in [testing notes](TESTING.md).

Keep the app's version, Python version string and Docker label in sync, and add
user-facing changes to the changelog. Early releases use `stage: experimental`
and a GitHub pre-release tag, such as `v0.3.0`.

Keep the repository URL stable: Home Assistant uses it to identify the app.
A local-app installation and a repository installation are separate installs.
If you're moving between them, stop the old gateway before starting the new one
with the same port and identity.
