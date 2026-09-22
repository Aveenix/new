(function () {
    'use strict';

    // 1. Google Translate Init Callback
    window.googleTranslateElementInit = function () {
        if (window.google && window.google.translate) {
            new window.google.translate.TranslateElement({
                pageLanguage: 'en',
                includedLanguages: 'en,gu,hi,es,fr,de,it,ar,zh-CN,ja,pt',
                layout: window.google.translate.TranslateElement.InlineLayout.SIMPLE,
                autoDisplay: false
            }, 'google_translate_element');
        }
    };

    // Hide Google Translate top banner iframe and prevent body top shift
    function hideGoogleBanner() {
        document.body.style.top = '0px';
        document.body.style.marginTop = '0px';
        document.documentElement.style.top = '0px';
        document.documentElement.style.marginTop = '0px';

        var frames = document.querySelectorAll('.goog-te-banner-frame, iframe[class*="VIpgJd"], iframe[src*="translate.google"], iframe[id*="container"]');
        frames.forEach(function (f) {
            f.style.display = 'none';
            f.style.visibility = 'hidden';
            f.style.height = '0';
            f.style.width = '0';
        });
    }

    function setGoogleCookie(langCode) {
        var val = (langCode === 'en') ? '/en/en' : ('/en/' + langCode);
        var domain = window.location.hostname;

        // Clear old cookie variations
        document.cookie = "googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        document.cookie = "googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/; domain=" + domain + ";";

        // Set new cookie
        document.cookie = "googtrans=" + val + "; path=/;";
        document.cookie = "googtrans=" + val + "; path=/; domain=" + domain + ";";
    }

    function getCookie(name) {
        var nameEQ = name + "=";
        var ca = document.cookie.split(';');
        for (var i = 0; i < ca.length; i++) {
            var c = ca[i];
            while (c.charAt(0) === ' ') c = c.substring(1, c.length);
            if (c.indexOf(nameEQ) === 0) return c.substring(nameEQ.length, c.length);
        }
        return null;
    }

    function detectOdooLanguage() {
        // 1. Check URL path prefix (e.g., /gu/, /hi/, /fr/, /es/)
        var path = window.location.pathname;
        var pathMatch = path.match(/^\/([a-z]{2})(_[A-Z]{2})?(\/|$)/);
        if (pathMatch && pathMatch[1] && pathMatch[1] !== 'en') {
            return pathMatch[1].toLowerCase();
        }

        // 2. Check HTML lang attribute (e.g., gu-IN, gu, hi, fr, es)
        var htmlLang = (document.documentElement.lang || '').toLowerCase();
        if (htmlLang) {
            var langPart = htmlLang.split('-')[0].split('_')[0];
            if (langPart && langPart !== 'en') {
                return langPart;
            }
        }

        // 3. Check Odoo session context if available
        if (window.odoo && window.odoo.session_info && window.odoo.session_info.user_context) {
            var ctxLang = (window.odoo.session_info.user_context.lang || '').toLowerCase();
            if (ctxLang) {
                var cPart = ctxLang.split('_')[0];
                if (cPart && cPart !== 'en') {
                    return cPart;
                }
            }
        }

        return 'en';
    }

    function initAutoTranslate() {
        hideGoogleBanner();
        setInterval(hideGoogleBanner, 400);

        var targetLang = detectOdooLanguage();
        var currentCookie = getCookie('googtrans');
        var expectedCookieVal = (targetLang === 'en') ? '/en/en' : ('/en/' + targetLang);

        // Inject Google Translate script if non-english or google translate active
        if (targetLang !== 'en' || (currentCookie && currentCookie !== '/en/en')) {
            if (!document.getElementById('google-translate-script')) {
                var script = document.createElement('script');
                script.id = 'google-translate-script';
                script.type = 'text/javascript';
                script.src = '//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit';
                document.head.appendChild(script);
            }

            if (!document.getElementById('google_translate_element')) {
                var hiddenDiv = document.createElement('div');
                hiddenDiv.id = 'google_translate_element';
                hiddenDiv.style.display = 'none';
                document.body.appendChild(hiddenDiv);
            }
        }

        // If target language cookie doesn't match active Odoo language, set cookie
        if (currentCookie !== expectedCookieVal) {
            setGoogleCookie(targetLang);
            var selectEl = document.querySelector('.goog-te-combo');
            if (selectEl) {
                selectEl.value = targetLang;
                selectEl.dispatchEvent(new Event('change'));
            } else if (targetLang !== 'en') {
                window.location.reload();
            }
        }

        // Also intercept clicks on native Odoo language switcher links (/website/lang/...)
        document.querySelectorAll('a[href*="/website/lang/"]').forEach(function (link) {
            link.addEventListener('click', function (e) {
                var href = this.getAttribute('href') || '';
                var match = href.match(/\/website\/lang\/([a-zA-Z_]+)/);
                if (match && match[1]) {
                    var rawCode = match[1]; // e.g. gu_IN, fr_FR, en_US
                    var lCode = rawCode.split('_')[0].toLowerCase();
                    setGoogleCookie(lCode);
                }
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAutoTranslate);
    } else {
        initAutoTranslate();
    }
})();
