"""
Django management command to download or update the GeoIP database.

Usage:
    python manage.py update_geoip

With MAXMIND_ACCOUNT_ID and MAXMIND_LICENSE_KEY set, it downloads MaxMind's GeoLite2 City.
Without them, it downloads DB-IP's free IP to Country Lite, which needs no account and is
licensed CC BY 4.0 (the stats page carries the credit it asks for, analytics/geolocation.py).
`--source dbip` takes DB-IP's whatever is set: respectlytics.com does, at every container start
(docker/entrypoint.sh) and in the daily jobs, which keep it at most 30 days old.

Get MaxMind credentials by:
1. Sign up at https://www.maxmind.com/en/geolite2/signup
2. Generate a license key at https://www.maxmind.com/en/accounts/current/license-key
"""

import gzip
import os
import tarfile
import tempfile
from datetime import date, datetime
from pathlib import Path

import geoip2.database
import requests
from django.core.management.base import BaseCommand, CommandError

from analytics.geolocation import DBIP_FILE, MAXMIND_FILE

# MaxMind download permalink for GeoLite2 City
MAXMIND_URL = "https://download.maxmind.com/geoip/databases/GeoLite2-City/download?suffix=tar.gz"
# DB-IP publishes each month's file under its month; early in a month it may not be out yet.
DBIP_URL = "https://download.db-ip.com/free/dbip-country-lite-{month}.mmdb.gz"
# What a download may weigh, packed and unpacked (GeoLite2 City is about 60 MB, DB-IP's
# Country Lite about 8): a server that sends more is not sending the database.
MAX_DOWNLOAD = 200 * 1024 * 1024
MAX_DATABASE = 400 * 1024 * 1024
FRESH_DAYS = 30


def months_to_try(today=None):
    """This month's DB-IP file, then last month's."""
    today = today or date.today()
    last = date(today.year - (today.month == 1), (today.month - 2) % 12 + 1, 1)
    return [today.strftime("%Y-%m"), last.strftime("%Y-%m")]


def check_database(path):
    """Refuse a file that is not a GeoIP database able to answer a country lookup."""
    try:
        with geoip2.database.Reader(str(path)) as reader:
            kind = reader.metadata().database_type
    except Exception as e:
        raise CommandError(f"The downloaded file is not a GeoIP database: {e}") from e
    if "City" not in kind and "Country" not in kind:
        raise CommandError(f"The downloaded database holds no countries ({kind}).")


def save(response, target, limit):
    """Write a streamed response to `target`, refusing more than `limit` bytes."""
    written = 0
    with open(target, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            written += len(chunk)
            if written > limit:
                raise CommandError("The download is larger than a GeoIP database can be.")
            f.write(chunk)


def unpack(source, target, limit):
    """Copy at most `limit` bytes from the open file `source` to `target`."""
    written = 0
    with open(target, "wb") as out:
        while chunk := source.read(65536):
            written += len(chunk)
            if written > limit:
                raise CommandError("The database is larger than a GeoIP database can be.")
            out.write(chunk)


class Command(BaseCommand):
    help = "Download or update the GeoIP database (MaxMind with credentials, DB-IP without)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--check-only",
            action="store_true",
            help="Only check if update is needed, do not download",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force download even if database exists",
        )
        parser.add_argument(
            "--source",
            choices=["auto", "dbip", "maxmind"],
            default="auto",
            help="auto: MaxMind with its credentials, DB-IP without (the default)",
        )

    def handle(self, *args, **options):
        account_id = os.environ.get("MAXMIND_ACCOUNT_ID")
        license_key = os.environ.get("MAXMIND_LICENSE_KEY")
        source = options.get("source") or "auto"
        if source == "maxmind" and not (account_id and license_key):
            raise CommandError("--source maxmind needs MAXMIND_ACCOUNT_ID and MAXMIND_LICENSE_KEY.")
        maxmind = source == "maxmind" or (source == "auto" and bool(account_id and license_key))
        db_path = MAXMIND_FILE if maxmind else DBIP_FILE
        db_path.parent.mkdir(exist_ok=True)

        # Runs at every container start, so a recent file is kept without asking.
        if db_path.exists() and not options["force"]:
            age_days = (datetime.now().timestamp() - db_path.stat().st_mtime) / 86400
            if age_days < FRESH_DAYS:
                self.stdout.write(
                    f"{db_path.name} is {age_days:.0f} days old, recent enough. "
                    "Use --force to update anyway."
                )
                return

        if options["check_only"]:
            self.stdout.write("Update is needed.")
            return

        with tempfile.TemporaryDirectory(dir=db_path.parent) as work:
            work = Path(work)
            candidate = work / db_path.name
            if maxmind:
                self.download_maxmind(account_id, license_key, work, candidate)
            else:
                self.download_dbip(work, candidate)
            check_database(candidate)
            # The new file replaces the old in one step, so a lookup never meets half a file.
            os.replace(candidate, db_path)

        source = "MaxMind GeoLite2 City" if maxmind else "DB-IP IP to Country Lite"
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated the GeoIP database ({source}): {db_path}, "
                f"{db_path.stat().st_size / 1024 / 1024:.1f} MB"
            )
        )

    def download_dbip(self, work, candidate):
        packed = work / "download.mmdb.gz"
        for month in months_to_try():
            url = DBIP_URL.format(month=month)
            self.stdout.write(f"Downloading {url} ...")
            try:
                response = requests.get(url, stream=True, timeout=120)
            except requests.RequestException as e:
                raise CommandError(f"Download failed: {e}") from e
            if response.status_code == 404:
                continue
            if response.status_code != 200:
                raise CommandError(f"Download failed: HTTP {response.status_code}")
            save(response, packed, MAX_DOWNLOAD)
            try:
                with gzip.open(packed, "rb") as source:
                    unpack(source, candidate, MAX_DATABASE)
            except (OSError, EOFError) as e:
                raise CommandError(f"The download is not a gzip file: {e}") from e
            return
        raise CommandError("DB-IP has no database for this month or the last.")

    def download_maxmind(self, account_id, license_key, work, candidate):
        self.stdout.write("Downloading GeoLite2 City database...")
        packed = work / "GeoLite2-City.tar.gz"
        try:
            # requests follows MaxMind's redirect to its R2 presigned URL
            response = requests.get(
                MAXMIND_URL, auth=(account_id, license_key), stream=True, timeout=120
            )
        except requests.RequestException as e:
            raise CommandError(f"Download failed: {e}") from e
        if response.status_code == 401:
            raise CommandError(
                "Authentication failed! Please check your MaxMind credentials:\n"
                f"  Account ID: {account_id}\n"
                "  License Key: [hidden]\n\n"
                "Verify at: https://www.maxmind.com/en/accounts/current/license-key"
            )
        if response.status_code != 200:
            raise CommandError(f"Download failed: HTTP {response.status_code}")
        save(response, packed, MAX_DOWNLOAD)
        try:
            with tarfile.open(packed, "r:gz") as tar:
                member = next((m for m in tar.getmembers() if m.name.endswith(".mmdb")), None)
                if member is None or not member.isfile():
                    raise CommandError("Could not find .mmdb file in downloaded archive")
                # Read the one file straight out of the archive: nothing is extracted to disk.
                with tar.extractfile(member) as source:
                    unpack(source, candidate, MAX_DATABASE)
        except tarfile.TarError as e:
            raise CommandError(f"The download is not a GeoLite2 archive: {e}") from e
