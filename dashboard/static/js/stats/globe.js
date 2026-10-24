/**
 * Stats Dashboard - Map Visualization Module
 * 
 * Renders a 2D SVG world map with analytics data.
 * No WebGL dependency - works on all devices.
 * 
 * Performance: Renders once, no animation loop, CSS hover only.
 */

// Namespace setup
window.StatsApp = window.StatsApp || {};

// Map state
let mapInitialized = false;
let activeTooltip = null;
let currentCountriesData = [];
let countryPaths = [];

/**
 * Toggle map fullscreen mode: the map fills the window on the page's own surface (stats.css);
 * the SVG scales with its box, so nothing is drawn again
 */
function toggleGlobeFullscreen() {
    const mapSection = document.getElementById('globeSection');
    if (!mapSection) return;
    if (mapSection.classList.contains('map-fullscreen')) {
        exitGlobeFullscreen();
        return;
    }
    mapSection.classList.add('map-fullscreen');
    document.addEventListener('keydown', handleMapEscape);
    const close = document.getElementById('globeCloseBtn');
    if (close) close.focus();
}

/**
 * Exit map fullscreen mode, giving the focus back to the button that opened it
 */
function exitGlobeFullscreen() {
    const mapSection = document.getElementById('globeSection');
    if (!mapSection || !mapSection.classList.contains('map-fullscreen')) return;
    mapSection.classList.remove('map-fullscreen');
    document.removeEventListener('keydown', handleMapEscape);
    const open = document.getElementById('globeFullscreenBtn');
    if (open) open.focus();
}

/**
 * Handle escape key for fullscreen
 */
function handleMapEscape(e) {
    if (e.key === 'Escape') {
        exitGlobeFullscreen();
    }
}

// Alias for compatibility
function handleGlobeEscape(e) {
    handleMapEscape(e);
}


/**
 * Remove any active tooltip
 */
function removeTooltip() {
    if (activeTooltip) {
        activeTooltip.remove();
        activeTooltip = null;
    }
    const existing = document.getElementById('mapTooltip');
    if (existing) existing.remove();
}

/**
 * Show tooltip for a country
 */
function showTooltip(e, name, iso, data) {
    removeTooltip();
    
    const tooltip = document.createElement('div');
    tooltip.id = 'mapTooltip';
    tooltip.className = 'fixed z-[10000] min-w-[12rem] rounded-lg border border-white/15 bg-[#0f172a] px-3.5 py-3 text-sm text-slate-200 shadow-2xl pointer-events-none';
    const esc = StatsApp.utils.escapeHtml;
    const row = (label, value) => `<div class="flex justify-between gap-6"><span class="text-slate-400">${label}</span><span class="text-slate-50">${value}</span></div>`;
    const title = `<div class="mb-1.5 font-semibold text-slate-50">${getCountryFlag(iso)} ${esc(name)}</div>`;
    if (!data || data.count === 0) {
        tooltip.innerHTML = `${title}<div class="text-slate-400">No sessions</div>`;
    } else {
        tooltip.innerHTML = title
            + row('Sessions', (data.sessions || 0).toLocaleString())
            + row('Events', (data.count || 0).toLocaleString())
            + (data.conversions > 0
                ? row('Conversions', (data.conversions || 0).toLocaleString()) + row('Conversion rate', `${data.conversion_rate.toFixed(1)}%`)
                : '');
    }

    document.body.appendChild(tooltip);
    activeTooltip = tooltip;
    
    // Position tooltip
    positionTooltip(e, tooltip);
}

/**
 * Position tooltip near cursor/touch point
 */
function positionTooltip(e, tooltip) {
    const x = e.clientX || (e.touches && e.touches[0]?.clientX) || 0;
    const y = e.clientY || (e.touches && e.touches[0]?.clientY) || 0;
    
    const tooltipRect = tooltip.getBoundingClientRect();
    const padding = 15;
    
    let left = x + padding;
    let top = y + padding;
    
    // Keep tooltip in viewport
    if (left + tooltipRect.width > window.innerWidth - padding) {
        left = x - tooltipRect.width - padding;
    }
    if (top + tooltipRect.height > window.innerHeight - padding) {
        top = y - tooltipRect.height - padding;
    }
    if (left < padding) left = padding;
    if (top < padding) top = padding;
    
    tooltip.style.left = left + 'px';
    tooltip.style.top = top + 'px';
}

