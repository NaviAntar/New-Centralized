"""
charts.py — semua chart portal.

Aturan warna (mengikuti disiplin repo FTE, supaya tidak ada dua sistem warna
yang bersaing dalam satu layar):
    - membandingkan SITE   -> theme.SITE_COLORS
    - membandingkan TAHAP  -> theme.STAGE_SHADES (satu ramp; tahap itu urutan)
    - menyatakan HASIL     -> theme.RESULT_COLORS / theme.SLA_COLORS

Tidak ada hex yang ditulis langsung di file ini. Ganti token di theme.py,
seluruh chart ikut berubah.
"""
from __future__ import annotations

import plotly.graph_objects as go

from theme import BRAND, NEUTRAL, RESULT_COLORS, RESULT_LABEL, STAGE_SHADES, STATUS

FONT = dict(family="Public Sans, Segoe UI, sans-serif", size=11, color=NEUTRAL["text"])
HOVER = dict(
    bgcolor=BRAND["navy"], bordercolor=BRAND["navy"],
    font=dict(family="Public Sans, Segoe UI, sans-serif", color="#FFFFFF", size=11.5),
)


def _layout(height: int, **kw) -> dict:
    """Layout bersama: latar transparan supaya chart menyatu dengan kartu putih."""
    base = dict(
        height=height,
        margin=dict(l=6, r=6, t=6, b=6),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=FONT,
        hoverlabel=HOVER,
        showlegend=False,
        dragmode=False,
    )
    base.update(kw)
    return base


def num(x, dec: int = 0) -> str:
    """Format angka gaya Indonesia: titik ribuan, koma desimal."""
    try:
        s = f"{float(x):,.{dec}f}"
    except (TypeError, ValueError):
        return "—"
    return s.replace(",", " ").replace(".", ",").replace(" ", ".")


def _empty(height: int, msg: str = "Belum ada data") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False,
                       font=dict(color=NEUTRAL["text_soft"], size=12))
    fig.update_layout(**_layout(height, xaxis=dict(visible=False), yaxis=dict(visible=False)))
    return fig


def funnel_bars(funnel_df, height: int = 330) -> go.Figure:
    """Funnel mendatar. Panjang batang = kandidat yang minimal sampai tahap itu."""
    if funnel_df is None or funnel_df.empty:
        return _empty(height)

    d = funnel_df.iloc[::-1]  # Plotly menggambar dari bawah
    colors = [STAGE_SHADES.get(s, BRAND["orange"]) for s in d["stage"]]
    hover = [
        f"<b>{r.stage}</b><br>{num(r.n)} kandidat"
        + (f"<br>{num(r.conv_pct, 1)}% dari tahap sebelumnya" if r.conv_pct == r.conv_pct else "")
        + (f"<br>{num(r.of_base_pct, 1)}% dari screening" if r.of_base_pct == r.of_base_pct else "")
        for r in d.itertuples()
    ]
    fig = go.Figure(go.Bar(
        x=d["n"], y=d["stage"], orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=[num(v) for v in d["n"]],
        textposition="outside",
        textfont=dict(size=11, color=NEUTRAL["text"]),
        hovertext=hover, hovertemplate="%{hovertext}<extra></extra>",
        cliponaxis=False,
    ))
    fig.update_layout(**_layout(
        height,
        xaxis=dict(visible=False, range=[0, d["n"].max() * 1.16]),
        yaxis=dict(showgrid=False, tickfont=dict(size=11.5)),
        bargap=0.32,
    ))
    return fig


def trend_line(trend_df, height: int = 280, budget: float | None = None) -> go.Figure:
    """Tren median time-to-hire per bulan, dengan garis budget sebagai acuan."""
    if trend_df is None or trend_df.empty:
        return _empty(height)

    x = [str(p) for p in trend_df["period"]]
    fig = go.Figure()
    if budget:
        fig.add_hline(y=budget, line=dict(color=NEUTRAL["text_soft"], width=1, dash="dot"),
                      annotation_text=f"budget {num(budget)} hari",
                      annotation_font=dict(size=10, color=NEUTRAL["text_soft"]),
                      annotation_position="top left")
    fig.add_trace(go.Scatter(
        x=x, y=trend_df["median_lt"], mode="lines+markers",
        line=dict(color=BRAND["orange"], width=2.5, shape="spline", smoothing=0.5),
        marker=dict(size=7, color=BRAND["orange"], line=dict(width=2, color="#FFFFFF")),
        fill="tozeroy", fillcolor="rgba(255,104,5,0.09)",
        hovertext=[f"<b>{p}</b><br>median {num(m)} hari kerja<br>{num(n)} hire"
                   for p, m, n in zip(x, trend_df["median_lt"], trend_df["n"])],
        hovertemplate="%{hovertext}<extra></extra>",
    ))
    fig.update_layout(**_layout(
        height,
        xaxis=dict(showgrid=False, tickfont=dict(size=10.5)),
        yaxis=dict(showgrid=True, gridcolor=NEUTRAL["border_soft"], zeroline=False,
                   tickfont=dict(size=10.5), title=dict(text="hari kerja", font=dict(size=10))),
    ))
    return fig


def status_donut(counts: dict, height: int = 240) -> go.Figure:
    """Komposisi status kandidat: Hired / On Progress / Failed."""
    codes = [k for k, v in counts.items() if v]
    if not codes:
        return _empty(height)
    values = [counts[k] for k in codes]
    # Kunci dict adalah KODE status (CLOSE/OPEN/FAILED); labelnya diterjemahkan
    # di sini supaya warna dan teks tidak pernah lepas satu sama lain.
    labels = [RESULT_LABEL.get(k, k) for k in codes]
    colors = [RESULT_COLORS.get(k, NEUTRAL["text_soft"]) for k in codes]
    total = sum(values)
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.62,
        marker=dict(colors=colors, line=dict(color="#FFFFFF", width=2)),
        textinfo="none", sort=False, direction="clockwise",
        hovertext=[f"<b>{l}</b><br>{num(v)} ({v / total * 100:.1f}%)"
                   for l, v in zip(labels, values)],
        hovertemplate="%{hovertext}<extra></extra>",
    ))
    fig.add_annotation(text=f"<b>{num(total)}</b><br><span style='font-size:10px'>kandidat</span>",
                       showarrow=False, font=dict(size=19, color=NEUTRAL["text"]))
    fig.update_layout(**_layout(height))
    return fig


def source_bars(src_df, height: int = 240) -> go.Figure:
    """Hire rate per sumber CV — batang tunggal, diurutkan dari yang terbaik."""
    if src_df is None or src_df.empty:
        return _empty(height)
    d = src_df.iloc[::-1]
    best = d["rate"].max()
    colors = [STATUS["good"] if r >= best * 0.8 else BRAND["orange"] if r >= best * 0.4
              else NEUTRAL["text_soft"] for r in d["rate"]]
    fig = go.Figure(go.Bar(
        x=d["rate"], y=d["source_cv"], orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{num(r, 1)}%" for r in d["rate"]],
        textposition="outside", textfont=dict(size=11),
        hovertext=[f"<b>{s}</b><br>{num(h)} hire dari {num(n)} kandidat"
                   for s, h, n in zip(d["source_cv"], d["hired"], d["n"])],
        hovertemplate="%{hovertext}<extra></extra>",
        cliponaxis=False,
    ))
    fig.update_layout(**_layout(
        height,
        xaxis=dict(visible=False, range=[0, best * 1.25]),
        yaxis=dict(showgrid=False, tickfont=dict(size=11.5)),
        bargap=0.35,
    ))
    return fig
