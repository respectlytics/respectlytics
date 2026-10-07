/*
 * Schibsted Grotesk for what a script draws or exports: the share images
 * drawn on a canvas, the PDFs jsPDF writes, and the print windows the
 * generators open. The page itself gets the faces from static/css/fonts.css;
 * this only waits for them, and hands jsPDF the release's own TTF files,
 * which it needs in place of WOFF2.
 *
 * Load it with the TTF addresses on the tag:
 *   <script src="{% static 'js/brand-fonts.js' %}"
 *           data-ttf-regular="{% static 'fonts/schibsted-grotesk/SchibstedGrotesk-Regular.ttf' %}"
 *           data-ttf-bold="{% static 'fonts/schibsted-grotesk/SchibstedGrotesk-Bold.ttf' %}"></script>
 *
 *   BrandFonts.family               the CSS stack for canvas text and inline styles
 *   BrandFonts.ready(['bold 56px'])  resolves once those faces are loaded (or failed)
 *   BrandFonts.pdf(doc)              registers the font with a jsPDF doc and resolves
 *                                    to the family name to pass to setFont
 *                                    ('helvetica' if the files could not be read)
 *   BrandFonts.printWhenReady(win)   prints a window once its fonts have loaded
 */
(function () {
    'use strict';

    var FAMILY = '"Schibsted Grotesk", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    var PDF_NAME = 'SchibstedGrotesk';
    var tag = document.currentScript;
    var files = {
        normal: tag && tag.dataset.ttfRegular,
        bold: tag && tag.dataset.ttfBold,
    };
    var loading = null;

    function toBase64(buffer) {
        var bytes = new Uint8Array(buffer);
        var chunks = [];
        for (var i = 0; i < bytes.length; i += 0x8000) {
            chunks.push(String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000)));
        }
        return btoa(chunks.join(''));
    }

    function readTtfs() {
        if (!loading) {
            loading = Promise.all(['normal', 'bold'].map(function (style) {
                if (!files[style]) return Promise.reject(new Error('no TTF address for ' + style));
                return fetch(files[style]).then(function (r) {
                    if (!r.ok) throw new Error(r.status + ' for ' + files[style]);
                    return r.arrayBuffer();
                }).then(function (buffer) { return [style, toBase64(buffer)]; });
            }));
            loading.catch(function () { loading = null; });
        }
        return loading;
    }

    window.BrandFonts = {
        family: FAMILY,

        ready: function (specs) {
            if (!document.fonts || !document.fonts.load) return Promise.resolve();
            return Promise.all((specs || ['16px']).map(function (spec) {
                return document.fonts.load(spec + ' "Schibsted Grotesk"').catch(function () {});
            })).then(function () {});
        },

        pdf: function (doc) {
            return readTtfs().then(function (faces) {
                faces.forEach(function (face) {
                    var file = PDF_NAME + '-' + face[0] + '.ttf';
                    doc.addFileToVFS(file, face[1]);
                    doc.addFont(file, PDF_NAME, face[0]);
                });
                return PDF_NAME;
            }).catch(function () { return 'helvetica'; });
        },

        printWhenReady: function (win) {
            // The window's stylesheet (fonts.css) has to arrive before its
            // fonts can be asked for; a print that waits longer than two
            // seconds goes ahead in the fallback font.
            var done = false;
            function print() { if (!done) { done = true; win.focus(); win.print(); } }
            function loadFonts() {
                var fonts = win.document.fonts;
                if (!fonts || !fonts.load) return print();
                Promise.all([
                    fonts.load('400 16px "Schibsted Grotesk"'),
                    fonts.load('700 16px "Schibsted Grotesk"'),
                ]).then(print, print);
            }
            if (win.document.readyState === 'complete') loadFonts();
            else win.addEventListener('load', loadFonts);
            setTimeout(print, 2000);
        },
    };
})();
