// ═══════════════════════════════════════════════════════════════
// GCSE CS Revision Site — Client-Side JavaScript
// Handles: theme toggle (dark/light), slide-in navigation,
// device ID generation, settings panel, quiz question modes,
// lesson/exam data reset, modal dialogs
// ═══════════════════════════════════════════════════════════════

// GCSE CS Revision — Shared App Scripts
// Cacheable external JS (loaded at end of body)

// ── Device ID: generate + persist via cookie (no login system)
// ── Nav ──
// ── openNav(): opens slide-in drawer — always at viewport top
function openNav() {
  var links = document.getElementById('navLinks');
  if (links) {
    links.style.top = '';         // respect CSS position: fixed; top: 0
    links.style.maxHeight = '';   // respect CSS height: 100dvh
  }
  document.body.classList.add('nav-open');
}
// ── closeNav(): closes slide-in drawer + backdrop
function closeNav() { document.body.classList.remove('nav-open'); }

function toggleNav() {
  if (document.body.classList.contains('nav-open')) {
    closeNav();
  } else {
    openNav();
  }
}

// ── toggleNavSection(el): collapses/expands a section in the slide menu
function toggleNavSection(el) {
  var items = el.nextElementSibling;
  if (!items || !items.classList.contains('nav-section-items')) return;
  var isOpen = items.style.display !== 'none';
  items.style.display = isOpen ? 'none' : 'block';
  el.classList.toggle('nav-section-open', !isOpen);
}

document.addEventListener('DOMContentLoaded', function() {
    var toggle = document.getElementById('navFloatToggle');
    var backdrop = document.getElementById('navBackdrop');
    var closeBtn = document.getElementById('navClose');
    if (toggle) toggle.addEventListener('click', openNav);
    if (backdrop) {
        backdrop.addEventListener('click', closeNav);
        backdrop.addEventListener('touchstart', closeNav, {passive: true});
    }
    if (closeBtn) closeBtn.addEventListener('click', closeNav);
});

// ── Click outside nav to close: any click that isn't on the nav panel closes it ──
document.addEventListener('click', function(e) {
    if (document.body.classList.contains('nav-open')) {
        var links = document.getElementById('navLinks');
        var floatBtn = document.getElementById('navFloatToggle');
        if (links && !links.contains(e.target) && (!floatBtn || !floatBtn.contains(e.target))) {
            closeNav();
        }
    }
});

// ── Scroll to close nav: when menu is open and user scrolls, close it ──
document.addEventListener('scroll', function() {
    if (document.body.classList.contains('nav-open')) {
        closeNav();
    }
}, {passive: true});

// ── Bottom action bar — show on scroll ──
document.addEventListener('DOMContentLoaded', function() {
    var bottomBar = document.getElementById('bottomBar');
    if (!bottomBar) return;
    document.addEventListener('scroll', function() {
        var nearBottom = document.body.scrollHeight - window.scrollY - window.innerHeight < 150;
        var pageTall = document.body.scrollHeight > window.innerHeight;
        bottomBar.classList.toggle('visible', nearBottom && pageTall);
    }, {passive: true});
});

// ── Question mode ──
// ── getMode(): reads current question mode
function getMode() {
    var m = document.cookie.match(/(?:^|;\\s*)gcsecs_qmode=([^;]*)/);
    return m ? m[1] : 'soft';
}
// ── setMode(mode): saves quiz question mode (random/weighted/soft/strict) to localStorage
function setMode(mode) {
    document.cookie = 'gcsecs_qmode=' + mode + '; domain=.gcse-cs.lan; path=/; max-age=31536000; SameSite=Lax';
    showAlert('Question mode changed.', '\u2705');
}

// ── Settings panel ──
// ── toggleSettingsPanel(): shows/hides the settings panel
function toggleSettingsPanel() {
    var panel = document.getElementById('settingsPanel');
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
    var cur = getMode();
    var radio = document.querySelector('#settingsPanel input[name="qmode"][value="' + cur + '"]');
    if (radio) radio.checked = true;
}
document.addEventListener('DOMContentLoaded', function() {
    var panel = document.getElementById('settingsPanel');
    if (!panel) return;
    document.addEventListener('click', function(e) {
        if (panel.style.display !== 'none' &&
            !panel.contains(e.target) &&
            !e.target.closest('[onclick*="toggleSettingsPanel"]') &&
            !e.target.closest('[onclick*="toggleThemeBase"]')) {
            panel.style.display = 'none';
        }
    });
});
// ── resetLessons(): clears all lesson progress, streaks, and review schedule (keeps exam history)
async function resetLessons() {
    var ok = await showConfirm('Reset all lesson progress?\n\nThis clears:\n\u2022 Correct streaks for all questions\n\u2022 All quiz attempt records\n\u2022 Spaced repetition review dates\n\nQuestions will feel fresh again. Exam history is NOT affected.');
    if (!ok) return;
    try {
        var resp = await fetch('/reset-lessons', {method:'POST'});
        var data = await resp.json();
        if (data.status === 'ok') {
            showAlert('Lesson progress reset complete! All questions are fresh again.', '\u2705');
            setTimeout(function() { location.reload(); }, 1500);
        } else {
            showAlert('Error: ' + (data.error || 'unknown'), '\u274c');
        }
    } catch(e) {
        showAlert('Network error: ' + e.message, '\u274c');
    }
}

