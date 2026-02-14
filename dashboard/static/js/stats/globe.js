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
 * Toggle map fullscreen mode
 */
function toggleGlobeFullscreen() {
    const mapSection = document.getElementById('globeSection');
    const mapViz = document.getElementById('globeViz');
    const btn = document.getElementById('globeFullscreenBtn');
    
    if (!mapSection || !mapViz || !btn) return;
    
    if (!mapSection.classList.contains('map-fullscreen')) {
        // Enter fullscreen
        mapSection.classList.add('map-fullscreen');
        mapSection.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            z-index: 9999;
            margin: 0;
            border-radius: 0;
            padding: 12px;
            background: linear-gradient(180deg, #0a0e27 0%, #1a1f3a 100%);
        `;
        mapViz.style.height = 'calc(100vh - 24px)';
        btn.textContent = '✕';
        btn.title = 'Exit Fullscreen';
        
        // Redraw map at new size
        setTimeout(() => {
            mapInitialized = false;
            render2DMap(currentCountriesData);
        }, 50);
        
        // Add escape key listener
        document.addEventListener('keydown', handleMapEscape);
    } else {
        exitGlobeFullscreen();
    }
}

/**
 * Exit map fullscreen mode
 */
function exitGlobeFullscreen() {
    const mapSection = document.getElementById('globeSection');
    const mapViz = document.getElementById('globeViz');
    const btn = document.getElementById('globeFullscreenBtn');
    
    if (!mapSection || !mapViz || !btn) return;
    
    mapSection.classList.remove('map-fullscreen');
    mapSection.style.cssText = 'padding: 8px; position: relative;';
    mapViz.style.height = '380px';
    btn.textContent = '⛶';
    btn.title = 'Toggle Fullscreen';
    
    // Redraw map at normal size
    setTimeout(() => {
        mapInitialized = false;
        render2DMap(currentCountriesData);
    }, 50);
    
    document.removeEventListener('keydown', handleMapEscape);
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
 * Get flag emoji from 2-letter country code
 */
function getFlagEmoji(countryCode) {
    if (!countryCode || countryCode.length !== 2) return '🌍';
    const codePoints = countryCode
        .toUpperCase()
        .split('')
        .map(char => 127397 + char.charCodeAt(0));
    return String.fromCodePoint(...codePoints);
}

/**
 * Get conversion rate color (green = good, yellow = ok, red = low)
 */
function getConversionRateColor(rate) {
    if (rate === 0) return '#64748b';
    if (rate >= 0.05) return '#34d399';
    if (rate >= 0.02) return '#fcd34d';
    return '#fb7185';
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
    
    const flagEmoji = getFlagEmoji(iso);
    const tooltip = document.createElement('div');
    tooltip.id = 'mapTooltip';
    tooltip.style.cssText = `
        position: fixed;
        background: #1e293b;
        border: 1px solid rgba(255, 255, 255, 0.15);
        padding: 12px 16px;
        border-radius: 10px;
        color: white;
        pointer-events: none;
        z-index: 10000;
        font-size: 14px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        min-width: 220px;
        backdrop-filter: blur(8px);
    `;
    
    if (!data || data.count === 0) {
        tooltip.innerHTML = `
            <div style="font-weight: 600; margin-bottom: 4px;">${flagEmoji} ${name}</div>
            <div style="color: #64748b; font-size: 13px;">No data</div>
        `;
    } else {
        const convRatePercent = data.conversion_rate.toFixed(1);
        const convRateColor = getConversionRateColor(data.conversion_rate / 100);
        
        let metricsHTML = `
            <div style="font-weight: 600; margin-bottom: 8px; font-size: 15px;">${flagEmoji} ${name}</div>
            <div style="display: flex; flex-direction: column; gap: 5px; font-size: 13px;">
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #94a3b8;">Events:</span>
                    <span style="color: #f8fafc; font-weight: 500;">${(data.count || 0).toLocaleString()}</span>
                </div>
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #94a3b8;">Sessions:</span>
                    <span style="color: #f8fafc; font-weight: 500;">${(data.sessions || 0).toLocaleString()}</span>
                </div>
        `;
        
        if (data.conversions > 0) {
            metricsHTML += `
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #94a3b8;">Conversions:</span>
                    <span style="color: #f8fafc; font-weight: 500;">${(data.conversions || 0).toLocaleString()}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 4px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.1);">
                    <span style="color: #94a3b8;">Conv. Rate:</span>
                    <span style="color: ${convRateColor}; font-weight: 600;">${convRatePercent}%</span>
                </div>
            `;
        }
        
        metricsHTML += `</div>`;
        tooltip.innerHTML = metricsHTML;
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
        
        // Color scale function - teal/cyan for data
        const getCountryColor = (data) => {
            const count = data ? data.count : 0;
            if (!count || count === 0) return '#2d4a5e'; // Muted blue-gray for no data
            const intensity = Math.min(count / maxCount, 1);
            // Teal/cyan gradient
            const r = Math.round(30 + (100 * intensity));
            const g = Math.round(160 + (90 * intensity));
            const b = Math.round(180 + (75 * intensity));
            return `rgb(${r}, ${g}, ${b})`;
        };
        
        // Create SVG with fixed dimensions for proper world map aspect ratio
        const mapWidth = 800;
        const mapHeight = 400;
        
        container.innerHTML = `
            <svg id="mapSvg" width="100%" height="100%" viewBox="0 0 ${mapWidth} ${mapHeight}" preserveAspectRatio="xMidYMid meet" style="background: linear-gradient(180deg, #0f172a 0%, #1e3a5f 50%, #0f172a 100%); border-radius: 8px;">
                <defs>
                    <radialGradient id="oceanGradient" cx="50%" cy="50%" r="70%">
                        <stop offset="0%" style="stop-color:#1e4976;stop-opacity:1" />
                        <stop offset="100%" style="stop-color:#0a1628;stop-opacity:1" />
                    </radialGradient>
                </defs>
                <rect width="100%" height="100%" fill="url(#oceanGradient)"/>
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
            path.setAttribute('stroke', '#0a1628');
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
                        cp.path.setAttribute('fill', '#ff6b6b');
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
                        cp.path.setAttribute('fill', '#ff6b6b');
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
        
        // Update last updated timestamp
        const now = new Date();
        const lastUpdatedEl = document.getElementById('globeLastUpdated');
        if (lastUpdatedEl) {
            lastUpdatedEl.textContent = `Updated: ${now.toLocaleTimeString()}`;
        }
        
        mapInitialized = true;
        
    } catch (error) {
        container.innerHTML = `
            <div style="padding: 4rem 2rem; text-align: center; color: rgba(255,255,255,0.7); background: rgba(0,0,0,0.3); border-radius: 12px;">
                <div style="font-size: 3rem; margin-bottom: 1rem;">🗺️</div>
                <div style="font-size: 1.2rem; margin-bottom: 0.5rem;">Unable to load map</div>
                <div style="font-size: 0.9rem; opacity: 0.7;">Map data could not be loaded. Please try refreshing the page.</div>
            </div>
        `;
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
