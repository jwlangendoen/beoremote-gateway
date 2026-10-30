"""Create a clean local HA-app archive, excluding caches and editor metadata."""
import argparse
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def package(destination):
    app = ROOT / "beoremote_gateway"
    root_files = {"config.yaml", "Dockerfile", ".dockerignore", "requirements.txt",
                  "README.md", "DOCS.md", "CHANGELOG.md", "LICENSE", "icon.png", "logo.png"}
    with tarfile.open(destination, "w:gz") as archive:
        for path in sorted(app.rglob("*")):
            relative = path.relative_to(app)
            allowed = ((len(relative.parts) == 1 and path.name in root_files)
                       or (relative.parts[0] == "gateway" and path.suffix == ".py"))
            if (not allowed or path.is_symlink() or not path.is_file()
                    or "__pycache__" in path.parts or path.name.startswith("._")):
                continue
            info = archive.gettarinfo(str(path), arcname=str(path.relative_to(ROOT)))
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            with path.open("rb") as source:
                archive.addfile(info, source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    package(args.destination)
    print(f"Packaged local HA app: {args.destination}")
