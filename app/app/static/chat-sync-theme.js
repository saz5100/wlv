(function() {
    'use strict';

    // ── Theme syncing ──
    try {
        var m = document.cookie.match(/(?:^|;\s*)gcsecs_theme=([^;]*)/);
        var t = m && m[1] ? m[1] : 'dark';
        localStorage.theme = t === 'light' ? 'light' : 'oled-dark';
        document.documentElement.classList.remove('dark', 'light');
        document.documentElement.classList.add(t !== 'light' ? 'dark' : 'light');
        var mt = document.querySelector('meta[name=theme-color]');
        if (mt) mt.content = t !== 'light' ? '#000000' : '#ffffff';
    } catch(e) {}

    // ── postMessage listener (theme only) ──
    window.addEventListener('message', function(e) {
        if (!e.data || typeof e.data !== 'object') return;
        if (e.data.type === 'setTheme') {
            var th = e.data.theme;
            localStorage.theme = th === 'light' ? 'light' : 'oled-dark';
            document.documentElement.classList.remove('dark', 'light');
            document.documentElement.classList.add(th !== 'light' ? 'dark' : 'light');
            var mt2 = document.querySelector('meta[name=theme-color]');
            if (mt2) mt2.content = th !== 'light' ? '#000000' : '#ffffff';
        }
    });

    // ── Hide entire header bar ──
    function hideHeader() {
        // Strategy 1: Find by known button and walk up
        var found = false;
        var buttons = document.querySelectorAll('button');
        for (var i = 0; i < buttons.length; i++) {
            var label = buttons[i].getAttribute('aria-label') || '';
            if (label.indexOf('Selected model') !== -1) {
                // Found the model selector button — walk up to find the header container
                var el = buttons[i];
                for (var d = 0; d < 20; d++) {
                    if (!el || !el.parentElement) break;
                    el = el.parentElement;
                    var cls = el.className || '';
                    // The outermost header div has: max-w-full, mx-auto, px-1.5
                    if (cls.indexOf('max-w-full') !== -1 && cls.indexOf('mx-auto') !== -1) {
                        // Check this isn't the inner div (which has items-center but not mx-auto)
                        // The outer div is the one we want
                        el.style.setProperty('display', 'none', 'important');
                        found = true;
                        console.log('GCSE Tutor: Hidden header by walking up from model selector');
                        break;
                    }
                }
                if (!found) {
                    // Fallback: just hide the button itself
                    buttons[i].style.setProperty('display', 'none', 'important');
                    console.log('GCSE Tutor: Hidden model selector button directly');
                }
            }
        }

        // Strategy 2: Direct class match on the header div
        if (!found) {
            var allDivs = document.querySelectorAll('div');
            for (var i = 0; i < allDivs.length; i++) {
                var cls = allDivs[i].className || '';
                // Look for the exact header pattern
                if (cls.indexOf('max-w-full w-full mx-auto px') !== -1 && cls.indexOf('bg-transparent') !== -1) {
                    allDivs[i].style.setProperty('display', 'none', 'important');
                    found = true;
                    console.log('GCSE Tutor: Hidden header by class match');
                    break;
                }
            }
        }

        // Strategy 3: Hide individual chrome elements as fallback
        var chromeIDs = ['temporary-chat-button', 'model-selector-0-button'];
        for (var i = 0; i < chromeIDs.length; i++) {
            var el = document.getElementById(chromeIDs[i]);
            if (el) {
                el.style.setProperty('display', 'none', 'important');
                console.log('GCSE Tutor: Hidden element by ID: ' + chromeIDs[i]);
            }
        }

        return found;
    }

    // Run now and on every DOM change
    var hidden = hideHeader();
    console.log('GCSE Tutor: Initial hide ' + (hidden ? 'SUCCESS' : 'FAILED - no header found'));

    // MutationObserver + aggressive polling
    var obs = new MutationObserver(function() {
        hideHeader();
    });
    obs.observe(document.documentElement, {
        childList: true,
        subtree: true,
        attributes: true
    });

    var retries = 0;
    var iv = setInterval(function() {
        hideHeader();
        retries++;
        if (retries > 60) clearInterval(iv);
    }, 500);
})();
