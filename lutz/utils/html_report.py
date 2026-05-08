"""Generate a self-contained HTML report from a lutz per-article analysis JSON."""

from __future__ import annotations

import html as _html
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Badge colour palette (bg, text, border)
# ---------------------------------------------------------------------------

_BADGE_COLORS: dict[str, tuple[str, str, str]] = {
    "INCLUDE":     ("#dcfce7", "#166534", "#86efac"),
    "EXCLUDE":     ("#fee2e2", "#991b1b", "#fca5a5"),
    "UNCERTAIN":   ("#fef3c7", "#92400e", "#fcd34d"),
    "HIGH":        ("#dcfce7", "#166534", "#86efac"),
    "MEDIUM":      ("#fef3c7", "#92400e", "#fcd34d"),
    "LOW":         ("#fee2e2", "#991b1b", "#fca5a5"),
    "RELEVANT":    ("#dcfce7", "#166534", "#86efac"),
    "NOT_RELEVANT":("#fee2e2", "#991b1b", "#fca5a5"),
    "UNKNOWN":     ("#f3f4f6", "#374151", "#d1d5db"),
}

_DEFAULT_BADGE = ("#f3f4f6", "#374151", "#d1d5db")


def _badge(label: str) -> tuple[str, str, str]:
    return _BADGE_COLORS.get(label.upper().replace(" ", "_"), _DEFAULT_BADGE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_html_report(report: dict) -> str:
    """Return a self-contained HTML string for a per-article analysis report."""
    meta = report.get("metadata", {})
    articles: list[dict] = report.get("articles", [])

    # --- aggregate counts ----------------------------------------------------
    label_counts: dict[str, int] = {}
    for a in articles:
        lbl = (a.get("relevance") or "UNKNOWN").upper()
        label_counts[lbl] = label_counts.get(lbl, 0) + 1
    all_labels = sorted(label_counts.keys())
    total = len(articles)

    # --- metadata display ----------------------------------------------------
    raw_ts = meta.get("started_at", "")
    try:
        dt = datetime.fromisoformat(raw_ts)
        ts_display = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        ts_display = raw_ts or "—"

    llm_meta = meta.get("llm", {})
    model = _html.escape(llm_meta.get("model", "—"))
    prompt_path = _html.escape(meta.get("prompt_path", "—"))
    total_tokens = llm_meta.get("total_tokens", 0)
    elapsed = meta.get("elapsed_seconds", 0)

    # --- filter buttons ------------------------------------------------------
    btn_all = (
        f'<button class="fbtn active" data-filter="all" '
        f'onclick="applyFilter(this)">All ({total})</button>'
    )
    label_btns = ""
    for lbl in all_labels:
        bg, txt, brd = _badge(lbl)
        cnt = label_counts[lbl]
        label_btns += (
            f'<button class="fbtn" data-filter="{_html.escape(lbl)}" '
            f'onclick="applyFilter(this)" '
            f'style="background:{bg};color:{txt};border-color:{brd}">'
            f'{_html.escape(lbl)} ({cnt})</button>\n'
        )

    # --- summary stats -------------------------------------------------------
    stats_html = ""
    for lbl in all_labels:
        bg, txt, brd = _badge(lbl)
        cnt = label_counts[lbl]
        pct = round(cnt / total * 100) if total else 0
        stats_html += (
            f'<div class="stat-card" '
            f'style="background:{bg};border-left:4px solid {brd}">\n'
            f'  <div class="stat-label" style="color:{txt}">{_html.escape(lbl)}</div>\n'
            f'  <div class="stat-count" style="color:{txt}">{cnt}</div>\n'
            f'  <div class="stat-pct" style="color:{txt}">{pct}%</div>\n'
            f'</div>\n'
        )

    # --- article cards -------------------------------------------------------
    cards_html = ""
    for art in articles:
        fn = _html.escape(art.get("filename", "unknown"))
        relevance = (art.get("relevance") or "UNKNOWN").upper()
        analysis_raw = art.get("analysis") or ""
        error = art.get("error")
        chunks = art.get("chunks_used", 0)
        art_tokens = art.get("llm_total_tokens", 0)

        bg, txt, brd = _badge(relevance)
        badge_html = (
            f'<span class="badge" '
            f'style="background:{bg};color:{txt};border:1px solid {brd}">'
            f'{_html.escape(relevance)}</span>'
        )

        if error:
            body_html = (
                f'<p class="err-msg">&#9888; Error: {_html.escape(error)}</p>'
            )
        else:
            analysis_escaped = _html.escape(analysis_raw).replace("\n", "<br>")
            body_html = (
                f'<details>\n'
                f'  <summary>Show analysis</summary>\n'
                f'  <div class="analysis-text">{analysis_escaped}</div>\n'
                f'</details>\n'
            )

        meta_line = f'<span class="art-meta">{chunks} chunks &middot; {art_tokens:,} tokens</span>'

        cards_html += (
            f'<article class="card" data-relevance="{_html.escape(relevance)}">\n'
            f'  <div class="card-hd">\n'
            f'    <span class="card-fn">{fn}</span>\n'
            f'    <div class="card-right">{meta_line}{badge_html}</div>\n'
            f'  </div>\n'
            f'  {body_html}\n'
            f'</article>\n'
        )

    # --- assemble full page --------------------------------------------------
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>lutz &mdash; Analysis Report</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f8fafc; color: #1e293b; line-height: 1.6;
    }}
    a {{ color: inherit; }}

    /* ---- layout ---- */
    .container {{ max-width: 900px; margin: 0 auto; padding: 2rem 1rem 4rem; }}

    /* ---- header ---- */
    .report-header {{
      background: #1e293b; color: #f1f5f9;
      border-radius: 12px; padding: 2rem;
      margin-bottom: 2rem;
    }}
    .report-header h1 {{
      font-size: 1.5rem; font-weight: 700;
      display: flex; align-items: center; gap: 0.5rem;
      margin-bottom: 1rem;
    }}
    .report-header h1 .logo {{ color: #38bdf8; }}
    .meta-grid {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 0.75rem; font-size: 0.85rem;
    }}
    .meta-item {{ display: flex; flex-direction: column; gap: 0.15rem; }}
    .meta-key {{ color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    .meta-val {{ color: #e2e8f0; word-break: break-all; }}

    /* ---- stat cards ---- */
    .stats {{ display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 1.5rem; }}
    .stat-card {{
      flex: 1 1 120px; border-radius: 8px; padding: 1rem;
      display: flex; flex-direction: column; gap: 0.25rem;
    }}
    .stat-label {{ font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }}
    .stat-count {{ font-size: 2rem; font-weight: 700; line-height: 1; }}
    .stat-pct {{ font-size: 0.85rem; }}

    /* ---- filter bar ---- */
    .filter-bar {{
      display: flex; flex-wrap: wrap; gap: 0.5rem;
      margin-bottom: 1.5rem; align-items: center;
    }}
    .filter-bar-label {{
      font-size: 0.8rem; font-weight: 600;
      color: #64748b; text-transform: uppercase;
      letter-spacing: 0.05em; margin-right: 0.25rem;
    }}
    .fbtn {{
      padding: 0.35rem 0.9rem; border-radius: 99px;
      border: 1px solid #cbd5e1; background: #fff; color: #475569;
      cursor: pointer; font-size: 0.85rem; font-weight: 500;
      transition: all 0.15s;
    }}
    .fbtn:hover {{ border-color: #94a3b8; }}
    .fbtn.active {{
      background: #1e293b; color: #f1f5f9; border-color: #1e293b;
    }}

    /* ---- cards ---- */
    .card {{
      background: #fff; border: 1px solid #e2e8f0;
      border-radius: 10px; padding: 1.25rem;
      margin-bottom: 1rem;
      transition: box-shadow 0.15s;
    }}
    .card:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    .card.hidden {{ display: none; }}
    .card-hd {{
      display: flex; align-items: flex-start;
      justify-content: space-between; gap: 1rem;
      margin-bottom: 0.75rem;
    }}
    .card-fn {{
      font-weight: 600; font-size: 0.95rem;
      color: #1e293b; word-break: break-all;
    }}
    .card-right {{
      display: flex; align-items: center; gap: 0.6rem;
      flex-shrink: 0;
    }}
    .art-meta {{
      font-size: 0.75rem; color: #94a3b8; white-space: nowrap;
    }}
    .badge {{
      padding: 0.25rem 0.65rem; border-radius: 99px;
      font-size: 0.75rem; font-weight: 700;
      letter-spacing: 0.04em; white-space: nowrap;
    }}
    .err-msg {{
      color: #dc2626; font-size: 0.9rem;
      background: #fef2f2; border-radius: 6px; padding: 0.75rem;
    }}
    details summary {{
      cursor: pointer; font-size: 0.85rem; color: #64748b;
      font-weight: 500; user-select: none;
    }}
    details summary:hover {{ color: #1e293b; }}
    .analysis-text {{
      margin-top: 0.75rem;
      font-size: 0.875rem; color: #334155;
      background: #f8fafc; border-radius: 6px;
      padding: 1rem; white-space: pre-wrap;
      border: 1px solid #e2e8f0;
      max-height: 400px; overflow-y: auto;
    }}

    /* ---- no results ---- */
    #no-results {{
      text-align: center; padding: 3rem;
      color: #94a3b8; font-size: 0.95rem;
      display: none;
    }}

    /* ---- footer ---- */
    .footer {{
      text-align: center; margin-top: 3rem;
      font-size: 0.8rem; color: #94a3b8;
    }}
    .footer a {{ color: #64748b; text-decoration: none; }}
    .footer a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="container">

    <!-- Header -->
    <header class="report-header">
      <h1><span class="logo">lutz</span> &mdash; Analysis Report</h1>
      <div class="meta-grid">
        <div class="meta-item">
          <span class="meta-key">Timestamp</span>
          <span class="meta-val">{ts_display}</span>
        </div>
        <div class="meta-item">
          <span class="meta-key">Model</span>
          <span class="meta-val">{model}</span>
        </div>
        <div class="meta-item">
          <span class="meta-key">Prompt</span>
          <span class="meta-val">{prompt_path}</span>
        </div>
        <div class="meta-item">
          <span class="meta-key">Articles</span>
          <span class="meta-val">{total}</span>
        </div>
        <div class="meta-item">
          <span class="meta-key">Total tokens</span>
          <span class="meta-val">{total_tokens:,}</span>
        </div>
        <div class="meta-item">
          <span class="meta-key">Duration</span>
          <span class="meta-val">{elapsed:.1f}s</span>
        </div>
      </div>
    </header>

    <!-- Summary stats -->
    <div class="stats">
      {stats_html}
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">
      <span class="filter-bar-label">Filter:</span>
      {btn_all}
      {label_btns}
    </div>

    <!-- Article cards -->
    <div id="article-list">
      {cards_html}
    </div>
    <div id="no-results">No articles match this filter.</div>

    <footer class="footer">
      Generated by <a href="https://github.com/jooguilhermesc/lutz">lutz</a>
    </footer>
  </div>

  <script>
    function applyFilter(btn) {{
      document.querySelectorAll('.fbtn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const f = btn.dataset.filter;
      let visible = 0;
      document.querySelectorAll('.card').forEach(card => {{
        const show = f === 'all' || card.dataset.relevance === f;
        card.classList.toggle('hidden', !show);
        if (show) visible++;
      }});
      document.getElementById('no-results').style.display = visible === 0 ? 'block' : 'none';
    }}
  </script>
</body>
</html>
"""
