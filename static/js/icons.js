/**
 * icon(name, size): one of the product's icons as SVG markup, for scripts that build HTML.
 * Read from the <template id="icon-NAME"> elements partials/icon_templates.html puts on the page,
 * so a script draws exactly what templates/partials/icon.html draws; `size` replaces its
 * default h-5 w-5. An unknown name gives an empty string, never a placeholder glyph.
 */
(function () {
    window.icon = function (name, size) {
        const template = document.getElementById('icon-' + name);
        if (!template) return '';
        const svg = template.innerHTML.trim();
        return size ? svg.replace(/class="[^"]*"/, 'class="' + size + '"') : svg;
    };
})();