/**
 * Render 2D SVG map (legacy alias)
 */
async function render2DFallbackMap(countriesData) {
    return render2DMap(countriesData);
}

/**
 * Render 2D SVG map
 */
async function render2DMap(countriesData) {
    const container = document.getElementById('globeViz');
    
    if (!container) {
        return; // Map container not found
    }
    
    // Store data for updates
    currentCountriesData = countriesData || [];
    countryPaths = [];
    
    try {
        // Fetch world countries GeoJSON from local static folder
        const response = await fetch('/static/geojson/countries.geojson');
        if (!response.ok) {
            throw new Error(`Map data not available (HTTP ${response.status})`);
        }
        
        const worldData = await response.json();
        
        // Create country code to full data map
        const countryMap = {};
        (countriesData || []).forEach(item => {
            const code = item.country.toUpperCase();
            countryMap[code] = {
                count: item.events || item.count || 0,
                sessions: item.sessions || 0,
                conversions: item.conversions || 0,
                conversion_rate: item.conversion_rate || 0
            };
        });
        
        // Find max count for color scaling
        const maxCount = Math.max(...(countriesData || []).map(c => c.count || c.events || 0), 1);
        
        // Land without sessions in a quiet slate; with them, brand tints by how many
        const getCountryColor = (data) => {
            const count = data ? data.count : 0;
            if (!count) return '#334155';
            const t = Math.sqrt(Math.min(count / maxCount, 1));
            const mix = (a, b) => Math.round(a + (b - a) * t);
            // from brand-800 (#3730a3) to brand-400 (#818cf8)
            return `rgb(${mix(55, 129)}, ${mix(48, 140)}, ${mix(163, 248)})`;
        };

        // Create SVG with fixed dimensions for proper world map aspect ratio
        const mapWidth = 800;
        const mapHeight = 400;
        
        container.innerHTML = `
            <svg id="mapSvg" width="100%" height="100%" viewBox="0 0 ${mapWidth} ${mapHeight}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Map of sessions by country">
                <g id="mapGroup"></g>
            </svg>
        `;
        
        const svg = container.querySelector('#mapSvg');
        const mapGroup = svg.querySelector('#mapGroup');
        
        // Equirectangular projection with fixed dimensions for centered world view
        const projectPoint = (lon, lat) => {
            lat = Math.max(-60, Math.min(85, lat)); // Clip Antarctica, keep most landmasses
            lon = Math.max(-180, Math.min(180, lon));
            
            // Simple equirectangular projection - maps lat/lon directly to x/y
            const x = (lon + 180) * (mapWidth / 360);
            const y = (90 - lat) * (mapHeight / 150); // 150 = 85 - (-60) + padding
            
            if (!isFinite(x) || !isFinite(y)) return null;
            return [x, y];
        };
        
        // Render country function
        const renderCountry = (coords, feature) => {
            const pathPoints = [];
            
            for (let i = 0; i < coords.length; i++) {
                const projected = projectPoint(coords[i][0], coords[i][1]);
                if (projected) {
                    pathPoints.push({ x: projected[0], y: projected[1], isFirst: i === 0 });
                }
            }
            
            if (pathPoints.length < 3) return null;
            
            const pathData = pathPoints.map((p, i) => 
                `${p.isFirst ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`
            ).join(' ') + ' Z';
            
            const iso = feature.properties.ISO_A2 || feature.properties.iso_a2;
            const data = countryMap[iso];
            const name = feature.properties.NAME || feature.properties.name || iso;
            const baseColor = getCountryColor(data);
            
            const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
            path.setAttribute('d', pathData);
            path.setAttribute('fill', baseColor);
            path.setAttribute('stroke', '#1e293b');
            path.setAttribute('stroke-width', '0.5');
            path.style.cursor = 'pointer';
            path.style.transition = 'fill 0.15s ease';
            path.dataset.iso = iso;
            path.dataset.name = name;
            path.dataset.baseColor = baseColor;
            
            return { path, iso, name, data, baseColor };
        };
        
        // Render all countries
        worldData.features.forEach(feature => {
            if (feature.properties.ISO_A2 === 'AQ') return; // Skip Antarctica
            
            if (feature.geometry.type === 'Polygon') {
                const result = renderCountry(feature.geometry.coordinates[0], feature);
                if (result) {
                    mapGroup.appendChild(result.path);
                    countryPaths.push(result);
                }
            } else if (feature.geometry.type === 'MultiPolygon') {
                feature.geometry.coordinates.forEach(polygon => {
                    const result = renderCountry(polygon[0], feature);
                    if (result) {
                        mapGroup.appendChild(result.path);
                        countryPaths.push(result);
                    }
                });
            }
        });
        
        // Add hover/touch interactions
        countryPaths.forEach(({ path, iso, name, data, baseColor }) => {
            // Mouse enter
            path.addEventListener('mouseenter', (e) => {
                // Highlight all paths for this country
                countryPaths.forEach(cp => {
                    if (cp.iso === iso) {
                        cp.path.setAttribute('fill', '#c7d2fe');
                    }
                });
                showTooltip(e, name, iso, data);
            });
            
            // Mouse move
            path.addEventListener('mousemove', (e) => {
                if (activeTooltip) {
                    positionTooltip(e, activeTooltip);
                }
            });
            
            // Mouse leave
            path.addEventListener('mouseleave', () => {
                countryPaths.forEach(cp => {
                    if (cp.iso === iso) {
                        cp.path.setAttribute('fill', cp.baseColor);
                    }
                });
                removeTooltip();
            });
            
            // Touch support for mobile
            path.addEventListener('touchstart', (e) => {
                e.preventDefault();
                countryPaths.forEach(cp => {
                    if (cp.iso === iso) {
                        cp.path.setAttribute('fill', '#c7d2fe');
                    }
                });
                showTooltip(e, name, iso, data);
            }, { passive: false });
            
            path.addEventListener('touchend', () => {
                setTimeout(() => {
                    countryPaths.forEach(cp => {
                        if (cp.iso === iso) {
                            cp.path.setAttribute('fill', cp.baseColor);
                        }
                    });
                    removeTooltip();
                }, 1500);
            });
        });
        
        mapInitialized = true;
        
    } catch (error) {
        container.innerHTML = '<p class="flex h-full items-center justify-center text-sm text-slate-400">The map could not be loaded. Reload the page to try again.</p>';
    }
}

