"""Create a curated, reproducible source ZIP and SHA-256 manifest; never publish."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from release_files import ROOT, manifest


def export(destination, root=ROOT):
    hashes = manifest(root)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists; choose a new archive name")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in hashes:
            info = zipfile.ZipInfo("beoremote-gateway/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
            archive.writestr(info, (root / name).read_bytes())
        info = zipfile.ZipInfo("beoremote-gateway/SOURCE_MANIFEST.json", date_time=(2026, 1, 1, 0, 0, 0))
        info.external_attr = 0o100644 << 16
        archive.writestr(info, json.dumps(hashes, indent=2, sort_keys=True) + "\n")
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(destination.suffix + ".sha256").write_text(f"{checksum}  {destination.name}\n")
    return len(hashes), checksum


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    count, checksum = export(args.destination)
    print(f"Exported {count} reviewed files: {args.destination}\nSHA-256: {checksum}")