// ── resetExams(): deletes all exam attempts and grades (keeps lesson progress)
async function resetExams() {
    var ok = await showConfirm('Delete all exam history?\n\nThis permanently removes:\n\u2022 All past exam results\n\u2022 Score history and grades\n\nLesson progress and question streaks are NOT affected.');
    if (!ok) return;
    try {
        var resp = await fetch('/reset-exams', {method:'POST'});
        var data = await resp.json();
        if (data.status === 'ok') {
            showAlert('Exam history deleted! All past results are gone.', '\u2705');
            setTimeout(function() { location.reload(); }, 1500);
        } else {
            showAlert('Error: ' + (data.error || 'unknown'), '\u274c');
        }
    } catch(e) {
        showAlert('Network error: ' + e.message, '\u274c');
    }
}
// ── DOMContentLoaded: sync theme icon on page load, set initial question mode radio
document.addEventListener('DOMContentLoaded', function() {
    var cur = getMode();
    var radio = document.querySelector('#settingsPanel input[name="qmode"][value="' + cur + '"]');
    if (radio) radio.checked = true;
    // Add data-label attributes to lesson tables for mobile responsive stacking
    document.querySelectorAll('.lesson-content table').forEach(function(table) {
        var headers = [];
        table.querySelectorAll('thead th, thead td').forEach(function(th) {
            headers.push(th.textContent.trim());
        });
        if (!headers.length) return;
        table.querySelectorAll('tbody tr').forEach(function(row) {
            row.querySelectorAll('td').forEach(function(td, i) {
                if (headers[i]) td.setAttribute('data-label', headers[i]);
            });
        });
    });
});

// ── Theme ──
// ── Theme: read from localStorage/cookie, default to 'dark'
function getThemeBase() {
    return localStorage.getItem('gcsecs_theme') || 'dark';
}
// ── setThemeBase(theme): applies .light-theme class, updates all UI elements, syncs nav icon, persists to localStorage + cookie
function setThemeBase(theme) {
    var nt = document.getElementById("navThemeToggle");
    if (nt) nt.textContent = theme === "light" ? "☀️" : "🌙";
    var st = document.getElementById("navSlideThemeToggle");
    if (st) st.textContent = (theme === "light" ? "☀️" : "🌙") + " Theme";
    document.body.classList.toggle('light-theme', theme === 'light');
    var label = document.getElementById('settingsThemeLabel');
    if (label) label.innerHTML = theme === 'light' ? '\u2600\ufe0f Light Mode' : '\ud83c\udf19 Dark Mode';
    var toggle = document.getElementById('settingsThemeToggle');
    if (toggle) toggle.textContent = theme === 'light' ? '\u25cf' : '\u25cb';
    localStorage.setItem('gcsecs_theme', theme);
    document.cookie = 'gcsecs_theme=' + theme + '; domain=.gcse-cs.lan; path=/; max-age=31536000; SameSite=Lax';
    // Switch D2 diagrams for dark/light theme
    document.querySelectorAll('.d2-diagram').forEach(function(img) {
        var src = img.getAttribute('data-src-' + theme);
        if (src) img.src = src;
    });
    var ifr = document.querySelector('iframe[src*=":8080"]');
    if (ifr && ifr.contentWindow) {
        ifr.contentWindow.postMessage({type:'setTheme', theme: theme}, '*');
    }
    // Notify mermaid diagrams to re-render with new theme
    window.dispatchEvent(new CustomEvent('themeChanged', {detail: {theme: theme}}));
}
// ── toggleThemeBase(): switches between dark/light
function toggleThemeBase() {
    setThemeBase(getThemeBase() === 'dark' ? 'light' : 'dark');
}
setThemeBase(getThemeBase());
(function() {
    var curMode = getMode();
    var radio = document.getElementById('mode_' + curMode);
    if (radio) radio.checked = true;
})();

// NOTE: inline search bar removed per student feedback.
// Search is available via hamburger menu → Search (/search).
// Home page topic card filtering was tied to the removed search bar
// and has been removed accordingly.

