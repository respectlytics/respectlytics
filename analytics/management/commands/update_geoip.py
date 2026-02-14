"""
Django management command to download and update MaxMind GeoLite2 City database.

Usage:
    python manage.py update_geoip

Environment variables required:
    MAXMIND_ACCOUNT_ID: Your MaxMind account ID
    MAXMIND_LICENSE_KEY: Your MaxMind license key

Get these credentials by:
1. Sign up at https://www.maxmind.com/en/geolite2/signup
2. Generate a license key at https://www.maxmind.com/en/accounts/current/license-key
"""
import os
import shutil
import tarfile
from datetime import datetime
from pathlib import Path

import requests

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings


class Command(BaseCommand):
    help = 'Download or update the MaxMind GeoLite2 City database'

    # MaxMind download permalink for GeoLite2 City
    DOWNLOAD_URL = 'https://download.maxmind.com/geoip/databases/GeoLite2-City/download?suffix=tar.gz'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only check if update is needed, do not download',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force download even if database exists',
        )

    def handle(self, *args, **options):
        # Get credentials from environment variables
        account_id = os.environ.get('MAXMIND_ACCOUNT_ID')
        license_key = os.environ.get('MAXMIND_LICENSE_KEY')
        
        if not account_id or not license_key:
            raise CommandError(
                'MaxMind credentials not found!\n\n'
                'Please set environment variables:\n'
                '  MAXMIND_ACCOUNT_ID=your_account_id\n'
                '  MAXMIND_LICENSE_KEY=your_license_key\n\n'
                'Get credentials at: https://www.maxmind.com/en/accounts/current/license-key'
            )

        # Define paths
        base_dir = Path(settings.BASE_DIR)
        geoip_dir = base_dir / 'geoip_data'
        db_path = geoip_dir / 'GeoLite2-City.mmdb'
        
        # Create directory if it doesn't exist
        geoip_dir.mkdir(exist_ok=True)
        
        # Check if database exists and is recent
        if db_path.exists() and not options['force']:
            age_days = (datetime.now().timestamp() - db_path.stat().st_mtime) / 86400
            self.stdout.write(
                self.style.SUCCESS(
                    f'Database exists ({age_days:.1f} days old): {db_path}'
                )
            )
            
            if age_days < 30:
                self.stdout.write('Database is recent (less than 30 days old). Use --force to update anyway.')
                if options['check_only']:
                    return
                else:
                    user_input = input('Download anyway? [y/N]: ')
                    if user_input.lower() != 'y':
                        return
        
        if options['check_only']:
            self.stdout.write('Update is needed.')
            return
        
        # Download the database
        self.stdout.write('Downloading GeoLite2 City database...')
        
        try:
            # Download with requests (follows R2 presigned URL redirects)
            temp_tar = geoip_dir / 'GeoLite2-City.tar.gz'

            response = requests.get(
                self.DOWNLOAD_URL,
                auth=(account_id, license_key),
                stream=True,
                timeout=120,
            )
            response.raise_for_status()

            total_size = int(response.headers.get('Content-Length', 0))
            self.stdout.write(f'Downloading {total_size / 1024 / 1024:.1f} MB...')

            with open(temp_tar, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            self.stdout.write(self.style.SUCCESS('✓ Download complete'))
            
            # Extract the .mmdb file from the tarball
            self.stdout.write('Extracting database file...')
            
            with tarfile.open(temp_tar, 'r:gz') as tar:
                # Find the .mmdb file in the archive
                mmdb_member = None
                for member in tar.getmembers():
                    if member.name.endswith('.mmdb'):
                        mmdb_member = member
                        break
                
                if not mmdb_member:
                    raise CommandError('Could not find .mmdb file in downloaded archive')
                
                # Extract to temporary location
                tar.extract(mmdb_member, geoip_dir)
                
                # Move to final location
                extracted_path = geoip_dir / mmdb_member.name
                shutil.move(str(extracted_path), str(db_path))
                
                # Clean up extracted directory
                extracted_dir = geoip_dir / mmdb_member.name.split('/')[0]
                if extracted_dir.is_dir():
                    shutil.rmtree(extracted_dir)
            
            # Remove temporary tar file
            temp_tar.unlink()
            
            # Show success message
            db_size = db_path.stat().st_size / 1024 / 1024
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✓ Successfully updated GeoLite2 City database\n'
                    f'  Location: {db_path}\n'
                    f'  Size: {db_size:.1f} MB\n'
                    f'  Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
                )
            )
            
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                raise CommandError(
                    'Authentication failed! Please check your MaxMind credentials:\n'
                    f'  Account ID: {account_id}\n'
                    '  License Key: [hidden]\n\n'
                    'Verify at: https://www.maxmind.com/en/accounts/current/license-key'
                )
            else:
                code = e.response.status_code if e.response is not None else 'unknown'
                raise CommandError(f'Download failed: HTTP {code}')

        except Exception as e:
            raise CommandError(f'Failed to download database: {str(e)}')