/**
 * Update map data (re-renders the map)
 */
async function updateGlobeData(countriesData) {
    mapInitialized = false;
    await render2DMap(countriesData);
}

/**
 * Initialize the map visualization
 */
async function initializeGlobe(countriesData) {
    if (mapInitialized) {
        await updateGlobeData(countriesData);
        return;
    }
    
    await render2DMap(countriesData);
}

// Legacy zoom functions (no-op for 2D map, kept for compatibility)
function globeZoomIn() {
    console.info('Zoom not available for 2D map');
}

function globeZoomOut() {
    console.info('Zoom not available for 2D map');
}

// Legacy WebGL check (always returns false now)
function supportsWebGL() {
    return false;
}

// Make functions globally available
window.supportsWebGL = supportsWebGL;
window.render2DFallbackMap = render2DFallbackMap;
window.render2DMap = render2DMap;
window.globeZoomIn = globeZoomIn;
window.globeZoomOut = globeZoomOut;
window.toggleGlobeFullscreen = toggleGlobeFullscreen;
window.exitGlobeFullscreen = exitGlobeFullscreen;
window.handleGlobeEscape = handleGlobeEscape;
window.handleMapEscape = handleMapEscape;
window.initializeGlobe = initializeGlobe;
window.updateGlobeData = updateGlobeData;
