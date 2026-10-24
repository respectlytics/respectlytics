"""The credit the GeoIP database's licence asks for where its results are shown
(analytics/geolocation.py). The stats page shows countries, so it carries it."""

from django import template

from analytics.geolocation import credit

register = template.Library()


@register.inclusion_tag("analytics/_geoip_credit.html")
def geoip_credit():
    return {"credit": credit()}
