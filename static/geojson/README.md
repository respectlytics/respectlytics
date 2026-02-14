# GeoJSON Data for Map Visualization

## File: countries.geojson

**Source**: Natural Earth Vector - Admin 0 Countries (110m resolution)
**URL**: https://github.com/nvkelso/natural-earth-vector
**License**: Public Domain
**Size**: ~819KB
**Purpose**: Provides country boundary polygons for the 2D map visualization on the stats page

## What This Contains

Geographic boundary data (polygons) for all countries in GeoJSON format. This file contains:
- Country names and ISO codes
- Polygon coordinates defining country borders
- Additional metadata (population, GDP, etc.)

## Why Local?

Originally fetched from GitHub CDN on every page load, which could:
- Cause page hangs if GitHub is slow/blocked
- Be blocked by corporate firewalls
- Add unnecessary latency
- Fail if GitHub is down

Now served locally for:
- ✅ Faster loading (no external dependency)
- ✅ More reliable (no external service dependency)  
- ✅ Works offline/behind firewalls
- ✅ Better user experience

## Updating

To update the data:

```bash
curl -o static/geojson/countries.geojson \
  "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson"
```

## Note

This is **different** from `geoip_data/GeoLite2-City.mmdb`:
- **GeoLite2-City.mmdb**: IP address → Country/Region lookup (backend)
- **countries.geojson**: Country shapes for 2D map visualization (frontend)
