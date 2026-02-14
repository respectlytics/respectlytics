"""
Authenticated dashboard views — Community Edition

Stripped of billing/subscription context.
All views identical to private edition except dashboard_view().
"""
import json
from datetime import datetime

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_http_methods

from analytics.models import App, Event, DeletionLog
from analytics.security_logger import log_security_event, SecurityEvent


@login_required
def dashboard_view(request):
    """
    Main user dashboard — Community Edition.

    No billing/subscription context. Just lists the user's apps.
    """
    apps = request.user.apps.all()

    context = {
        'apps': apps,
    }

    return render(request, 'dashboard/dashboard.html', context)


@login_required
def stats_view(request, app_slug=None):
    """
    View analytics stats for a specific app.
    """
    if not app_slug:
        messages.error(request, 'Please select an app from your dashboard.')
        return redirect('dashboard:main')

    try:
        app = App.objects.get(slug=app_slug, user=request.user)
        user_apps = request.user.apps.all().order_by('name')

        context = {
            'app_key': str(app.id),
            'app': app,
            'app_name': app.name,
            'app_slug': app.slug,
            'user_apps': user_apps,
            'preferred_conversion_events': json.dumps(app.preferred_conversion_events or [])
        }
        return render(request, 'dashboard/stats.html', context)
    except App.DoesNotExist:
        messages.error(request, 'App not found or you do not have permission to access it.')
        return redirect('dashboard:main')


@login_required
def funnel_view(request, app_slug=None):
    """
    Funnel analysis visualization page.
    """
    if not app_slug:
        messages.error(request, 'Please select an app from your dashboard.')
        return redirect('dashboard:main')

    try:
        app = App.objects.get(slug=app_slug, user=request.user)
        context = {
            'app_key': str(app.id),
            'app': app,
            'app_name': app.name,
            'app_slug': app.slug
        }
        return render(request, 'dashboard/funnel.html', context)
    except App.DoesNotExist:
        messages.error(request, 'App not found or you do not have permission to access it.')
        return redirect('dashboard:main')


@login_required
@require_POST
def save_conversion_preferences(request, app_slug):
    """Save preferred conversion events for an app."""
    try:
        app = App.objects.get(slug=app_slug, user=request.user)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        conversion_events = data.get('conversion_events', [])
        if not isinstance(conversion_events, list):
            return JsonResponse({'error': 'conversion_events must be a list'}, status=400)

        cleaned_events = []
        for event in conversion_events[:50]:
            if isinstance(event, str) and len(event) <= 255:
                cleaned_events.append(event.strip())

        app.preferred_conversion_events = cleaned_events
        app.save(update_fields=['preferred_conversion_events'])

        return JsonResponse({
            'success': True,
            'conversion_events': cleaned_events
        })

    except App.DoesNotExist:
        return JsonResponse({'error': 'App not found'}, status=404)


@login_required
@require_http_methods(["PATCH"])
def update_app_name(request, app_slug):
    """Update an app's name (PATCH only)."""
    try:
        app = App.objects.get(slug=app_slug, user=request.user)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        new_name = data.get('name', '').strip()
        if not new_name:
            return JsonResponse({'error': 'App name cannot be empty'}, status=400)

        if len(new_name) > 255:
            return JsonResponse({'error': 'App name must be 255 characters or less'}, status=400)

        app.name = new_name
        app.save(update_fields=['name'])

        return JsonResponse({
            'success': True,
            'name': app.name,
            'slug': app.slug
        })

    except App.DoesNotExist:
        return JsonResponse({'error': 'App not found'}, status=404)


@login_required
@require_http_methods(["DELETE"])
def delete_app(request, app_slug):
    """Delete an app and all associated data (events, usage records)."""
    try:
        app = App.objects.get(slug=app_slug, user=request.user)

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        confirmation_name = data.get('confirmation_name', '')
        if confirmation_name != app.name:
            return JsonResponse({
                'error': 'Confirmation does not match. Type the app name exactly as shown.'
            }, status=400)

        app_name = app.name

        app.delete()

        return JsonResponse({
            'success': True,
            'message': f'App "{app_name}" deleted successfully'
        })

    except App.DoesNotExist:
        return JsonResponse({'error': 'App not found'}, status=404)


