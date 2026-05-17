"""Generate self-contained HTML reports from lutz JSON outputs."""

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


# ---------------------------------------------------------------------------
# Citations report
# ---------------------------------------------------------------------------

def generate_html_citations_report(report: dict) -> str:
    """Return a self-contained HTML string for a citations report."""
    meta = report.get("metadata", {})
    relevant_articles: list[dict] = report.get("relevant_articles", [])
    not_relevant_articles: list[dict] = report.get("not_relevant_articles", [])
    unknown_articles: list[dict] = report.get("unknown_articles", [])

    # --- metadata display ----------------------------------------------------
    raw_ts = meta.get("generated_at", "")
    try:
        dt = datetime.fromisoformat(raw_ts)
        ts_display = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        ts_display = raw_ts or "—"

    llm_meta = meta.get("llm", {})
    model = _html.escape(llm_meta.get("model", "—"))
    analysis_file = _html.escape(meta.get("analysis_file", "—"))
    total_tokens = llm_meta.get("total_tokens", 0)
    elapsed = meta.get("elapsed_seconds", 0)
    n_relevant = meta.get("relevant", len(relevant_articles))
    n_not_relevant = meta.get("not_relevant", len(not_relevant_articles))
    n_unknown = meta.get("unknown", len(unknown_articles))
    total = meta.get("total_articles", n_relevant + n_not_relevant + n_unknown)

    # --- summary stats -------------------------------------------------------
    stats_data = [
        ("INCLUDE", n_relevant),
        ("EXCLUDE", n_not_relevant),
        ("UNKNOWN", n_unknown),
    ]
    stats_html = ""
    for lbl, cnt in stats_data:
        if cnt == 0:
            continue
        bg, txt, brd = _badge(lbl)
        pct = round(cnt / total * 100) if total else 0
        stats_html += (
            f'<div class="stat-card" style="background:{bg};border-left:4px solid {brd}">\n'
            f'  <div class="stat-label" style="color:{txt}">{_html.escape(lbl)}</div>\n'
            f'  <div class="stat-count" style="color:{txt}">{cnt}</div>\n'
            f'  <div class="stat-pct" style="color:{txt}">{pct}%</div>\n'
            f'</div>\n'
        )

    # --- filter buttons ------------------------------------------------------
    filter_btns = f'<button class="fbtn active" data-filter="all" onclick="applyFilter(this)">All ({total})</button>\n'
    for lbl, cnt in stats_data:
        if cnt == 0:
            continue
        bg, txt, brd = _badge(lbl)
        filter_btns += (
            f'<button class="fbtn" data-filter="{_html.escape(lbl)}" onclick="applyFilter(this)" '
            f'style="background:{bg};color:{txt};border-color:{brd}">'
            f'{_html.escape(lbl)} ({cnt})</button>\n'
        )

    # --- relevant article cards ----------------------------------------------
    cards_html = ""
    for art in relevant_articles:
        fn = _html.escape(art.get("filename", "unknown"))
        label = _html.escape(str(art.get("label") or "—"))
        confidence = art.get("confidence", "—")
        reasoning = _html.escape(art.get("reasoning") or "")
        citations: list[dict] = art.get("citations") or []
        art_tokens = art.get("llm_total_tokens", 0)
        error = art.get("error")

        bg, txt, brd = _badge("INCLUDE")
        badge_html = (
            f'<span class="badge" style="background:{bg};color:{txt};border:1px solid {brd}">INCLUDE</span>'
        )

        if error:
            body_html = f'<p class="err-msg">&#9888; Error: {_html.escape(error)}</p>'
        else:
            cit_rows = ""
            for c in citations:
                page = _html.escape(str(c.get("page", "—")))
                text = _html.escape(c.get("text", ""))
                cit_rows += (
                    f'<tr><td class="pg-cell">{page}</td>'
                    f'<td class="cit-cell">{text}</td></tr>\n'
                )
            cit_table = (
                f'<table class="cit-table"><thead><tr>'
                f'<th>Page</th><th>Citation</th></tr></thead>'
                f'<tbody>{cit_rows}</tbody></table>'
            ) if citations else '<p class="no-cit">No citations extracted.</p>'

            reasoning_html = (
                f'<div class="reasoning-block">'
                f'<span class="reasoning-label">Reasoning:</span> {reasoning}'
                f'</div>'
            ) if reasoning else ""

            body_html = (
                f'<details>\n'
                f'  <summary>Label: {label} &middot; Confidence: {confidence} '
                f'&middot; {art_tokens:,} tokens</summary>\n'
                f'  <div class="detail-body">\n'
                f'    {reasoning_html}\n'
                f'    {cit_table}\n'
                f'  </div>\n'
                f'</details>\n'
            )

        cards_html += (
            f'<article class="card" data-relevance="INCLUDE">\n'
            f'  <div class="card-hd">\n'
            f'    <span class="card-fn">{fn}</span>\n'
            f'    <div class="card-right">'
            f'<span class="art-meta">{len(citations)} citation(s)</span>'
            f'{badge_html}</div>\n'
            f'  </div>\n'
            f'  {body_html}\n'
            f'</article>\n'
        )

    for art in not_relevant_articles:
        fn = _html.escape(art.get("filename", "unknown"))
        bg, txt, brd = _badge("EXCLUDE")
        badge_html = (
            f'<span class="badge" style="background:{bg};color:{txt};border:1px solid {brd}">EXCLUDE</span>'
        )
        cards_html += (
            f'<article class="card" data-relevance="EXCLUDE">\n'
            f'  <div class="card-hd">\n'
            f'    <span class="card-fn">{fn}</span>\n'
            f'    <div class="card-right">{badge_html}</div>\n'
            f'  </div>\n'
            f'</article>\n'
        )

    for art in unknown_articles:
        fn = _html.escape(art.get("filename", "unknown"))
        raw = _html.escape(art.get("raw_analysis") or "").replace("\n", "<br>")
        bg, txt, brd = _badge("UNKNOWN")
        badge_html = (
            f'<span class="badge" style="background:{bg};color:{txt};border:1px solid {brd}">UNKNOWN</span>'
        )
        body_html = (
            f'<details><summary>Show raw analysis</summary>'
            f'<div class="analysis-text">{raw}</div></details>'
        ) if raw else ""
        cards_html += (
            f'<article class="card" data-relevance="UNKNOWN">\n'
            f'  <div class="card-hd">\n'
            f'    <span class="card-fn">{fn}</span>\n'
            f'    <div class="card-right">{badge_html}</div>\n'
            f'  </div>\n'
            f'  {body_html}\n'
            f'</article>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>lutz &mdash; Citations Report</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f8fafc; color: #1e293b; line-height: 1.6;
    }}
    .container {{ max-width: 900px; margin: 0 auto; padding: 2rem 1rem 4rem; }}
    .report-header {{
      background: #1e293b; color: #f1f5f9;
      border-radius: 12px; padding: 2rem; margin-bottom: 2rem;
    }}
    .report-header h1 {{
      font-size: 1.5rem; font-weight: 700;
      display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem;
    }}
    .report-header h1 .logo {{ color: #38bdf8; }}
    .meta-grid {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 0.75rem; font-size: 0.85rem;
    }}
    .meta-item {{ display: flex; flex-direction: column; gap: 0.15rem; }}
    .meta-key {{ color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    .meta-val {{ color: #e2e8f0; word-break: break-all; }}
    .stats {{ display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 1.5rem; }}
    .stat-card {{
      flex: 1 1 120px; border-radius: 8px; padding: 1rem;
      display: flex; flex-direction: column; gap: 0.25rem;
    }}
    .stat-label {{ font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }}
    .stat-count {{ font-size: 2rem; font-weight: 700; line-height: 1; }}
    .stat-pct {{ font-size: 0.85rem; }}
    .filter-bar {{
      display: flex; flex-wrap: wrap; gap: 0.5rem;
      margin-bottom: 1.5rem; align-items: center;
    }}
    .filter-bar-label {{
      font-size: 0.8rem; font-weight: 600; color: #64748b;
      text-transform: uppercase; letter-spacing: 0.05em; margin-right: 0.25rem;
    }}
    .fbtn {{
      padding: 0.35rem 0.9rem; border-radius: 99px;
      border: 1px solid #cbd5e1; background: #fff; color: #475569;
      cursor: pointer; font-size: 0.85rem; font-weight: 500; transition: all 0.15s;
    }}
    .fbtn:hover {{ border-color: #94a3b8; }}
    .fbtn.active {{ background: #1e293b; color: #f1f5f9; border-color: #1e293b; }}
    .card {{
      background: #fff; border: 1px solid #e2e8f0;
      border-radius: 10px; padding: 1.25rem; margin-bottom: 1rem;
      transition: box-shadow 0.15s;
    }}
    .card:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    .card.hidden {{ display: none; }}
    .card-hd {{
      display: flex; align-items: flex-start;
      justify-content: space-between; gap: 1rem;
    }}
    .card-fn {{ font-weight: 600; font-size: 0.95rem; color: #1e293b; word-break: break-all; }}
    .card-right {{ display: flex; align-items: center; gap: 0.6rem; flex-shrink: 0; }}
    .art-meta {{ font-size: 0.75rem; color: #94a3b8; white-space: nowrap; }}
    .badge {{
      padding: 0.25rem 0.65rem; border-radius: 99px;
      font-size: 0.75rem; font-weight: 700; letter-spacing: 0.04em; white-space: nowrap;
    }}
    .err-msg {{
      color: #dc2626; font-size: 0.9rem;
      background: #fef2f2; border-radius: 6px; padding: 0.75rem; margin-top: 0.75rem;
    }}
    details {{ margin-top: 0.75rem; }}
    details summary {{
      cursor: pointer; font-size: 0.85rem; color: #64748b;
      font-weight: 500; user-select: none;
    }}
    details summary:hover {{ color: #1e293b; }}
    .detail-body {{ margin-top: 0.75rem; }}
    .reasoning-block {{
      font-size: 0.875rem; color: #334155;
      background: #f8fafc; border-radius: 6px; padding: 0.75rem;
      border: 1px solid #e2e8f0; margin-bottom: 0.75rem;
    }}
    .reasoning-label {{ font-weight: 600; }}
    .cit-table {{
      width: 100%; border-collapse: collapse;
      font-size: 0.85rem;
    }}
    .cit-table th {{
      text-align: left; padding: 0.5rem 0.75rem;
      background: #f1f5f9; color: #475569;
      font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em;
      border-bottom: 1px solid #e2e8f0;
    }}
    .cit-table td {{ padding: 0.5rem 0.75rem; border-bottom: 1px solid #f1f5f9; }}
    .cit-table tr:last-child td {{ border-bottom: none; }}
    .pg-cell {{ white-space: nowrap; color: #64748b; width: 60px; }}
    .cit-cell {{ color: #1e293b; }}
    .no-cit {{ font-size: 0.85rem; color: #94a3b8; font-style: italic; }}
    .analysis-text {{
      margin-top: 0.75rem; font-size: 0.875rem; color: #334155;
      background: #f8fafc; border-radius: 6px; padding: 1rem;
      white-space: pre-wrap; border: 1px solid #e2e8f0;
      max-height: 400px; overflow-y: auto;
    }}
    #no-results {{
      text-align: center; padding: 3rem;
      color: #94a3b8; font-size: 0.95rem; display: none;
    }}
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
    <header class="report-header">
      <h1><span class="logo">lutz</span> &mdash; Citations Report</h1>
      <div class="meta-grid">
        <div class="meta-item">
          <span class="meta-key">Generated at</span>
          <span class="meta-val">{ts_display}</span>
        </div>
        <div class="meta-item">
          <span class="meta-key">Model</span>
          <span class="meta-val">{model}</span>
        </div>
        <div class="meta-item">
          <span class="meta-key">Analysis file</span>
          <span class="meta-val">{analysis_file}</span>
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
    <div class="stats">{stats_html}</div>
    <div class="filter-bar">
      <span class="filter-bar-label">Filter:</span>
      {filter_btns}
    </div>
    <div id="article-list">{cards_html}</div>
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


# ---------------------------------------------------------------------------
# Vector store report
# ---------------------------------------------------------------------------

def generate_html_vector_store_report(report: dict) -> str:
    """Return a self-contained HTML string for a vector store summary."""
    articles: list[dict] = report.get("articles", [])
    total_records = report.get("total_records", 0)
    unique_docs = report.get("unique_documents", len(articles))
    db_size_mb = report.get("db_size_mb", 0.0)
    embedding_model = _html.escape(report.get("embedding_model") or "—")
    embedding_provider = _html.escape(report.get("embedding_provider") or "—")
    last_updated = _html.escape(report.get("last_updated") or "—")

    rows_html = ""
    for art in articles:
        fn = _html.escape(art.get("filename", "unknown"))
        chunks = art.get("chunk_count", 0)
        vectorized_at = _html.escape(art.get("vectorized_at") or "—")
        model = _html.escape(art.get("embedding_model") or "—")
        rows_html += (
            f'<tr>'
            f'<td class="fn-cell">{fn}</td>'
            f'<td class="num-cell">{chunks}</td>'
            f'<td class="date-cell">{vectorized_at}</td>'
            f'<td class="model-cell">{model}</td>'
            f'</tr>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>lutz &mdash; Vector Store Summary</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f8fafc; color: #1e293b; line-height: 1.6;
    }}
    .container {{ max-width: 900px; margin: 0 auto; padding: 2rem 1rem 4rem; }}
    .report-header {{
      background: #1e293b; color: #f1f5f9;
      border-radius: 12px; padding: 2rem; margin-bottom: 2rem;
    }}
    .report-header h1 {{
      font-size: 1.5rem; font-weight: 700;
      display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem;
    }}
    .report-header h1 .logo {{ color: #38bdf8; }}
    .meta-grid {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 0.75rem; font-size: 0.85rem;
    }}
    .meta-item {{ display: flex; flex-direction: column; gap: 0.15rem; }}
    .meta-key {{ color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }}
    .meta-val {{ color: #e2e8f0; word-break: break-all; }}
    .stats {{ display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 2rem; }}
    .stat-card {{
      flex: 1 1 120px; border-radius: 8px; padding: 1rem;
      background: #fff; border: 1px solid #e2e8f0;
      display: flex; flex-direction: column; gap: 0.25rem;
    }}
    .stat-label {{ font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; }}
    .stat-count {{ font-size: 2rem; font-weight: 700; line-height: 1; color: #1e293b; }}
    .stat-sub {{ font-size: 0.85rem; color: #94a3b8; }}
    .section-title {{
      font-size: 1rem; font-weight: 600; color: #1e293b;
      margin-bottom: 0.75rem;
    }}
    .search-bar {{
      width: 100%; padding: 0.5rem 0.75rem;
      border: 1px solid #cbd5e1; border-radius: 8px;
      font-size: 0.9rem; margin-bottom: 1rem; outline: none;
    }}
    .search-bar:focus {{ border-color: #94a3b8; }}
    table {{
      width: 100%; border-collapse: collapse;
      background: #fff; border-radius: 10px;
      overflow: hidden; border: 1px solid #e2e8f0;
    }}
    thead th {{
      text-align: left; padding: 0.75rem 1rem;
      background: #f1f5f9; color: #475569;
      font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em;
      border-bottom: 1px solid #e2e8f0;
    }}
    tbody tr {{ transition: background 0.1s; }}
    tbody tr:hover {{ background: #f8fafc; }}
    tbody tr.hidden {{ display: none; }}
    tbody td {{ padding: 0.65rem 1rem; border-bottom: 1px solid #f1f5f9; font-size: 0.875rem; }}
    tbody tr:last-child td {{ border-bottom: none; }}
    .fn-cell {{ font-weight: 500; word-break: break-all; }}
    .num-cell {{ white-space: nowrap; color: #64748b; text-align: right; width: 80px; }}
    .date-cell {{ white-space: nowrap; color: #64748b; width: 180px; }}
    .model-cell {{ color: #64748b; }}
    #no-results {{
      text-align: center; padding: 3rem;
      color: #94a3b8; font-size: 0.95rem; display: none;
    }}
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
    <header class="report-header">
      <h1><span class="logo">lutz</span> &mdash; Vector Store Summary</h1>
      <div class="meta-grid">
        <div class="meta-item">
          <span class="meta-key">Last updated</span>
          <span class="meta-val">{last_updated}</span>
        </div>
        <div class="meta-item">
          <span class="meta-key">Embedding model</span>
          <span class="meta-val">{embedding_model}</span>
        </div>
        <div class="meta-item">
          <span class="meta-key">Provider</span>
          <span class="meta-val">{embedding_provider}</span>
        </div>
        <div class="meta-item">
          <span class="meta-key">DB size</span>
          <span class="meta-val">{db_size_mb:.3f} MB</span>
        </div>
      </div>
    </header>
    <div class="stats">
      <div class="stat-card">
        <span class="stat-label">Documents</span>
        <span class="stat-count">{unique_docs}</span>
        <span class="stat-sub">unique files</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Chunks</span>
        <span class="stat-count">{total_records:,}</span>
        <span class="stat-sub">total vectors</span>
      </div>
    </div>
    <div class="section-title">Indexed articles</div>
    <input
      class="search-bar" type="search"
      placeholder="Filter by filename…"
      oninput="filterTable(this.value)"
    >
    <table>
      <thead>
        <tr>
          <th>Filename</th>
          <th style="text-align:right">Chunks</th>
          <th>Vectorized at</th>
          <th>Model</th>
        </tr>
      </thead>
      <tbody id="article-rows">
        {rows_html}
      </tbody>
    </table>
    <div id="no-results">No articles match this filter.</div>
    <footer class="footer">
      Generated by <a href="https://github.com/jooguilhermesc/lutz">lutz</a>
    </footer>
  </div>
  <script>
    function filterTable(q) {{
      const lower = q.toLowerCase();
      let visible = 0;
      document.querySelectorAll('#article-rows tr').forEach(row => {{
        const fn = row.querySelector('.fn-cell');
        const show = !fn || fn.textContent.toLowerCase().includes(lower);
        row.classList.toggle('hidden', !show);
        if (show) visible++;
      }});
      document.getElementById('no-results').style.display = visible === 0 ? 'block' : 'none';
    }}
  </script>
</body>
</html>
"""
