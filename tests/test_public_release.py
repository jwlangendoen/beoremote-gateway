import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock
import zipfile

from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from check_release import load_blueprint
from discover import Listener, describe
from export_release import export
from release_files import manifest, privacy_issues, public_files


class SourceExportTests(unittest.TestCase):
    def test_export_excludes_household_files_and_verifies_every_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            sentinel = "PRIVATE_" + "SENTINEL"
            for name in public_files():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, path)
            for name in (".local/options.json", "home_assistant/private.json", "docs/verified-behaviour.json",
                         "beoremote_gateway/gateway/private.py", "tests/private_capture.json"):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(sentinel)
            destination = Path(directory) / "source.zip"
            count, checksum = export(destination, source)
            self.assertEqual(checksum, hashlib.sha256(destination.read_bytes()).hexdigest())
            with zipfile.ZipFile(destination) as archive:
                prefix = "beoremote-gateway/"
                names = {name.removeprefix(prefix) for name in archive.namelist()}
                self.assertEqual(names, set(public_files()) | {"SOURCE_MANIFEST.json"})
                self.assertEqual(count, len(names) - 1)
                recorded = json.loads(archive.read(prefix + "SOURCE_MANIFEST.json"))
                for name, digest in recorded.items():
                    self.assertEqual(hashlib.sha256(archive.read(prefix + name)).hexdigest(), digest)
                    self.assertNotIn(sentinel.encode(), archive.read(prefix + name))
            second = Path(directory) / "second.zip"
            export(second, source)
            self.assertEqual(destination.read_bytes(), second.read_bytes())
            with self.assertRaises(ValueError):
                export(destination, source)

    def test_missing_or_symlinked_public_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            with self.assertRaises(ValueError):
                public_files(source)
            for name in public_files():
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, path)
            target = source / "README.md"
            target.unlink()
            target.symlink_to(ROOT / "README.md")
            with self.assertRaises(ValueError):
                public_files(source)

    def test_privacy_patterns_reject_private_values_without_printing_them(self):
        for private in ("192." + "168.12.34", "10." + "42.0.1", "172." + "20.0.3",
                        "/" + "Users/person/secret", "ghp_" + "a" * 30,
                        "7980." + "9999999.99999999@products.bang-olufsen.com"):
            self.assertTrue(privacy_issues("example.txt", private))
        for public in ("192.0.2.10", "127.0.0.1", "7980.1234567.12345678@products.bang-olufsen.com"):
            self.assertEqual(privacy_issues("example.txt", public), [])
        self.assertTrue(manifest())

    def test_relative_documentation_links_resolve_in_public_source(self):
        names = set(public_files())
        for name in names:
            if not name.endswith(".md"):
                continue
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", (ROOT / name).read_text()):
                if link.startswith(("https://", "http://", "#")):
                    continue
                target = (ROOT / name).parent / link.split("#", 1)[0]
                relative = target.resolve().relative_to(ROOT).as_posix()
                self.assertIn(relative, names, (name, link))


class BlueprintTests(unittest.TestCase):
    def setUp(self):
        self.blueprint = load_blueprint()
        environment = Environment(undefined=StrictUndefined)
        # Home Assistant float(default) accepts invalid values and returns default.
        def ha_float(value, default=0):
            try:
                return float(value)
            except (ValueError, TypeError):
                return default
        environment.filters["float"] = ha_float
        self.template = environment.from_string(self.blueprint["actions"][0]["value_template"])

    def render(self, data, now=1000):
        trigger = {"platform": "event", "event": {"data": data}}
        return self.template.render(trigger=trigger,
                                    now=lambda: datetime.datetime.fromtimestamp(now, datetime.timezone.utc)) == "True"

    def test_freshness_at_action_time_rejects_stale_future_and_invalid_events(self):
        self.assertTrue(self.render({"received_at": 999.5}))
        self.assertFalse(self.render({"received_at": 999.5}, now=1002))
        for value in (998, 1001, 0, None, "invalid", "nan", "inf", "-inf"):
            with self.subTest(value=value):
                self.assertFalse(self.render({"received_at": value}))
        self.assertFalse(self.render({}))
        self.assertEqual(self.template.render(), "False")
        self.assertEqual(self.template.render(trigger={"platform": "manual"}), "False")

    def test_blueprint_filters_full_identity_and_only_observed_press_payloads(self):
        event = self.blueprint["triggers"][0]["event_data"]
        self.assertEqual(event, {"peer_jid": {"input": "tv_jid"}, "originator": "0",
                                 "data_hex": {"input": "light_payload"}})
        fixtures = json.loads((ROOT / "tests/fixtures/verified_light_telegrams.json").read_text())
        observed = {sample["data_hex"] for sample in fixtures["samples"] if sample["phase"] == "press"}
        choices = self.blueprint["blueprint"]["input"]["light_payload"]["selector"]["select"]["options"]
        self.assertEqual({choice["value"] for choice in choices}, observed)
        self.assertIs(self.blueprint["blueprint"]["input"]["dry_run"]["default"], True)
        self.assertEqual(self.blueprint["actions"][1]["then"][0].keys(), {"stop"})
        self.assertEqual(self.blueprint["actions"][2], {"sequence": {"input": "button_action"}})


class DiscoveryHelperTests(unittest.TestCase):
    def test_txt_bytes_and_missing_fields_are_displayed_without_control_commands(self):
        info = Mock(name="BeoCore", properties={b"jid": b"synthetic@example.test", b"name": b"TV"}, port=5222)
        info.name = "TV._beocore._tcp.local."
        info.parsed_addresses.return_value = ["192.0.2.10"]
        record = describe(info)
        self.assertEqual(record["jid"], "synthetic@example.test")
        self.assertEqual(record["addresses"], ["192.0.2.10"])
        zeroconf = Mock()
        zeroconf.get_service_info.return_value = info
        listener = Listener()
        listener.add_service(zeroconf, "_beocore._tcp.local.", info.name)
        self.assertEqual(listener.records[info.name], record)
        listener.remove_service(zeroconf, "_beocore._tcp.local.", info.name)
        self.assertEqual(listener.records, {})
        zeroconf.register_service.assert_not_called()
