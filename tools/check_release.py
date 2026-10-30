"""Validate public metadata, blueprint and source boundary without network access."""
import ast
from pathlib import Path
import re
import sys

import yaml

from release_files import ROOT, manifest

sys.path.insert(0, str(ROOT / "beoremote_gateway"))
from gateway.config import Options


class BlueprintLoader(yaml.SafeLoader):
    pass


BlueprintLoader.add_constructor("!input", lambda loader, node: {"input": loader.construct_scalar(node)})


def load_blueprint():
    return yaml.load((ROOT / "blueprints/automation/beoremote_light_action.yaml").read_text(),
                     Loader=BlueprintLoader)


def check():
    app = ROOT / "beoremote_gateway"
    config = yaml.safe_load((app / "config.yaml").read_text())
    versions = [node.value.value for node in ast.parse((app / "gateway/__init__.py").read_text()).body
                if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)]
    assert versions == [config["version"]], "Runtime/app versions differ"
    docker_version = re.search(r"^ARG BUILD_VERSION=(.+)$", (app / "Dockerfile").read_text(), re.M).group(1)
    assert docker_version == config["version"], "Docker version differs"
    assert f'# Beoremote Gateway {config["version"]}' in (app / "DOCS.md").read_text()
    defaults = Options.from_dict(config["options"])
    assert defaults.mode == "auto" and defaults.publish_ha_events is False
    assert config["ingress"] is True and config["ingress_port"] == 0
    assert not any(defaults.as_dict()[key] for key in ("horizon_address", "horizon_jid", "advertise_address"))
    assert set(config["options"]) == set(config["schema"])
    assert config["stage"] == "experimental"
    assert config["arch"] == ["aarch64", "amd64"]
    assert "image" not in config, "First release builds from source on the user's HA host"
    assert (ROOT / "LICENSE").read_bytes() == (app / "LICENSE").read_bytes()
    repo = yaml.safe_load((ROOT / "repository.yaml").read_text())
    assert repo["url"] == config["url"] == "https://github.com/jwlangendoen/beoremote-gateway"
    blueprint = load_blueprint()
    assert blueprint["blueprint"]["domain"] == "automation"
    inputs = blueprint["blueprint"]["input"]
    assert inputs["dry_run"]["default"] is True
    assert inputs["button_action"]["default"] == []
    assert blueprint["triggers"][0]["event_type"] == "beoremote_telegram"
    for choice in inputs["light_payload"]["selector"]["select"]["options"]:
        raw = bytes.fromhex(choice["value"])
        assert len(raw) == 13 and raw[1] == 27 and raw[4] != 126
    hashes = manifest()
    print(f'Release {config["version"]}: {len(hashes)} public files, metadata and setup defaults valid')


if __name__ == "__main__":
    check()
