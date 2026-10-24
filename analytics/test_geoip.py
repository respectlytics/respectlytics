"""The GeoIP database: MaxMind's with a key, DB-IP's free one without (GitHub issue 1), and the
credit each licence asks for where the countries are shown (analytics/geolocation.py)."""

import gzip
import io
import ipaddress
import os
import tarfile
import tempfile
import time
from datetime import date
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.template import Context, Template
from django.test import SimpleTestCase

from analytics import geolocation
from analytics.management.commands import update_geoip

COMMAND = "analytics.management.commands.update_geoip"


# ---- A GeoIP database for the tests ------------------------------------------------------------
# A real database file in the MaxMind DB format both MaxMind and DB-IP publish, built here from a
# few networks, so the lookups are tested against the reader as it runs and no test needs a file
# that has to be downloaded (respectlytics.com and the community edition both download theirs).


def _control(kind, size):
    """A field's control byte (its type and size), the format's extended types and long sizes."""
    if size < 29:
        head, extra = size, b""
    elif size < 285:
        head, extra = 29, bytes([size - 29])
    else:
        head, extra = 30, (size - 285).to_bytes(2, "big")
    if kind <= 7:
        return bytes([(kind << 5) | head]) + extra
    return bytes([head, kind - 7]) + extra


def _uint(kind, value):
    payload = value.to_bytes((value.bit_length() + 7) // 8, "big") if value else b""
    return _control(kind, len(payload)) + payload


def _encode(value):
    if isinstance(value, tuple):  # ("uint16" | "uint32" | "uint64", n): the metadata's integers
        return _uint({"uint16": 5, "uint32": 6, "uint64": 9}[value[0]], value[1])
    if isinstance(value, str):
        data = value.encode()
        return _control(2, len(data)) + data
    if isinstance(value, dict):
        return _control(7, len(value)) + b"".join(_encode(k) + _encode(v) for k, v in value.items())
    if isinstance(value, list):
        return _control(11, len(value)) + b"".join(_encode(v) for v in value)
    raise TypeError(value)


def write_mmdb(path, networks, database_type="Test-Country"):
    """An IPv4 database: {"89.160.20.0/24": {"country": {"iso_code": "SE"}}, ...}."""
    nodes = [[None, None]]
    for network, record in networks.items():
        net = ipaddress.ip_network(network)
        bits, length, node = int(net.network_address), net.prefixlen, 0
        for depth in range(length):
            bit = (bits >> (31 - depth)) & 1
            if depth == length - 1:
                nodes[node][bit] = ("data", record)
            else:
                if not isinstance(nodes[node][bit], int):
                    nodes.append([None, None])
                    nodes[node][bit] = len(nodes) - 1
                node = nodes[node][bit]
    data, offsets = b"", {}
    for record in networks.values():
        key = repr(record)
        if key not in offsets:
            offsets[key] = len(data)
            data += _encode(record)

    count = len(nodes)

    def value(entry):
        if entry is None:
            return count
        if isinstance(entry, int):
            return entry
        return count + 16 + offsets[repr(entry[1])]

    tree = b"".join(value(a).to_bytes(3, "big") + value(b).to_bytes(3, "big") for a, b in nodes)
    metadata = {
        "node_count": ("uint32", count),
        "record_size": ("uint16", 24),
        "ip_version": ("uint16", 4),
        "database_type": database_type,
        "languages": ["en"],
        "binary_format_major_version": ("uint16", 2),
        "binary_format_minor_version": ("uint16", 0),
        "build_epoch": ("uint64", 1790000000),
        "description": {"en": "Respectlytics test database"},
    }
    Path(path).write_bytes(tree + bytes(16) + data + b"\xab\xcd\xefMaxMind.com" + _encode(metadata))
    return Path(path)


def country(code, region=None):
    record = {"country": {"iso_code": code, "names": {"en": code}}}
    if region:
        record["subdivisions"] = [{"names": {"en": region}}]
    return record


class Response:
    def __init__(self, status, body=b""):
        self.status_code = status
        self.body = body

    def iter_content(self, chunk_size):
        for i in range(0, len(self.body), chunk_size):
            yield self.body[i : i + chunk_size]


class Folder(SimpleTestCase):
    """Each test gets its own geoip_data folder."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)
        self.maxmind = self.dir / "GeoLite2-City.mmdb"
        self.dbip = self.dir / "dbip-country-lite.mmdb"
        for target in (geolocation, update_geoip):
            for name, path in (("MAXMIND_FILE", self.maxmind), ("DBIP_FILE", self.dbip)):
                patcher = mock.patch.object(target, name, path)
                patcher.start()
                self.addCleanup(patcher.stop)


class DatabaseInUseTests(Folder):
    def test_maxmind_first_then_dbip_then_none(self):
        self.assertIsNone(geolocation.database_path())
        self.assertIsNone(geolocation.credit())
        self.dbip.write_bytes(b"x")
        self.assertEqual(geolocation.database_path(), self.dbip)
        self.maxmind.write_bytes(b"x")
        self.assertEqual(geolocation.database_path(), self.maxmind)

    def render(self):
        return Template("{% load geoip %}{% geoip_credit %}").render(Context())

    def test_the_credit_names_the_database_in_use(self):
        self.assertEqual(self.render().strip(), "")
        self.dbip.write_bytes(b"x")
        html = self.render()
        self.assertIn('href="https://db-ip.com"', html)
        self.assertIn("IP Geolocation by DB-IP", html)
        self.maxmind.write_bytes(b"x")
        html = self.render()
        self.assertIn("This product includes GeoLite Data created by MaxMind", html)
        self.assertIn('href="https://www.maxmind.com"', html)
        self.assertNotIn("db-ip.com", html)

    def test_a_country_database_is_asked_for_a_country(self):
        """DB-IP's Country Lite answers country(); asking it for city() is a TypeError."""
        write_mmdb(self.dbip, {"89.160.20.0/24": country("SE")}, "DBIP-Country-Lite")
        self.assertEqual(geolocation.get_location_from_ip("89.160.20.112"), ("SE", None))
        self.assertEqual(geolocation.get_location_from_ip("81.2.69.142"), (None, None))

    def test_a_city_database_gives_the_region_too(self):
        write_mmdb(self.maxmind, {"81.2.69.0/24": country("GB", "England")}, "GeoLite2-City")
        self.assertEqual(geolocation.get_location_from_ip("81.2.69.142"), ("GB", "England"))


@mock.patch(f"{COMMAND}.check_database")
class DownloadTests(Folder):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"MAXMIND_ACCOUNT_ID": "", "MAXMIND_LICENSE_KEY": ""})
        env.start()
        self.addCleanup(env.stop)

    def run_command(self, *args):
        call_command("update_geoip", *args, stdout=io.StringIO())

    def test_without_a_key_dbip_is_downloaded_falling_back_to_last_month(self, check):
        this, last = update_geoip.months_to_try()
        responses = [Response(404), Response(200, gzip.compress(b"the database"))]
        with mock.patch(f"{COMMAND}.requests.get", side_effect=responses) as get:
            self.run_command()
        urls = [c.args[0] for c in get.call_args_list]
        self.assertEqual(
            urls,
            [
                f"https://download.db-ip.com/free/dbip-country-lite-{this}.mmdb.gz",
                f"https://download.db-ip.com/free/dbip-country-lite-{last}.mmdb.gz",
            ],
        )
        self.assertNotIn("auth", get.call_args.kwargs)
        self.assertEqual(self.dbip.read_bytes(), b"the database")
        self.assertFalse(self.maxmind.exists())
        check.assert_called_once()

    def test_with_a_key_maxmind_is_downloaded(self, check):
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w:gz") as tar:
            info = tarfile.TarInfo("GeoLite2-City_20261020/GeoLite2-City.mmdb")
            info.size = len(b"maxmind data")
            tar.addfile(info, io.BytesIO(b"maxmind data"))
        keys = {"MAXMIND_ACCOUNT_ID": "1", "MAXMIND_LICENSE_KEY": "k"}
        with (
            mock.patch.dict(os.environ, keys),
            mock.patch(
                f"{COMMAND}.requests.get", return_value=Response(200, archive.getvalue())
            ) as get,
        ):
            self.run_command()
        self.assertEqual(get.call_args.args[0], update_geoip.MAXMIND_URL)
        self.assertEqual(get.call_args.kwargs["auth"], ("1", "k"))
        self.assertEqual(self.maxmind.read_bytes(), b"maxmind data")
        self.assertEqual(list(self.dir.iterdir()), [self.maxmind])

    def test_a_recent_file_is_kept_without_asking(self, check):
        self.dbip.write_bytes(b"current")
        with mock.patch(f"{COMMAND}.requests.get") as get:
            self.run_command()
        get.assert_not_called()

    def test_an_old_file_is_replaced(self, check):
        self.dbip.write_bytes(b"old")
        old = time.time() - 31 * 86400
        os.utime(self.dbip, (old, old))
        with mock.patch(
            f"{COMMAND}.requests.get", return_value=Response(200, gzip.compress(b"new"))
        ):
            self.run_command()
        self.assertEqual(self.dbip.read_bytes(), b"new")

    def test_a_bad_download_leaves_the_old_file(self, check):
        self.dbip.write_bytes(b"old")
        with (
            mock.patch(f"{COMMAND}.requests.get", return_value=Response(200, b"not gzip")),
            self.assertRaises(CommandError),
        ):
            self.run_command("--force")
        self.assertEqual(self.dbip.read_bytes(), b"old")
        self.assertEqual(list(self.dir.iterdir()), [self.dbip])

    def test_an_oversized_download_is_refused(self, check):
        with (
            mock.patch(f"{COMMAND}.MAX_DOWNLOAD", 10),
            mock.patch(f"{COMMAND}.requests.get", return_value=Response(200, b"x" * 100)),
            self.assertRaises(CommandError),
        ):
            self.run_command()
        self.assertFalse(self.dbip.exists())

    def test_no_file_this_month_or_last(self, check):
        with (
            mock.patch(f"{COMMAND}.requests.get", return_value=Response(404)),
            self.assertRaises(CommandError),
        ):
            self.run_command()