@login_required
@require_http_methods(["GET"])
def get_app_event_count(request, app_slug):
    """Get the total event count for an app."""
    try:
        app = App.objects.get(slug=app_slug, user=request.user)
        count = Event.objects.filter(app=app).count()
        return JsonResponse({'count': count})

    except App.DoesNotExist:
        return JsonResponse({'error': 'App not found'}, status=404)


# ---------------------------------------------------------------------------
# Event Data Deletion (Dashboard)
# ---------------------------------------------------------------------------

def _dashboard_build_filter(app, data):
    """Build a queryset filter dict from dashboard deletion request JSON."""
    date_from = data.get('date_from')
    date_to = data.get('date_to')

    if not date_from or not date_to:
        return None, JsonResponse(
            {'error': 'date_from and date_to are required (YYYY-MM-DD format).'},
            status=400
        )

    try:
        parsed_from = datetime.strptime(date_from, '%Y-%m-%d').date()
        parsed_to = datetime.strptime(date_to, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None, JsonResponse(
            {'error': 'Invalid date format. Use YYYY-MM-DD.'},
            status=400
        )

    if parsed_from > parsed_to:
        return None, JsonResponse(
            {'error': 'date_from must be before or equal to date_to.'},
            status=400
        )

    filters = {
        'app': app,
        'timestamp__date__gte': parsed_from,
        'timestamp__date__lte': parsed_to,
    }

    platform = data.get('platform')
    if platform:
        filters['platform'] = platform

    country = data.get('country')
    if country:
        filters['country'] = country

    event_name = data.get('event_name')
    if event_name:
        filters['event_name'] = event_name

    return filters, None


@login_required
@require_POST
def dashboard_delete_events_preview(request, app_slug):
    """Preview how many events would be deleted with the given filters."""
    try:
        app = App.objects.get(slug=app_slug, user=request.user)
    except App.DoesNotExist:
        return JsonResponse({'error': 'App not found'}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    filters, error = _dashboard_build_filter(app, data)
    if error:
        return error

    count = Event.objects.filter(**filters).count()
    return JsonResponse({'count': count})


@login_required
@require_POST
def dashboard_delete_events(request, app_slug):
    """Delete events matching the given filters."""
    try:
        app = App.objects.get(slug=app_slug, user=request.user)
    except App.DoesNotExist:
        return JsonResponse({'error': 'App not found'}, status=404)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    filters, error = _dashboard_build_filter(app, data)
    if error:
        return error

    qs = Event.objects.filter(**filters)
    count = qs.count()

    confirmation_count = data.get('confirmation_count')
    if confirmation_count is None:
        return JsonResponse({'error': 'confirmation_count is required.'}, status=400)

    try:
        confirmation_count = int(confirmation_count)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'confirmation_count must be an integer.'}, status=400)

    if confirmation_count != count:
        return JsonResponse({
            'error': f'Confirmation mismatch. Expected {count}, got {confirmation_count}. '
                     'Re-preview to get the current count.'
        }, status=400)

    deleted, _ = qs.delete()

    DeletionLog.objects.create(
        app=app,
        app_name=app.name,
        deleted_by=request.user,
        events_deleted=deleted,
        filter_date_from=datetime.strptime(data['date_from'], '%Y-%m-%d').date(),
        filter_date_to=datetime.strptime(data['date_to'], '%Y-%m-%d').date(),
        filter_platform=data.get('platform', ''),
        filter_country=data.get('country', ''),
        filter_event_name=data.get('event_name', ''),
    )

    log_security_event(
        event_type=SecurityEvent.DATA_DELETION,
        request=request,
        details={
            'app_name': app.name,
            'app_id': str(app.id),
            'events_deleted': deleted,
            'date_from': data['date_from'],
            'date_to': data['date_to'],
            'platform': data.get('platform'),
            'country': data.get('country'),
            'event_name': data.get('event_name'),
            'source': 'dashboard',
        }
    )

    return JsonResponse({'deleted': deleted})