// ── Modal dialog system ──
function showAlert(msg, icon) {
    return new Promise(function(resolve) {
        var ov = document.getElementById('modalOverlay');
        document.getElementById('modalHeader').innerHTML = icon || '\u26a0\ufe0f';
        document.getElementById('modalBody').textContent = msg;
        var actions = document.getElementById('modalActions');
        actions.innerHTML = '<button class="btn btn-primary btn-sm" id="modalConfirm">OK</button>';
        ov.style.display = 'flex';
        document.getElementById('modalConfirm').onclick = function() {
            ov.style.display = 'none';
            resolve();
        };
        ov.onclick = function(e) {
            if (e.target === ov) { ov.style.display = 'none'; resolve(); }
        };
    });
}
function showConfirm(msg) {
    return new Promise(function(resolve) {
        var ov = document.getElementById('modalOverlay');
        document.getElementById('modalHeader').innerHTML = '\u2753';
        document.getElementById('modalBody').textContent = msg;
        var actions = document.getElementById('modalActions');
        actions.innerHTML = '<button class="btn btn-sm" id="modalCancel">Cancel</button><button class="btn btn-primary btn-sm" id="modalConfirm">OK</button>';
        ov.style.display = 'flex';
        document.getElementById('modalConfirm').onclick = function() {
            ov.style.display = 'none';
            resolve(true);
        };
        document.getElementById('modalCancel').onclick = function() {
            ov.style.display = 'none';
            resolve(false);
        };
        ov.onclick = function(e) {
            if (e.target === ov) { ov.style.display = 'none'; resolve(false); }
        };
    });
}
// Patch native alert/confirm to use custom dialogs
window._nativeAlert = window.alert;
window.alert = function(msg) { showAlert(msg, '\u26a0\ufe0f'); };
window._nativeConfirm = window.confirm;
window.confirm = function(msg) { return showConfirm(msg); };

// ── Swipe-to-close on mobile nav ──
(function() {
    var startX = 0, startY = 0;
    document.addEventListener('touchstart', function(e) {
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
    }, {passive: true});
    document.addEventListener('touchmove', function(e) {
        if (!document.body.classList.contains('nav-open')) return;
        var dx = e.touches[0].clientX - startX;
        var dy = e.touches[0].clientY - startY;
        if (dx < -80 && Math.abs(dx) > Math.abs(dy) * 1.5) {
            closeNav();
        }
    }, {passive: true});
})();

// ── Daily Revision Streak Engine ──
function initStreakEngine() {
    var today = new Date().toISOString().split('T')[0];
    var yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0];
    var streakCount = parseInt(localStorage.getItem('study_streak_count') || '0');
    var lastStudyDate = localStorage.getItem('study_last_date') || '';
    if (lastStudyDate) {
        if (lastStudyDate === today) {
            // Already counted today
        } else if (lastStudyDate === yesterday) {
            // Maintained
        } else {
            // Broken
            streakCount = 0;
            localStorage.setItem('study_streak_count', '0');
        }
    } else {
        streakCount = 0;
        localStorage.setItem('study_streak_count', '0');
    }
    updateStreakDOM(streakCount);
}

function recordStudyStreak(scorePct) {
    var today = new Date().toISOString().split('T')[0];
    var yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0];
    var streakCount = parseInt(localStorage.getItem('study_streak_count') || '0');
    var lastStudyDate = localStorage.getItem('study_last_date') || '';
    if (lastStudyDate !== today) {
        if (lastStudyDate === yesterday || streakCount === 0) {
            streakCount++;
        } else {
            streakCount = 1;
        }
        localStorage.setItem('study_streak_count', streakCount.toString());
        localStorage.setItem('study_last_date', today);
    }
    // Quality multiplier: score >= 80% awards ×2 badge for today
    if (typeof scorePct === 'number' && scorePct >= 80) {
        localStorage.setItem('study_streak_quality_date', today);
    }
    updateStreakDOM(streakCount);
}

function updateStreakDOM(count) {
    var today = new Date().toISOString().split('T')[0];
    var qualityToday = localStorage.getItem('study_streak_quality_date') === today;
    var navStreak = document.getElementById('navStreakCount');
    if (navStreak) {
        navStreak.textContent = count + (qualityToday ? ' ×2' : '');
        var parent = navStreak.closest('.nav-streak-badge');
        if (parent) {
            parent.style.display = count > 0 ? 'inline-flex' : 'none';
            parent.title = qualityToday ? 'Quality streak! You scored 80%+ today.' : count + '-day study streak';
        }
    }
    var homeStreak = document.getElementById('homeStreakCount');
    if (homeStreak) {
        homeStreak.textContent = count;
    }
    var homeQuality = document.getElementById('homeStreakQuality');
    if (homeQuality) {
        homeQuality.style.display = qualityToday ? 'inline' : 'none';
    }
    var homeStreakContainer = document.getElementById('homeStreakWidget');
    if (homeStreakContainer) {
        homeStreakContainer.style.display = count > 0 ? 'block' : 'none';
    }
}

document.addEventListener('DOMContentLoaded', function() {
    initStreakEngine();
    if (window.location.pathname.indexOf('/lesson/') === 0) {
        recordStudyStreak();
    }
});
