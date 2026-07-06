"""
Server-side Mermaid SVG renderer using beautiful-mermaid.

Extracts `<pre class="mermaid">` blocks from lesson HTML content,
renders them to SVGs via Node.js, and inlines the SVGs.

Usage:
    from mermaid_renderer import render_mermaid_in_html
    html = render_mermaid_in_html(lesson_content)
"""

import re
import subprocess
import os

MERMAID_DIR = os.path.join(os.path.dirname(__file__), "mermaid-renderer")
RENDER_SCRIPT = os.path.join(MERMAID_DIR, "render.js")

# Cache: mermaid_source -> svg_string
_cache: dict[str, str] = {}
_cache_hits = 0
_cache_misses = 0


def _render_one(source: str) -> str:
    """Render one mermaid diagram to SVG via Node.js subprocess."""
    global _cache_hits, _cache_misses
    key = source.strip()

    if key in _cache:
        _cache_hits += 1
        return _cache[key]

    _cache_misses += 1
    try:
        proc = subprocess.run(
            ["node", RENDER_SCRIPT],
            input=key,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=MERMAID_DIR,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"exit code {proc.returncode}")
        svg = proc.stdout.strip()
        _cache[key] = svg
        return svg
    except FileNotFoundError:
        # Node.js not available — return fallback
        return _fallback_html(key)
    except subprocess.TimeoutExpired:
        return _fallback_html(key)
    except Exception as e:
        return _fallback_html(key)


def _fallback_html(source: str) -> str:
    """Fallback: wrap source in a <pre class="mermaid"> block for client-side rendering."""
    escaped = source.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<pre class="mermaid">{escaped}</pre>'


def _wrap_svg(svg: str) -> str:
    """Wrap an SVG with our CSS variable styling for theme support."""
    return (
        f'<div class="mermaid-rendered">'
        f'{svg}'
        f'</div>'
    )


def render_mermaid_in_html(html_content: str) -> str:
    """
    Replace all `<pre class="mermaid">source</pre>` blocks with rendered SVGs.

    The SVGs use CSS custom properties for theme colours (defined in style.css),
    so theme switching works automatically.
    """
    pattern = re.compile(
        r'<pre\s+class="mermaid"[^>]*>\s*(.*?)\s*</pre>',
        re.DOTALL,
    )

    def _replacer(match: re.Match) -> str:
        source = match.group(1).strip()
        svg = _render_one(source)
        return _wrap_svg(svg)

    return pattern.sub(_replacer, html_content)


def render_mermaid_source(source: str) -> str:
    """Render a bare mermaid source string to SVG. Returns SVG string or fallback."""
    svg = _render_one(source)
    if svg.startswith("<svg") or svg.startswith('<?xml'):
        return svg
    # Subprocess may have returned raw output; try wrapping
    if svg.startswith("<pre"):
        return svg  # fallback
    return svg


def get_cache_stats() -> dict:
    return {
        "size": len(_cache),
        "hits": _cache_hits,
        "misses": _cache_misses,
    }


def clear_cache():
    _cache.clear()
    global _cache_hits, _cache_misses
    _cache_hits = 0
    _cache_misses = 0