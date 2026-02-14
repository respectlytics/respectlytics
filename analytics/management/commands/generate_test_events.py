"""
Management command to generate realistic test events with session-based analytics.

Session-Based Analytics Model (v2.0.0):
- Each session is independent (no cross-session tracking)
- Session IDs are random UUIDs (simulating in-memory, rotated every 2 hours)
- No user_id field - privacy by design
- Realistic conversion funnels within individual sessions
"""
import random
import uuid
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from analytics.models import App, Event


class Command(BaseCommand):
    help = 'Generate realistic test events with session-based analytics (no user tracking)'

    def add_arguments(self, parser):
        parser.add_argument('app_key', type=str, help='The app UUID/API key')
        parser.add_argument('--count', type=int, default=10000, help='Number of events to generate')
        parser.add_argument('--start-date', type=str, default=None, help='Start date (YYYY-MM-DD), default: 30 days ago')
        parser.add_argument('--end-date', type=str, default=None, help='End date (YYYY-MM-DD), default: today')
        parser.add_argument('--sessions', type=int, default=None, help='Number of unique sessions (default: count/8)')
        parser.add_argument('--clear', action='store_true', help='Clear existing events for this app before generating')
        parser.add_argument('--seed', type=int, default=None, help='Random seed for reproducible generation')

    def handle(self, *args, **options):
        app_key = options['app_key']
        count = options['count']
        
        # Default date range: last 30 days
        if options['end_date']:
            end_date = datetime.strptime(options['end_date'], '%Y-%m-%d')
        else:
            end_date = datetime.now()
        
        if options['start_date']:
            start_date = datetime.strptime(options['start_date'], '%Y-%m-%d')
        else:
            start_date = end_date - timedelta(days=30)
        
        num_sessions = options['sessions'] or count // 8  # ~8 events per session on average
        clear_existing = options['clear']
        seed = options['seed']

        # Set random seed for reproducibility if provided
        if seed is not None:
            random.seed(seed)
            self.stdout.write(f'Using random seed: {seed}')

        try:
            app = App.objects.get(id=app_key)
        except App.DoesNotExist:
            self.stderr.write(self.style.ERROR(f'App with key {app_key} not found'))
            return

        # Clear existing events if requested
        if clear_existing:
            deleted_count = Event.objects.filter(app=app).delete()[0]
            self.stdout.write(self.style.WARNING(f'Cleared {deleted_count} existing events for app: {app.name}'))

        self.stdout.write(self.style.SUCCESS(f'Generating {count} events for app: {app.name}'))
        self.stdout.write(f'  Date range: {start_date.date()} to {end_date.date()}')
        self.stdout.write(f'  Sessions: {num_sessions}')
        self.stdout.write(f'  Analytics model: Session-based (no user tracking)')

        # Geographic data with weighted regions
        COUNTRIES = {
            'US': [('California', 20), ('New York', 15), ('Texas', 12), ('Florida', 10), 
                   ('Illinois', 8), ('Washington', 7), ('Massachusetts', 6), ('Other', 22)],
            'GB': [('England', 70), ('Scotland', 15), ('Wales', 10), ('Northern Ireland', 5)],
            'DE': [('Bavaria', 25), ('North Rhine-Westphalia', 20), ('Baden-Württemberg', 18),
                   ('Berlin', 12), ('Other', 25)],
            'CA': [('Ontario', 40), ('Quebec', 25), ('British Columbia', 18), ('Alberta', 12), ('Other', 5)],
            'AU': [('New South Wales', 35), ('Victoria', 28), ('Queensland', 20), ('Other', 17)],
            'FR': [('Île-de-France', 30), ('Auvergne-Rhône-Alpes', 15), ('Other', 55)],
            'IN': [('Maharashtra', 20), ('Karnataka', 18), ('Tamil Nadu', 15), ('Delhi', 12), ('Other', 35)],
            'JP': [('Tokyo', 30), ('Osaka', 15), ('Kanagawa', 10), ('Other', 45)],
            'BR': [('São Paulo', 35), ('Rio de Janeiro', 15), ('Other', 50)],
            'KR': [('Seoul', 45), ('Busan', 15), ('Other', 40)],
        }

        COUNTRY_WEIGHTS = {
            'US': 35, 'GB': 12, 'DE': 10, 'CA': 8, 'AU': 6,
            'FR': 6, 'IN': 8, 'JP': 5, 'BR': 5, 'KR': 5
        }

        # Session journey patterns with realistic conversion funnels
        # Each session is independent - no cross-session tracking
        JOURNEY_PATTERNS = [
            # Casual browsers (50%) - short sessions, no conversion
            ['app_open', 'screen_view', 'scroll', 'screen_view', 'app_backgrounded'],
            ['app_open', 'screen_view', 'button_click', 'screen_view', 'app_backgrounded'],
            ['app_open', 'screen_view', 'search', 'screen_view', 'scroll', 'app_backgrounded'],
            ['app_open', 'screen_view', 'scroll', 'app_backgrounded'],
            
            # Engaged browsers (25%) - longer sessions, product views
            ['app_open', 'screen_view', 'search', 'view_product', 'scroll', 'view_product', 'app_backgrounded'],
            ['app_open', 'screen_view', 'button_click', 'view_product', 'add_to_cart', 'app_backgrounded'],
            ['app_open', 'screen_view', 'search', 'view_product', 'share', 'app_backgrounded'],
            ['app_open', 'screen_view', 'view_product', 'scroll', 'view_product', 'scroll', 'app_backgrounded'],
            
            # Cart abandoners (15%) - add to cart but don't purchase
            ['app_open', 'screen_view', 'view_product', 'add_to_cart', 'screen_view', 'app_backgrounded'],
            ['app_open', 'search', 'view_product', 'add_to_cart', 'view_product', 'add_to_cart', 'app_backgrounded'],
            ['app_open', 'view_product', 'add_to_cart', 'checkout_started', 'app_backgrounded'],
            
            # Checkout abandoners (5%) - start checkout but don't complete
            ['app_open', 'view_product', 'add_to_cart', 'checkout_started', 'apply_coupon', 'app_backgrounded'],
            
            # Purchasers (5%) - complete the purchase funnel
            ['app_open', 'search', 'view_product', 'add_to_cart', 'checkout_started', 'purchase', 'app_backgrounded'],
            ['app_open', 'screen_view', 'view_product', 'add_to_cart', 'checkout_started', 'apply_coupon', 'purchase', 'rate_app', 'app_backgrounded'],
            ['app_open', 'view_product', 'add_to_cart', 'add_to_cart', 'checkout_started', 'purchase', 'app_backgrounded'],
        ]

        JOURNEY_WEIGHTS = [
            12, 14, 13, 11,  # Casual browsers (50%)
            8, 7, 6, 4,      # Engaged browsers (25%)
            7, 5, 3,         # Cart abandoners (15%)
            3,               # Checkout abandoners (5%)
            3, 2, 2          # Purchasers (5%)
        ]

        PLATFORMS = [('ios', 55), ('android', 45)]
        APP_VERSIONS = [('2.5.0', 35), ('2.4.3', 30), ('2.4.2', 20), ('2.4.0', 15)]
        LOCALES = [('en-US', 40), ('en-GB', 12), ('de-DE', 10), ('fr-FR', 8), ('ja-JP', 6),
                   ('pt-BR', 6), ('es-ES', 5), ('ko-KR', 5), ('hi-IN', 4), ('zh-CN', 4)]

        def weighted_choice(choices):
            """Select from a list of (item, weight) tuples."""
            total = sum(w for _, w in choices)
            r = random.uniform(0, total)
            upto = 0
            for item, weight in choices:
                upto += weight
                if r <= upto:
                    return item
            return choices[-1][0]

        class Session:
            """
            Represents a single session (independent, no user tracking).
            
            In production, session IDs are:
            - Generated in-memory by the SDK
            - Random UUID format (32 hex chars)
            - Rotated every 2 hours or on app restart
            - Never persisted to device storage
            
            SCHEMA REDUCTION (ROA - Return of Avoidance):
            Only stored fields are generated:
            - event_name, timestamp, platform, country, session_id
            
            Deprecated fields (not generated):
            - region, device_type, os_version, app_version, locale, screen
            """
            def __init__(self, session_index, start_date, end_date):
                # Generate random session ID (simulating SDK behavior)
                self.session_id = uuid.uuid4().hex  # 32 lowercase hex chars
                
                # Random session characteristics (STORED FIELDS ONLY)
                self.country = weighted_choice(list(COUNTRY_WEIGHTS.items()))
                self.platform = weighted_choice(PLATFORMS)
                
                # Random session time within date range
                days_range = max(1, (end_date - start_date).days)
                session_day = start_date + timedelta(days=random.randint(0, days_range - 1))
                
                # Hour distribution: more activity in evening/afternoon
                hour_weights = [(h, 5 if h < 6 else 8 if h < 9 else 15 if h < 12 else 20 if h < 18 else 30 if h < 22 else 12) 
                                for h in range(24)]
                hour = weighted_choice(hour_weights)
                minute = random.randint(0, 59)
                second = random.randint(0, 59)
                
                self.start_time = timezone.make_aware(
                    datetime(session_day.year, session_day.month, session_day.day, hour, minute, second)
                )
                
                # Select journey pattern
                self.journey = weighted_choice(list(zip(JOURNEY_PATTERNS, JOURNEY_WEIGHTS)))

        def generate_session_events(session, app, end_date):
            """Generate events for a single session."""
            events = []
            event_time = session.start_time
            
            for event_name in session.journey:
                # Variable time between events based on event type
                if event_name in ['app_open']:
                    delay = random.randint(0, 2)  # Immediate
                elif event_name in ['scroll', 'button_click']:
                    delay = random.randint(3, 15)  # Fast interactions
                elif event_name in ['search', 'screen_view']:
                    delay = random.randint(5, 30)  # Quick browsing
                elif event_name in ['view_product']:
                    delay = random.randint(15, 90)  # Viewing product details
                elif event_name in ['add_to_cart', 'apply_coupon']:
                    delay = random.randint(5, 20)  # Quick decision
                elif event_name in ['checkout_started']:
                    delay = random.randint(10, 45)  # Review cart
                elif event_name == 'purchase':
                    delay = random.randint(30, 120)  # Payment processing
                elif event_name in ['rate_app', 'share']:
                    delay = random.randint(5, 30)
                elif event_name == 'app_backgrounded':
                    delay = random.randint(2, 10)
                else:
                    delay = random.randint(5, 60)
                
                event_time += timedelta(seconds=delay)
                
                if event_time > timezone.make_aware(end_date):
                    break
                
                # SCHEMA REDUCTION (ROA): Only stored fields are included
                # Deprecated fields removed: region, device_type, os_version, app_version, locale, screen
                event_data = {
                    'app': app,
                    'event_name': event_name,
                    'timestamp': event_time,
                    'country': session.country,
                    'session_id': session.session_id,
                    'platform': session.platform,
                }
                
                events.append(event_data)
            
            return events

        # Generate sessions
        self.stdout.write('\n[1/3] Creating sessions...')
        sessions = []
        for i in range(num_sessions):
            sessions.append(Session(i + 1, start_date, end_date))

        # Generate events from sessions
        self.stdout.write('[2/3] Generating event sequences...')
        all_events = []
        
        for session in sessions:
            session_events = generate_session_events(session, app, end_date)
            all_events.extend(session_events)
            
            if len(all_events) >= count:
                all_events = all_events[:count]
                break

        # If we need more events, generate additional sessions
        while len(all_events) < count:
            session = Session(len(sessions) + 1, start_date, end_date)
            sessions.append(session)
            session_events = generate_session_events(session, app, end_date)
            for event in session_events:
                all_events.append(event)
                if len(all_events) >= count:
                    break

        self.stdout.write(f'  Generated {len(all_events)} events from {len(sessions)} sessions')

        # Insert events
        self.stdout.write('[3/3] Inserting events into database...')
        events_to_create = []
        batch_size = 1000
        
        for i, event_data in enumerate(all_events):
            events_to_create.append(Event(**event_data))
            
            if len(events_to_create) >= batch_size:
                Event.objects.bulk_create(events_to_create)
                self.stdout.write(f'  Inserted {i + 1}/{len(all_events)} events...')
                events_to_create = []
        
        if events_to_create:
            Event.objects.bulk_create(events_to_create)

        # Summary statistics (session-based only)
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.SUCCESS('✓ Event generation complete!'))
        self.stdout.write('=' * 60)
        
        final_count = Event.objects.filter(app_id=app_key).count()
        unique_sessions = Event.objects.filter(app_id=app_key).values('session_id').distinct().count()
        
        self.stdout.write(f'\nSummary:')
        self.stdout.write(f'  Total events: {final_count:,}')
        self.stdout.write(f'  Unique sessions: {unique_sessions:,}')
        if unique_sessions > 0:
            self.stdout.write(f'  Avg events/session: {final_count / unique_sessions:.1f}')
        
        # Event type breakdown
        from django.db.models import Count
        self.stdout.write(f'\nTop event types:')
        top_events = Event.objects.filter(app_id=app_key).values('event_name').annotate(
            event_count=Count('id')).order_by('-event_count')[:10]
        for e in top_events:
            pct = (e['event_count'] / final_count) * 100
            self.stdout.write(f'  {e["event_name"]}: {e["event_count"]:,} ({pct:.1f}%)')
        
        # Country breakdown
        self.stdout.write(f'\nTop countries:')
        top_countries = Event.objects.filter(app_id=app_key).values('country').annotate(
            country_count=Count('id')).order_by('-country_count')[:5]
        for c in top_countries:
            pct = (c['country_count'] / final_count) * 100
            self.stdout.write(f'  {c["country"]}: {c["country_count"]:,} ({pct:.1f}%)')
        
        # Platform breakdown
        self.stdout.write(f'\nPlatforms:')
        platforms = Event.objects.filter(app_id=app_key).values('platform').annotate(
            platform_count=Count('id')).order_by('-platform_count')
        for p in platforms:
            pct = (p['platform_count'] / final_count) * 100
            self.stdout.write(f'  {p["platform"]}: {p["platform_count"]:,} ({pct:.1f}%)')
        
        # Conversion funnel (session-based)
        self.stdout.write(f'\nConversion funnel (within sessions):')
        funnel_events = ['app_open', 'view_product', 'add_to_cart', 'checkout_started', 'purchase']
        prev_count = final_count
        for event in funnel_events:
            event_count = Event.objects.filter(app_id=app_key, event_name=event).count()
            if prev_count > 0:
                pct = (event_count / prev_count) * 100
                self.stdout.write(f'  {event}: {event_count:,} ({pct:.1f}% of previous)')
            prev_count = event_count if event_count > 0 else prev_count
        
        # Sessions with conversions
        sessions_with_purchase = Event.objects.filter(
            app_id=app_key, event_name='purchase'
        ).values('session_id').distinct().count()
        if unique_sessions > 0:
            conversion_rate = (sessions_with_purchase / unique_sessions) * 100
            self.stdout.write(f'\nSession Conversion Rate:')
            self.stdout.write(f'  Sessions with purchase: {sessions_with_purchase:,} ({conversion_rate:.1f}%)')
        
        # Sample output for verification
        self.stdout.write(f'\nSample events (first 5):')
        sample_events = Event.objects.filter(app_id=app_key).order_by('timestamp')[:5]
        for e in sample_events:
            self.stdout.write(f'  session={e.session_id[:16]}... event={e.event_name} @ {e.timestamp.strftime("%Y-%m-%d %H:%M")}')
        
        self.stdout.write(f'\n✅ Session-based analytics: No user tracking, transparent and defensible by design')