class CheckTests(SimpleTestCase):
    def test_january_falls_back_to_december(self):
        self.assertEqual(update_geoip.months_to_try(date(2027, 1, 2)), ["2027-01", "2026-12"])

    def test_a_file_that_is_no_database_is_refused(self):
        with tempfile.NamedTemporaryFile(suffix=".mmdb") as f:
            f.write(b"this is no database")
            f.flush()
            with self.assertRaises(CommandError):
                update_geoip.check_database(f.name)

    def test_a_country_or_city_database_passes_and_any_other_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            for kind in ("DBIP-Country-Lite", "GeoLite2-City"):
                update_geoip.check_database(write_mmdb(Path(folder) / kind, {}, kind))
            with self.assertRaises(CommandError):
                update_geoip.check_database(write_mmdb(Path(folder) / "asn", {}, "GeoLite2-ASN"))

    def test_the_source_can_be_named(self):
        """respectlytics.com names DB-IP's, whatever credentials the environment holds."""
        keys = {"MAXMIND_ACCOUNT_ID": "1", "MAXMIND_LICENSE_KEY": "k"}
        with (
            mock.patch.dict(os.environ, keys),
            mock.patch(f"{COMMAND}.check_database"),
            tempfile.TemporaryDirectory() as folder,
            mock.patch.object(update_geoip, "DBIP_FILE", Path(folder) / "dbip.mmdb"),
            mock.patch(
                f"{COMMAND}.requests.get", return_value=Response(200, gzip.compress(b"db"))
            ) as get,
        ):
            call_command("update_geoip", source="dbip", stdout=io.StringIO())
            self.assertIn("db-ip.com", get.call_args.args[0])
        with mock.patch.dict(os.environ, {"MAXMIND_ACCOUNT_ID": "", "MAXMIND_LICENSE_KEY": ""}):
            with self.assertRaises(CommandError):
                call_command("update_geoip", source="maxmind", stdout=io.StringIO())
