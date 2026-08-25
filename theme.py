"""
Design system — FTE Calculator PT Darma Henwa (v6, "Looker light").

Arah desain (dipilih user): TERANG, mengikuti nuansa dashboard Looker Studio
PTDH — header band gradasi orange dengan logo putih, kartu putih di atas
background abu terang, judul kartu berwarna sesuai aksen, dan strip navy
gelap untuk legenda/readout.

Tiga hal yang diperbaiki dari v5:

1.  KARTU SEKARANG BENAR-BENAR MEMBUNGKUS ISINYA.
    v5 membuka `<div class="ptdh-card">` lewat st.markdown lalu menutupnya
    di st.markdown berikutnya. Itu tidak pernah bekerja: Streamlit merender
    tiap markdown di container terpisah, jadi browser menutup div-nya
    sendiri dan chart jatuh DI LUAR kartu (kartu tampil sebagai strip putih
    kosong). Sekarang kartu dibangun dari `st.container(key=...)` +
    selector `div[class*="st-key-card_"]`, jadi apa pun yang dirender di
    dalam blok `with theme.card(...)` benar-benar berada di dalam kartu.

2.  WARNA ROLE DIPISAH BERDASARKAN HUE, BUKAN CUMA LIGHTNESS.
    v5 memakai orange #FF6805, salmon #FF9182, dan kuning-tua #E0A400 —
    ketiganya hue 15–45°, jadi Mechanic/Welder/Electrician tampak seperti
    satu warna yang buram. Sekarang: Mechanic = orange brand (populasi
    terbesar, layak dapat warna brand), Electrician = kuning listrik,
    Welder = biru-teal (warna busur las). Ketiganya masih dalam keluarga
    swatch PTDH (orange primary, yellow & steel-blue secondary).

3.  ANGKA MEMAKAI TABULAR NUMERALS.
    Kolom angka pada tabel/KPI tidak lagi "goyang" saat nilainya berubah.

Pembagian tugas warna dibuat tegas supaya tidak ada dua sistem warna yang
bersaing dalam satu layar:
    - Chart yang membandingkan SITE   -> pakai SITE_COLORS (hue berbeda).
    - Chart yang membandingkan TAHAP  -> pakai STAGE_SHADES (1 ramp orange),
      karena tahap seleksi itu urutan, bukan kategori.
    - Chart/badge yang menyatakan HASIL -> pakai RESULT_COLORS / SLA_COLORS.
"""
from __future__ import annotations

import base64
import colorsys
import html
from contextlib import contextmanager
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
IMAGES_DIR = ASSETS_DIR / "images"

# ---------------------------------------------------------------------------
# Token warna
# ---------------------------------------------------------------------------
BRAND = {
    "orange": "#FF6805",     # primary swatch PTDH
    "orange_deep": "#D94E00",
    "header_l": "#FF8A0D",   # ujung kiri gradasi header — dari sampel referensi
    "amber": "#FFC21A",      # ujung kanan gradasi header — dari sampel referensi
    "navy": "#101B2D",       # strip legenda & readout gelap
}

# Satu hue per SITE. Jarak hue-nya sengaja lebar supaya tetap terbaca saat
# dicetak hitam-putih maupun oleh penderita deuteranopia. HO memakai orange
# brand karena itu kantor pusat; site tambang memakai hue lain.
SITE_COLORS = {
    "HO": "#FF6805",     # orange brand — HO & BPN
    "BCP": "#0E7C86",    # teal — Bengalon
    "KCP": "#3D5AFE",    # biru — Kintap
    "ACP": "#12A150",    # hijau — Asam-Asam
    "SSCP": "#98A1AF",   # abu — belum aktif
}

STATUS = {
    "good": "#12A150",
    "warn": "#F5A524",
    "bad": "#E5484D",
}

# Warna hasil akhir kandidat. Mengambil dari STATUS supaya arti "hijau = baik"
# konsisten di seluruh aplikasi — badge, tabel, dan chart memakai peta ini.
RESULT_COLORS = {
    "CLOSE": STATUS["good"],    # onboarding — hire berhasil
    "OPEN": STATUS["warn"],     # masih berjalan
    "FAILED": STATUS["bad"],
    "HOLD": "#98A1AF",
    "WITHDRAWN": "#67707F",
}

RESULT_LABEL = {
    "CLOSE": "Hired",
    "OPEN": "On Progress",
    "FAILED": "Failed",
    "HOLD": "Hold",
    "WITHDRAWN": "Withdrawn",
}

# Status SLA per tahap. Dipakai chip di tabel tahap dan heatmap Overview.
SLA_COLORS = {
    "Ontime": STATUS["good"],
    "Late": STATUS["bad"],
    "Running": STATUS["warn"],
    "": "#98A1AF",
}

NEUTRAL = {
    "bg": "#F1F3F7",
    "card": "#FFFFFF",
    "border": "#E3E7EF",
    "border_soft": "#EEF1F6",
    "text": "#111827",
    "text_muted": "#67707F",
    "text_soft": "#98A1AF",
    "wash": "#F7F9FC",
}

FONT_DISPLAY = "'Archivo', 'Segoe UI', sans-serif"
FONT_BODY = "'Public Sans', 'Segoe UI', sans-serif"

# Urutan tahap seleksi. SATU-SATUNYA tempat urutan ini didefinisikan — funnel,
# tabel tahap, progress bar, dan heatmap SLA semuanya membacanya dari sini.
# Menambah tahap baru cukup disisipkan di list ini.
STAGE_ORDER = [
    "PRF Approval",
    "Screening CV",
    "Interview HR",
    "Interview User",
    "Technical Test",
    "Psychotest",
    "Offering",
    "MCU",
    "Review MCU",
    "FU MCU",
    "One Month Notice",
    "Onboarding",
]

# Tahap yang dilalui SEMUA kandidat. Technical Test (hanya Non Staff) dan
# Psychotest (sering dilewat) sengaja tidak masuk: keduanya cabang opsional,
# dan memasukkannya ke funnel membuat angka tahap sesudahnya terbaca seolah
# lebih banyak orang mengerjakannya daripada kenyataan.
MAIN_FUNNEL = [
    "Screening CV",
    "Interview HR",
    "Interview User",
    "Offering",
    "MCU",
    "Review MCU",
    "FU MCU",
    "One Month Notice",
    "Onboarding",
]

OPTIONAL_STAGES = ["Technical Test", "Psychotest"]


# ---------------------------------------------------------------------------
# Shade generator — gradasi natural dari satu warna dasar
# ---------------------------------------------------------------------------
def _hex_to_hls(hex_color: str):
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def _hls_to_hex(h, l, s) -> str:
    l = min(max(l, 0.0), 1.0)
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def shades_from_base(hex_color: str, levels=("M1", "M2", "M3")) -> dict:
    """Level pertama paling gelap (senior), terakhir paling terang (junior).

    Arahnya dibalik dibanding v5: di semua chart, nilai yang "lebih berat"
    (M1 = paling mahal, paling senior) sekarang selalu jadi warna paling
    pekat, jadi bobot visualnya sejalan dengan bobot maknanya.
    """
    h, l, s = _hex_to_hls(hex_color)
    n = len(levels)
    out = {}
    for i, lvl in enumerate(levels):
        if n == 1:
            out[lvl] = hex_color
            continue
        t = i / (n - 1)
        if t <= 0.5:
            dt = (0.5 - t) / 0.5
            out[lvl] = _hls_to_hex(h, max(l - dt * 0.16, 0.16), s * (1 - dt * 0.08))
        else:
            dt = (t - 0.5) / 0.5
            out[lvl] = _hls_to_hex(h, min(l + dt * 0.30, 0.90), s * (1 - dt * 0.18))
    return out


# Gradasi satu-hue untuk funnel tahap. Funnel itu URUTAN, bukan kategori —
# karena itu satu hue yang memudar, bukan 11 warna berbeda.
STAGE_SHADES = shades_from_base(BRAND["orange"], levels=tuple(STAGE_ORDER))


def tint(hex_color: str, amount: float = 0.88) -> str:
    """Campur warna dengan putih. amount=0.88 -> 88% putih (latar ikon/chip)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    r = round(r + (255 - r) * amount)
    g = round(g + (255 - g) * amount)
    b = round(b + (255 - b) * amount)
    return "#{:02X}{:02X}{:02X}".format(r, g, b)


# ---------------------------------------------------------------------------
# Asset helpers
# ---------------------------------------------------------------------------
def _data_uri(path: Path) -> str | None:
    if not path.is_file():
        return None
    ext = path.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{b64}"


def image_uri(name: str) -> str | None:
    return _data_uri(IMAGES_DIR / name)


def icon_svg(name: str, size: int = 16, color: str | None = None) -> str:
    """Inline <svg> dari assets/icons/<n>.svg, warnanya ikut currentColor."""
    import re

    raw = _ICON_CACHE.get(name)
    if raw is None:
        p = ICONS_DIR / f"{name}.svg"
        if not p.is_file():
            return ""
        raw = p.read_text(encoding="utf-8")
        _ICON_CACHE[name] = raw
    svg = re.sub(r'stroke="#[0-9a-fA-F]{3,6}"', 'stroke="currentColor"', raw)
    svg = re.sub(r'fill="#[0-9a-fA-F]{3,6}"', 'fill="currentColor"', svg)
    svg = re.sub(r'width="\d+(px)?"', f'width="{size}"', svg)
    svg = re.sub(r'height="\d+(px)?"', f'height="{size}"', svg)
    style = "display:inline-flex;align-items:center;"
    if color:
        style += f"color:{color};"
    return f'<span style="{style}">{svg}</span>'


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
def inject_css():
    import streamlit as st

    # Ikon "i" dipakai sebagai background-image tombol popover: Streamlit tidak
    # mengizinkan elemen <img> di dalam label tombol, jadi labelnya dikosongkan
    # dan ikonnya digambar lewat CSS.
    info_uri = image_uri("info.png") or ""

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700;800&family=Public+Sans:wght@400;500;600;700;800&display=swap');

        :root {{
            --dh-orange: {BRAND['orange']};
            --dh-orange-deep: {BRAND['orange_deep']};
            --dh-amber: {BRAND['amber']};
            --dh-navy: {BRAND['navy']};
            --dh-border: {NEUTRAL['border']};
            --dh-text: {NEUTRAL['text']};
            --dh-muted: {NEUTRAL['text_muted']};
        }}

        html, body, .stApp, [class*="css"] {{ font-family: {FONT_BODY}; }}
        .stApp {{ background: {NEUTRAL['bg']}; }}
        h1, h2, h3, h4, h5 {{ font-family: {FONT_DISPLAY}; color: {NEUTRAL['text']}; }}

        /* full-bleed: dashboard Looker memakai seluruh lebar layar */
        .block-container {{
            padding: 0.45rem 1.4rem 2rem 1.4rem !important;
            max-width: 100% !important;
        }}
        header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
        #MainMenu, footer {{ visibility: hidden; }}
        div[data-testid="stDecoration"] {{ display: none; }}

        /* angka tidak goyang saat berubah */
        .dh-num, .dh-table td, .kpi .value, .kpi .sub {{ font-variant-numeric: tabular-nums; }}

        /* =====================================================
           HEADER BAND (orange gradient, logo putih) — signature
           ===================================================== */
        /* Gradasi v6.1: ramp VERTIKAL monoton amber -> orange -> orange pekat.
           Versi sebelumnya (#FF8A0D 0% -> #FF6805 45% -> #FFC21A 100%) naik-turun
           lightness-nya, jadi terlihat ada "pita" tegas di tengah band. Sekarang
           enam stop dengan jarak rapat di area transisi supaya perpindahan
           warnanya halus, ditambah highlight radial tipis di kiri-atas seperti
           header referensi. */
        .dh-band {{
            background:
                radial-gradient(120% 150% at 12% 0%, rgba(255,255,255,.22) 0%, rgba(255,255,255,0) 55%),
                linear-gradient(180deg,
                    {BRAND['amber']} 0%,
                    #FFB015 16%,
                    #FF9D10 32%,
                    #FF8A0D 48%,
                    #FF7908 66%,
                    {BRAND['orange']} 84%,
                    #F25F02 100%);
            border-radius: 14px;
            padding: 20px 22px;
            min-height: 84px;
            display: flex; align-items: center; gap: 18px;
            flex-wrap: wrap;
            margin-bottom: 14px;
            box-shadow: 0 6px 18px -8px rgba(217,78,0,.55);
        }}
        .dh-band .logo {{ height: 46px; width: auto; flex: 0 0 auto; }}
        .dh-band .rule {{ width: 1px; height: 40px; background: rgba(255,255,255,.45); flex: 0 0 auto; }}
        /* basis 260px: kalau sisa lebar kurang dari itu, .heading TURUN ke baris
           berikutnya alih-alih diperas sampai satu huruf per baris. Sebelumnya
           .chips memakai flex 0 0 auto (tidak pernah menyusut) sementara
           .heading boleh menyusut tanpa batas — di layar HP chip "Site ACP" +
           "Competency factor 0,60" menghabiskan seluruh baris dan judulnya
           tersisa selebar satu karakter. */
        .dh-band .heading {{ flex: 1 1 260px; min-width: 0; }}
        .dh-band .heading .title {{
            font-family: {FONT_DISPLAY}; font-weight: 800; font-size: 21px;
            color: #fff; line-height: 1.15; letter-spacing: -.01em;
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .dh-band .heading .sub {{
            font-size: 11.5px; color: rgba(255,255,255,.85); font-weight: 500; margin-top: 1px;
        }}
        .dh-band .chips {{
            display: flex; gap: 8px; flex: 0 1 auto; flex-wrap: wrap; justify-content: flex-end;
            min-width: 0;
        }}
        .dh-band .chip {{
            background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.35);
            border-radius: 999px; padding: 5px 12px; color: #fff;
            font-size: 11.5px; font-weight: 600; backdrop-filter: blur(2px);
        }}
        .dh-band .chip b {{ font-weight: 800; }}

        /* Layar sempit (HP): band ditumpuk vertikal. Logo + judul satu baris,
           chip pindah ke baris bawah dan rata kiri. Judul boleh membungkus
           penuh karena tidak ada lagi yang berebut lebar dengannya. */
        @media (max-width: 720px) {{
            .dh-band {{
                padding: 15px 16px; gap: 12px; min-height: 0;
                align-items: flex-start;
            }}
            .dh-band .logo {{ height: 36px; }}
            .dh-band .rule {{ height: 32px; }}
            .dh-band .heading {{ flex: 1 1 140px; }}
            .dh-band .heading .title {{
                font-size: 17px; white-space: normal; overflow: visible; text-overflow: clip;
            }}
            .dh-band .heading .sub {{ font-size: 11px; margin-top: 3px; }}
            .dh-band .chips {{
                flex: 1 1 100%; justify-content: flex-start; gap: 6px;
            }}
            .dh-band .chip {{ font-size: 11px; padding: 4px 10px; }}
        }}

        /* strip navy: legenda / catatan skala */
        .dh-strip {{
            background: {BRAND['navy']}; border-radius: 10px;
            padding: 8px 16px; margin-bottom: 14px;
            display: flex; align-items: center; justify-content: space-between;
            gap: 14px; flex-wrap: wrap;
        }}
        .dh-strip .left {{ color: #C3CBD9; font-size: 11.5px; font-weight: 600; }}
        .dh-strip .items {{ display: flex; gap: 16px; flex-wrap: wrap; }}
        .dh-strip .item {{
            display: inline-flex; align-items: center; gap: 6px;
            color: #E8ECF3; font-size: 11.5px; font-weight: 600;
        }}
        .dh-strip .item .sw {{ width: 9px; height: 9px; border-radius: 50%; }}

        /* =====================================================
           KPI CARD
           ===================================================== */
        .kpi {{
            background: {NEUTRAL['card']};
            border: 1px solid {NEUTRAL['border']};
            border-top: 3px solid var(--accent, {BRAND['orange']});
            border-radius: 12px;
            padding: 11px 13px;
            display: flex; align-items: center; gap: 11px;
            box-shadow: 0 1px 2px rgba(17,24,39,.05);
            min-height: 88px;
        }}
        .kpi .ico {{
            width: 42px; height: 42px; border-radius: 50%;
            background: var(--tint, #FFF0E6);
            display: flex; align-items: center; justify-content: center;
            flex: 0 0 auto;
        }}
        .kpi .ico img {{ width: 24px; height: 24px; object-fit: contain; }}
        .kpi .ico span {{ font-size: 19px; line-height: 1; }}
        .kpi .body {{ min-width: 0; }}
        .kpi .label {{
            font-size: 10px; font-weight: 700; letter-spacing: .07em;
            text-transform: uppercase; color: {NEUTRAL['text_muted']};
        }}
        .kpi .value {{
            font-family: {FONT_DISPLAY}; font-size: var(--vsize, 25px); font-weight: 800;
            color: {NEUTRAL['text']}; line-height: 1.1; letter-spacing: -.02em;
            white-space: nowrap;
        }}
        .kpi .value small {{ font-size: 13px; font-weight: 700; color: {NEUTRAL['text_muted']}; }}
        .kpi .sub {{
            font-size: 10.5px; color: {NEUTRAL['text_muted']}; margin-top: 2px;
            white-space: normal; line-height: 1.35; overflow-wrap: break-word;
        }}
        .kpi .sub b {{ color: {NEUTRAL['text']}; font-weight: 700; }}

        /* =====================================================
           CARD — dibangun dari st.container(key="card_*") supaya
           isinya benar-benar terbungkus (lihat docstring file)
           ===================================================== */
        /* Streamlit meregangkan kartu di dalam st.columns supaya setinggi
           kolom TERTINGGI dalam baris (default flex align-items:stretch di
           stHorizontalBlock). Itu penyebab ruang kosong besar di bawah kartu
           yang isinya lebih pendek dari kartu sebelahnya — dikeluhkan di
           mode Kalkulator (kartu Parameter) dan mode Basecase (kartu
           Persebaran M1-M3). Kartu dipaksa mengikuti tinggi isinya sendiri. */
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            align-items: stretch !important;
        }}
        div[class*="st-key-card_"] {{
            background: {NEUTRAL['card']};
            border: 1px solid {NEUTRAL['border']};
            border-radius: 12px;
            padding: 14px 16px 14px 16px;
            box-shadow: 0 1px 2px rgba(17,24,39,.05);
            height: auto !important;
            flex-grow: 0 !important;
            align-self: flex-start !important;
            width: 100%;
        }}
        /* Kartu berpasangan kiri-kanan: tingginya HARUS ditentukan oleh yang
           tertinggi, bukan oleh tinggi chart yang dipatok manual. Jumlah baris
           tabel berubah-ubah per site, jadi penyetelan tinggi chart satu per
           satu selalu meleset begitu datanya ganti. Di sini kartunya dibiarkan
           meregang mengikuti tinggi baris, lalu legend-nya didorong ke dasar
           kartu supaya ruang kosongnya jatuh di tengah, bukan menggantung di
           bawah. */
        div[class*="st-key-card_level_donut"],
        div[class*="st-key-card_staff_donut"],
        div[class*="st-key-card_cost_ns_donut"],
        div[class*="st-key-card_cost_st_donut"],
        div[class*="st-key-card_total_section"],
        div[class*="st-key-card_staff_table"],
        div[class*="st-key-card_cost_ns_table"],
        div[class*="st-key-card_cost_st_table"],
        div[class*="st-key-card_total_head"],
        div[class*="st-key-card_total_cost"] {{
            align-self: stretch !important;
            height: 100% !important;
            flex-grow: 1 !important;
        }}
        /* Streamlit membungkus tiap kartu dalam stLayoutWrapper. Wrapper itu
           adalah flex item di kolom, dan tanpa flex-grow ia hanya setinggi
           isinya — jadi `height:100%` pada kartunya sendiri tidak berpengaruh.
           :has() dipakai untuk menyasar wrapper lewat kartu di dalamnya. */
        div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-card_level_donut"]),
        div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-card_staff_donut"]),
        div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-card_cost_ns_donut"]),
        div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-card_cost_st_donut"]),
        div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-card_total_section"]),
        div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-card_staff_table"]),
        div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-card_cost_ns_table"]),
        div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-card_cost_st_table"]),
        div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-card_total_head"]),
        div[data-testid="stLayoutWrapper"]:has(> div[class*="st-key-card_total_cost"]) {{
            flex: 1 1 auto !important;
            align-self: stretch !important;
        }}

        div[class*="st-key-card_level_donut"] > div[data-testid="stVerticalBlock"],
        div[class*="st-key-card_staff_donut"] > div[data-testid="stVerticalBlock"],
        div[class*="st-key-card_cost_ns_donut"] > div[data-testid="stVerticalBlock"],
        div[class*="st-key-card_cost_st_donut"] > div[data-testid="stVerticalBlock"],
        div[class*="st-key-card_total_head"] > div[data-testid="stVerticalBlock"],
        div[class*="st-key-card_total_cost"] > div[data-testid="stVerticalBlock"] {{
            height: 100%;
        }}
        div[class*="st-key-card_level_donut"] > div[data-testid="stVerticalBlock"] > div:last-child,
        div[class*="st-key-card_staff_donut"] > div[data-testid="stVerticalBlock"] > div:last-child,
        div[class*="st-key-card_cost_ns_donut"] > div[data-testid="stVerticalBlock"] > div:last-child,
        div[class*="st-key-card_cost_st_donut"] > div[data-testid="stVerticalBlock"] > div:last-child,
        div[class*="st-key-card_total_head"] > div[data-testid="stVerticalBlock"] > div:last-child,
        div[class*="st-key-card_total_cost"] > div[data-testid="stVerticalBlock"] > div:last-child {{
            margin-top: auto;
        }}

        div[class*="st-key-card_"] {{ gap: 0.35rem !important; }}
        div[class*="st-key-card_"] div[data-testid="stVerticalBlock"] {{ gap: 0.35rem !important; }}
        div[class*="st-key-card_"] div[data-testid="stCaptionContainer"] p {{ margin-bottom: 0; }}

        /* Jarak judul kartu ke isinya dilebarkan: sebelumnya chart menempel
           persis di bawah garis judul sehingga kartu terasa sesak. */
        .dh-card-head {{
            display: flex; align-items: center; gap: 8px;
            padding-bottom: 9px; margin-bottom: 12px;
            border-bottom: 1px solid {NEUTRAL['border_soft']};
        }}
        .dh-card-head .bar {{
            width: 3px; height: 15px; border-radius: 2px;
            background: var(--accent, {BRAND['orange']}); flex: 0 0 auto;
        }}
        .dh-card-head .t {{
            font-family: {FONT_DISPLAY}; font-weight: 700; font-size: 13px;
            color: var(--accent, {BRAND['orange']}); letter-spacing: -.005em;
        }}
        .dh-card-head .s {{
            font-size: 11px; color: {NEUTRAL['text_soft']}; font-weight: 500;
            margin-left: auto; text-align: right;
        }}

        /* =====================================================
           SIDEBAR — terang, aksen orange
           ===================================================== */
        section[data-testid="stSidebar"] {{
            background: {NEUTRAL['card']} !important;
            border-right: 1px solid {NEUTRAL['border']};
            min-width: 268px !important;
        }}
        section[data-testid="stSidebar"] .dh-side-brand {{
            display: flex; align-items: center; gap: 10px;
            padding: 2px 0 14px 0; margin-bottom: 8px;
            border-bottom: 1px solid {NEUTRAL['border_soft']};
        }}
        section[data-testid="stSidebar"] .dh-side-brand .mark {{
            width: 34px; height: 34px; border-radius: 9px; flex: 0 0 auto;
            background: linear-gradient(135deg, {BRAND['orange_deep']}, {BRAND['amber']});
            display: flex; align-items: center; justify-content: center;
        }}
        section[data-testid="stSidebar"] .dh-side-brand .mark img {{ width: 22px; height: 22px; }}
        section[data-testid="stSidebar"] .dh-side-brand .title {{
            font-family: {FONT_DISPLAY}; font-weight: 800; font-size: 14px; color: {NEUTRAL['text']};
        }}
        section[data-testid="stSidebar"] .dh-side-brand .subtitle {{
            font-size: 10.5px; color: {NEUTRAL['text_muted']};
        }}
        .dh-side-label {{
            font-size: 9.5px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase;
            color: {NEUTRAL['text_soft']}; margin: 14px 0 6px 0;
        }}
        section[data-testid="stSidebar"] label p {{
            font-size: 10.5px !important; font-weight: 700 !important;
            text-transform: uppercase; letter-spacing: .04em;
            color: {NEUTRAL['text_muted']} !important;
        }}

        /* nav pill */
        div[class*="st-key-nav_"] button {{
            background: transparent !important;
            color: {NEUTRAL['text_muted']} !important;
            border: 1px solid {NEUTRAL['border']} !important;
            border-radius: 9px !important;
            font-weight: 600 !important; font-size: 13px !important;
            justify-content: flex-start !important; text-align: left !important;
            height: 40px; padding-left: 12px !important;
        }}
        div[class*="st-key-nav_"] button:hover {{
            border-color: {BRAND['orange']} !important; color: {BRAND['orange']} !important;
            background: {tint(BRAND['orange'], .94)} !important;
        }}
        div[class*="st-key-nav_"] button[kind="primary"] {{
            background: linear-gradient(135deg, {BRAND['orange_deep']}, {BRAND['orange']}) !important;
            border-color: transparent !important; color: #fff !important;
            box-shadow: 0 4px 10px -4px rgba(217,78,0,.6);
        }}

        /* Tombol kartu landing. Sebelumnya tidak punya aturan sendiri, jadi
           tombol type="primary" ("Open calculator") memakai warna primary
           bawaan Streamlit yang merah — bertabrakan dengan palet orange. */
        div[class*="st-key-go_"] {{ margin-top: 10px; }}
        div[class*="st-key-go_"] button {{
            border-radius: 10px !important; height: 44px;
            font-weight: 700 !important; font-size: 13px !important;
            background: {NEUTRAL['card']} !important;
            color: {NEUTRAL['text']} !important;
            border: 1px solid {NEUTRAL['border']} !important;
        }}
        div[class*="st-key-go_"] button:hover {{
            border-color: {BRAND['orange']} !important;
            color: {BRAND['orange']} !important;
            background: {tint(BRAND['orange'], .95)} !important;
        }}
        div[class*="st-key-go_"] button[kind="primary"] {{
            background: linear-gradient(135deg, {BRAND['orange_deep']}, {BRAND['orange']}) !important;
            border-color: transparent !important; color: #fff !important;
            font-weight: 800 !important;
            box-shadow: 0 6px 14px -6px rgba(217,78,0,.65);
        }}
        div[class*="st-key-go_"] button[kind="primary"]:hover {{
            color: #fff !important;
            background: linear-gradient(135deg, {BRAND['orange_deep']}, {BRAND['orange']}) !important;
        }}

        /* tombol utama */
        div[class*="st-key-sb_compute"] button, div[class*="st-key-calc_go"] button {{
            background: linear-gradient(135deg, {BRAND['orange_deep']}, {BRAND['orange']}) !important;
            color: #fff !important; border: none !important;
            font-weight: 800 !important; border-radius: 9px !important; height: 42px;
            box-shadow: 0 4px 12px -4px rgba(217,78,0,.6);
        }}
        div[class*="st-key-sb_compute"] button:disabled, div[class*="st-key-calc_go"] button:disabled {{
            background: {NEUTRAL['border']} !important; color: {NEUTRAL['text_soft']} !important;
            box-shadow: none;
        }}
        div[class*="st-key-sb_refresh"] button {{
            background: {NEUTRAL['wash']} !important; color: {NEUTRAL['text_muted']} !important;
            border: 1px solid {NEUTRAL['border']} !important; border-radius: 9px !important; height: 42px;
            font-weight: 600 !important;
        }}

        /* slider & select aksen orange */
        div[data-baseweb="slider"] div[role="slider"] {{ background: {BRAND['orange']} !important; }}
        .stSlider [data-testid="stTickBar"] {{ display: none; }}

        /* =====================================================
           TABS
           ===================================================== */
        div[data-testid="stTabs"] button[role="tab"] {{
            font-weight: 700 !important; font-size: 12.5px !important;
            color: {NEUTRAL['text_muted']} !important;
        }}
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
            color: {BRAND['orange']} !important;
        }}
        div[data-testid="stTabs"] div[data-baseweb="tab-highlight"] {{
            background: {BRAND['orange']} !important;
        }}

        /* =====================================================
           TABEL
           ===================================================== */
        /* ---- Tabel Control Manpower Ratio (header bergrup) -------------- */
        .dh-ctrl {{
            width: 100%; border-collapse: collapse; font-size: 12px;
            font-variant-numeric: tabular-nums;
        }}
        .dh-ctrl th {{
            color: #fff; padding: 7px 10px; text-align: right;
            font-size: 9.5px; letter-spacing: .06em; text-transform: uppercase;
            font-weight: 800; border-right: 1px solid rgba(255,255,255,.14);
        }}
        .dh-ctrl tr.grp th {{ text-align: center; font-size: 10.5px; }}
        .dh-ctrl th.lvl {{
            text-align: left; background: {NEUTRAL['wash']};
            color: {NEUTRAL['text']}; border-radius: 6px 0 0 0;
            vertical-align: middle;
        }}
        .dh-ctrl th.ratio {{
            background: {tint(BRAND['orange'], .90)}; color: {BRAND['orange_deep']};
            text-align: center; vertical-align: middle; line-height: 1.35;
            border-radius: 0 6px 0 0; border-right: none;
        }}
        .dh-ctrl th.ratio span {{
            font-size: 8px; font-weight: 600; text-transform: none;
            letter-spacing: 0; opacity: .8;
        }}
        .dh-ctrl td {{
            text-align: right; padding: 8px 10px;
            border-bottom: 1px solid {NEUTRAL['border_soft']};
        }}
        .dh-ctrl td.lvl {{
            text-align: left; font-weight: 700; color: {NEUTRAL['text']};
            background: {NEUTRAL['wash']};
        }}
        .dh-ctrl td.ratio {{
            text-align: center; font-size: 13px;
            background: {tint(BRAND['orange'], .955)};
        }}
        .dh-ctrl tbody tr:nth-child(even) td:not(.lvl):not(.ratio) {{
            background: {NEUTRAL['wash']};
        }}
        .dh-ctrl tbody tr:last-child td {{ border-bottom: none; }}

        .dh-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
        .dh-table th {{
            text-align: right; font-weight: 700; font-size: 9.5px; letter-spacing: .07em;
            text-transform: uppercase; color: #fff; background: {BRAND['navy']};
            padding: 7px 10px;
        }}
        .dh-table th:first-child {{ text-align: left; border-radius: 6px 0 0 0; }}
        .dh-table th:last-child {{ border-radius: 0 6px 0 0; }}
        .dh-table td {{
            text-align: right; padding: 6px 10px; color: {NEUTRAL['text']};
            border-bottom: 1px solid {NEUTRAL['border_soft']};
        }}
        .dh-table td:first-child {{ text-align: left; font-weight: 600; }}
        .dh-table tbody tr:nth-child(even) td {{ background: {NEUTRAL['wash']}; }}
        /* Kolom TOTAL: latarnya tint oranye TERANG, jadi teksnya HARUS gelap.
           Sebelumnya th.tc mewarisi color:#fff dari aturan `th` di atas —
           putih di atas tint terang jadi nyaris tak kelihatan. */
        .dh-table td.tc, .dh-table th.tc {{
            font-weight: 800; background: {tint(BRAND['orange'], .93)};
            color: {BRAND['orange_deep']} !important;
        }}
        .dh-table tbody tr:nth-child(even) td.tc {{ background: {tint(BRAND['orange'], .89)}; }}
        .dh-table tr.tr-total td {{
            font-weight: 800; background: {BRAND['navy']} !important; color: #fff; border-bottom: none;
        }}
        .dh-table tr.tr-total td:first-child {{ border-radius: 0 0 0 6px; }}
        /* Sel TOTAL di baris TOTAL: latar oranye solid, putih di atasnya
           kontrasnya rendah — dipakai teks navy gelap supaya tetap terbaca. */
        .dh-table tr.tr-total td.tc {{
            background: {BRAND['amber']} !important; color: {BRAND['navy']} !important;
        }}
        .dh-table tr.tr-total td:last-child {{ border-radius: 0 0 6px 0; }}

        div[data-testid="stDataFrame"] {{
            border-radius: 10px; overflow: hidden; border: 1px solid {NEUTRAL['border']};
        }}
        div[data-testid="stDataFrame"] table {{ font-size: 12px !important; }}

        /* =====================================================
           MISC
           ===================================================== */
        .dh-empty {{
            border: 1.5px dashed {NEUTRAL['border']}; border-radius: 14px;
            background: {NEUTRAL['card']}; padding: 34px 26px; text-align: center;
        }}
        .dh-empty .ico {{
            width: 54px; height: 54px; border-radius: 50%; margin: 0 auto 12px auto;
            background: {tint(BRAND['orange'], .9)};
            display: flex; align-items: center; justify-content: center; font-size: 24px;
        }}
        .dh-empty h4 {{ margin: 0 0 4px 0; font-size: 15px; font-weight: 700; }}
        .dh-empty p {{ margin: 0; font-size: 12.5px; color: {NEUTRAL['text_muted']}; }}

        /* =====================================================
           READOUT KALKULATOR — versi TERANG
           Sebelumnya panel ini berlatar navy pekat, jadi ia berdiri sendiri
           di antara kartu-kartu putih. Sekarang ia memakai kartu putih yang
           sama, dan "nuansa kalkulator"-nya dibawa oleh dua hal lain:
           (1) strip display bergaya LCD di atas, dan (2) baris rincian
           bergaya struk. Header & baris totalnya sengaja memakai navy yang
           persis sama dengan .dh-table supaya senada dengan tabel di
           sebelahnya.
           ===================================================== */
        .dh-calcout {{ margin-top: 2px; }}

        /* strip display ala layar kalkulator */
        .dh-calcout .disp {{
            background: {tint(BRAND['orange'], .93)};
            border: 1px solid {tint(BRAND['orange'], .80)};
            border-radius: 10px;
            padding: 12px 15px 13px 15px;
            margin-bottom: 12px;
            position: relative; overflow: hidden;
        }}
        /* garis-garis tipis diagonal, meniru tekstur layar segmen */
        .dh-calcout .disp::after {{
            content: ""; position: absolute; inset: 0;
            background: repeating-linear-gradient(
                135deg, rgba(255,255,255,0) 0 7px, rgba(255,255,255,.5) 7px 8px);
            pointer-events: none;
        }}
        .dh-calcout .disp .label {{
            font-size: 9.5px; letter-spacing: .12em; text-transform: uppercase;
            color: {BRAND['orange_deep']}; font-weight: 800; opacity: .8;
        }}
        .dh-calcout .disp .big {{
            font-family: {FONT_DISPLAY}; font-size: 44px; font-weight: 800;
            line-height: 1.02; color: {BRAND['orange_deep']};
            letter-spacing: -.02em; font-variant-numeric: tabular-nums;
        }}
        .dh-calcout .disp .unit {{
            font-size: 13px; font-weight: 700; color: {NEUTRAL['text_muted']}; margin-left: 6px;
        }}

        /* header kolom — navy, sama persis dengan .dh-table th */
        .dh-calcout .hd {{
            display: flex; align-items: center; gap: 10px;
            background: {BRAND['navy']}; border-radius: 6px 6px 0 0;
            padding: 7px 10px;
            font-size: 9.5px; letter-spacing: .07em; text-transform: uppercase;
            color: #fff; font-weight: 700;
        }}
        .dh-calcout .row {{
            display: flex; align-items: center; gap: 10px;
            padding: 8px 10px;
            border-bottom: 1px solid {NEUTRAL['border_soft']};
        }}
        .dh-calcout .row:nth-child(odd) {{ background: {NEUTRAL['wash']}; }}
        .dh-calcout .sw {{ width: 9px; height: 9px; border-radius: 3px; flex: 0 0 auto; }}
        .dh-calcout .nm {{
            flex: 1 1 auto; min-width: 0; font-size: 12px; font-weight: 600;
            color: {NEUTRAL['text']}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .dh-calcout .nm i {{ font-style: normal; color: {NEUTRAL['text_soft']}; font-weight: 500; }}
        .dh-calcout .qty {{
            flex: 0 0 auto; min-width: 46px; text-align: right;
            font-size: 12.5px; font-weight: 800; color: {NEUTRAL['text']};
            font-variant-numeric: tabular-nums;
        }}
        .dh-calcout .qty small {{
            font-size: 9.5px; color: {NEUTRAL['text_soft']}; font-weight: 600; margin-left: 3px;
        }}
        .dh-calcout .amt {{
            flex: 0 0 auto; min-width: 104px; text-align: right;
            font-size: 12px; font-weight: 700; color: {NEUTRAL['text']};
            font-variant-numeric: tabular-nums;
        }}
        /* baris total — navy + nominal amber, sama dengan .dh-table tr.tr-total */
        .dh-calcout .grand {{
            display: flex; align-items: center; justify-content: space-between; gap: 10px;
            background: {BRAND['navy']}; border-radius: 0 0 6px 6px;
            padding: 11px 12px;
        }}
        .dh-calcout .grand .k {{
            font-size: 9.5px; letter-spacing: .08em; text-transform: uppercase;
            color: #A9B4C6; font-weight: 800; line-height: 1.3;
        }}
        .dh-calcout .grand .v {{
            font-family: {FONT_DISPLAY}; font-size: 17px; font-weight: 800;
            color: {BRAND['amber']}; font-variant-numeric: tabular-nums; white-space: nowrap;
        }}

        /* Catatan inline (mis. jarak area kerja). Sengaja TIDAK memakai
           st.caption: tinggi container caption bawaan Streamlit ikut runtuh
           saat margin <p>-nya dinolkan di dalam kartu, sehingga tombol di
           bawahnya menimpa separuh teks. Div sendiri + margin eksplisit
           menghilangkan tumpang tindih itu. */
        .dh-inline-note {{
            display: flex; align-items: center; gap: 8px;
            background: {NEUTRAL['wash']};
            border: 1px solid {NEUTRAL['border_soft']};
            border-left: 3px solid {BRAND['orange']};
            border-radius: 8px;
            padding: 9px 12px;
            margin: 10px 0 2px 0;
            font-size: 11.5px; color: {NEUTRAL['text_muted']}; font-weight: 600;
            line-height: 1.4;
        }}
        .dh-inline-note b {{ color: {NEUTRAL['text']}; font-weight: 800; }}
        /* Varian paragraf: display flex bawaan membuat tiap <b> jadi kolom
           tersendiri, jadi catatan panjang harus block. */
        .dh-inline-note.block {{ display: block; }}
        .dh-inline-note.warn {{
            border-left-color: {STATUS['warn']};
            background: {tint(STATUS['warn'], .93)};
        }}

        /* jarak aman antara catatan dan tombol Hitung FTE */
        div[class*="st-key-calc_go"] {{ margin-top: 12px !important; }}

        /* Legend donut dengan persentase — menggantikan legend bawaan Plotly
           supaya angka share-nya ikut terbaca dan gaya barisnya sama dengan
           komponen lain di kartu. */
        .dh-plegend {{ margin-top: 12px; }}
        .dh-plegend .row {{
            display: flex; align-items: center; gap: 9px;
            padding: 8px 2px; border-top: 1px dashed {NEUTRAL['border']};
        }}
        .dh-plegend .row:first-child {{ border-top: none; }}
        .dh-plegend .sw {{ width: 10px; height: 10px; border-radius: 3px; flex: 0 0 auto; }}
        .dh-plegend .nm {{
            flex: 1 1 auto; min-width: 0; font-size: 12px; font-weight: 600;
            color: {NEUTRAL['text']}; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }}
        .dh-plegend .ft {{
            flex: 0 0 auto; min-width: 54px; text-align: right;
            font-size: 11.5px; font-weight: 600; color: {NEUTRAL['text_muted']};
            font-variant-numeric: tabular-nums;
        }}
        .dh-plegend .pc {{
            flex: 0 0 auto; min-width: 52px; text-align: right;
            font-size: 12.5px; font-weight: 800; color: {NEUTRAL['text']};
            font-variant-numeric: tabular-nums;
        }}

        /* Grid parameter rumus — dipakai di panel "Formula parameters" yang
           bisa dibuka-tutup di atas dashboard. Kotak kecil label + nilai,
           membungkus sendiri sesuai lebar layar. */
        /* Kolom TETAP, bukan auto-fill: keempat kartu parameter harus selalu
           terlihat sekaligus. Baru di bawah 900px ia turun jadi dua kolom. */
        /* Enam kartu -> tiga kolom, jadi ia jatuh rapi menjadi dua baris penuh
           alih-alih 4 + 2 yang menyisakan lubang di kanan bawah. */
        .dh-infogrid {{
            display: grid; gap: 9px;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            margin-bottom: 10px;
        }}
        @media (max-width: 900px) {{
            .dh-infogrid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        }}
        .dh-infogrid .cell {{
            background: {NEUTRAL['wash']};
            border: 1px solid {NEUTRAL['border_soft']};
            border-left: 3px solid {BRAND['orange']};
            border-radius: 8px; padding: 9px 11px;
        }}
        .dh-infogrid .cell.mut {{ border-left-color: {NEUTRAL['border']}; }}
        .dh-infogrid .k {{
            font-size: 9.5px; letter-spacing: .07em; text-transform: uppercase;
            color: {NEUTRAL['text_soft']}; font-weight: 800;
        }}
        .dh-infogrid .v {{
            font-size: 14px; font-weight: 800; color: {NEUTRAL['text']};
            margin-top: 2px; font-variant-numeric: tabular-nums;
        }}
        .dh-infogrid .n {{ font-size: 10.5px; color: {NEUTRAL['text_muted']}; font-weight: 500; }}
        .dh-secnote {{
            font-size: 11.5px; color: {NEUTRAL['text_muted']};
            margin: 0 0 9px 0; font-weight: 500;
        }}

        /* Expander "Formula parameters" — dibuat menonjol.
           Versi sebelumnya memakai expander polos bawaan Streamlit, yang di
           tengah dashboard putih nyaris tidak terlihat: hanya orang yang tahu
           panel itu ada yang akan mengkliknya. Sekarang ia berlatar oranye
           muda, bergaris tegas, dan judulnya besar + tebal. */
        div[class*="st-key-param_panel"] details {{
            border: 1.5px solid {tint(BRAND['orange'], .62)} !important;
            border-radius: 12px !important;
            background: {tint(BRAND['orange'], .955)} !important;
            box-shadow: 0 4px 14px -10px rgba(217,78,0,.65);
            overflow: hidden;
        }}
        div[class*="st-key-param_panel"] details summary {{
            padding: 13px 15px !important;
            background: {tint(BRAND['orange'], .90)} !important;
        }}
        div[class*="st-key-param_panel"] details summary:hover {{
            background: {tint(BRAND['orange'], .84)} !important;
        }}
        div[class*="st-key-param_panel"] details summary [data-testid="stMarkdownContainer"] p {{
            font-family: {FONT_DISPLAY} !important;
            font-size: 14.5px !important;
            font-weight: 800 !important;
            color: {BRAND['orange_deep']} !important;
            letter-spacing: -.005em;
        }}
        div[class*="st-key-param_panel"] details summary svg {{
            fill: {BRAND['orange_deep']} !important;
            color: {BRAND['orange_deep']} !important;
        }}

        /* Expander "Details" — netral, tidak boleh berebut perhatian dengan
           panel parameter di atas. */
        div[class*="st-key-detail_panel"] details {{
            border: 1px solid {NEUTRAL['border']} !important;
            border-radius: 12px !important;
            background: {NEUTRAL['card']} !important;
        }}
        div[class*="st-key-detail_panel"] details summary {{
            padding: 12px 15px !important;
            background: {NEUTRAL['wash']} !important;
        }}
        div[class*="st-key-detail_panel"] details summary [data-testid="stMarkdownContainer"] p {{
            font-size: 13px !important; font-weight: 800 !important;
            color: {NEUTRAL['text']} !important;
        }}

        /* =====================================================
           SECTION HEADING — pengganti legend_strip navy yang lebar penuh.
           Yang lama terlihat "keluar dari kanvas putih" karena ia balok gelap
           selebar layar tanpa kartu di belakangnya. Versi ini ramping,
           menempel pada grid kartu, dan hanya memakai aksen garis kiri.
           ===================================================== */
        .dh-section {{
            display: flex; align-items: baseline; gap: 12px;
            margin: 30px 0 16px 0; padding: 0 0 10px 0;
            border-bottom: 1px solid {NEUTRAL['border']};
        }}
        .dh-section .no {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 22px; height: 22px; border-radius: 6px; flex: 0 0 auto;
            background: {BRAND['navy']}; color: #fff;
            font-size: 11px; font-weight: 800; align-self: center;
        }}
        .dh-section .ttl {{
            font-family: {FONT_DISPLAY}; font-size: 16px; font-weight: 800;
            color: {NEUTRAL['text']}; letter-spacing: -.01em;
        }}
        .dh-section .sub {{
            font-size: 11.5px; color: {NEUTRAL['text_muted']}; font-weight: 500;
            flex: 1 1 auto;
        }}
        .dh-section .tag {{
            font-size: 10px; font-weight: 800; letter-spacing: .06em;
            text-transform: uppercase; color: {BRAND['orange_deep']};
            background: {tint(BRAND['orange'], .90)};
            border-radius: 999px; padding: 4px 10px; flex: 0 0 auto;
        }}

        /* =====================================================
           LANDING PAGE
           ===================================================== */
        @keyframes dh-rise {{
            from {{ opacity: 0; transform: translateY(14px); }}
            to   {{ opacity: 1; transform: translateY(0); }}
        }}
        @keyframes dh-sheen {{
            0%   {{ background-position: -140% 0; }}
            100% {{ background-position: 240% 0; }}
        }}
        @keyframes dh-float {{
            0%, 100% {{ transform: translateY(0); }}
            50%      {{ transform: translateY(-7px); }}
        }}

        .dh-hero {{
            position: relative; overflow: hidden;
            border-radius: 16px; padding: 22px 26px 24px 26px; margin-bottom: 4px;
            background:
                radial-gradient(120% 150% at 10% 0%, rgba(255,255,255,.24) 0%, rgba(255,255,255,0) 55%),
                linear-gradient(180deg, {BRAND['amber']} 0%, #FFA614 30%,
                                {BRAND['orange']} 72%, #F25F02 100%);
            box-shadow: 0 18px 40px -22px rgba(217,78,0,.75);
            animation: dh-rise .55s ease both;
        }}
        /* kilau yang menyapu pelan dari kiri ke kanan */
        .dh-hero::after {{
            content: ""; position: absolute; inset: 0; pointer-events: none;
            background: linear-gradient(105deg, rgba(255,255,255,0) 38%,
                        rgba(255,255,255,.30) 50%, rgba(255,255,255,0) 62%);
            background-size: 220% 100%;
            animation: dh-sheen 5.5s ease-in-out infinite;
        }}
        /* Band hero sengaja pendek: satu baris logo + judul. Paragraf pengantar
           dihapus karena membuat blok oranye ini mendominasi halaman. */
        .dh-hero .row {{ display: flex; align-items: center; gap: 16px; }}
        .dh-hero .logo {{
            height: 42px; flex: 0 0 auto;
            animation: dh-float 5.5s ease-in-out infinite;
        }}
        .dh-hero .rule {{ width: 1px; height: 36px; background: rgba(255,255,255,.42); }}
        .dh-hero h1 {{
            font-family: {FONT_DISPLAY}; font-size: 25px; font-weight: 800;
            color: #fff; margin: 0; line-height: 1.15; letter-spacing: -.015em;
        }}
        .dh-hero .eyebrow {{
            font-size: 9.5px; letter-spacing: .16em; text-transform: uppercase;
            color: rgba(255,255,255,.86); font-weight: 800; margin-bottom: 3px;
        }}
        /* sisakan ruang di kanan band untuk tombol Open Calculator */
        .dh-hero-action {{ padding-right: 250px; }}
        div[class*="st-key-hero_wrap"] {{ position: relative; }}

        /* ---- Tombol Open Calculator di pojok kanan band hero --------------
           Ditempel absolut ke atas band (bukan di dalamnya) karena tombol
           Streamlit tidak bisa ikut dirender di dalam string HTML hero.

           Dibuat timbul 3D supaya terbaca sebagai tombol fitur, bukan sekadar
           label: permukaannya diberi isi tipis + kilau di tepi atas, lalu
           "bibir" keras di bawahnya (box-shadow tanpa blur) yang memendek
           saat ditekan — itu yang memberi kesan tombol benar-benar turun. */
        div[class*="st-key-hero_calc"] {{
            position: absolute; top: 50%; right: 26px;
            transform: translateY(-50%); width: 200px; z-index: 8;
        }}
        div[class*="st-key-hero_calc"] button {{
            background: linear-gradient(180deg,
                        rgba(255,255,255,.30) 0%, rgba(255,255,255,.14) 100%) !important;
            border: 1.5px solid rgba(255,255,255,.92) !important;
            border-bottom-color: rgba(255,255,255,.75) !important;
            color: #fff !important;
            border-radius: 12px !important; height: 46px;
            box-shadow:
                0 4px 0 rgba(150,52,0,.55),
                0 9px 16px -6px rgba(120,42,0,.45),
                inset 0 1px 0 rgba(255,255,255,.55) !important;
            transform: translateY(0);
            transition: transform .12s ease, box-shadow .12s ease,
                        background-color .18s ease;
        }}
        div[class*="st-key-hero_calc"] button p {{
            font-weight: 800 !important; letter-spacing: .01em;
            text-shadow: 0 1px 1px rgba(140,48,0,.35);
        }}
        div[class*="st-key-hero_calc"] button:hover {{
            background: linear-gradient(180deg,
                        rgba(255,255,255,.42) 0%, rgba(255,255,255,.22) 100%) !important;
            border-color: #fff !important; color: #fff !important;
            transform: translateY(-2px);
            box-shadow:
                0 6px 0 rgba(150,52,0,.55),
                0 13px 20px -6px rgba(120,42,0,.5),
                inset 0 1px 0 rgba(255,255,255,.65) !important;
        }}
        div[class*="st-key-hero_calc"] button:active {{
            transform: translateY(3px);
            box-shadow:
                0 1px 0 rgba(150,52,0,.55),
                0 3px 7px -3px rgba(120,42,0,.4),
                inset 0 1px 0 rgba(255,255,255,.4) !important;
        }}
        @media (max-width: 900px) {{
            .dh-hero-action {{ padding-right: 26px; }}
            div[class*="st-key-hero_calc"] {{
                position: static; transform: none; width: 100%; margin-top: 10px;
            }}
        }}

        /* Kartu pilihan: ikon, judul, satu kalimat, satu baris "isinya apa".
           Daftar panduan empat butir yang lama membuat halaman penuh teks. */
        .dh-choice {{
            background: {NEUTRAL['card']};
            border: 1px solid {NEUTRAL['border']};
            border-radius: 16px; padding: 22px 20px 18px 20px;
            min-height: 196px;
            /* Ketiga kartu landing harus berakhir di tinggi yang sama supaya
               tombol di bawahnya sejajar. Panjang teks deskripsi tiap kartu
               berbeda, jadi tanpa height:100% kartu yang teksnya pendek jadi
               lebih pendek dan tombolnya naik sendiri. */
            height: 100%;
            box-shadow: 0 2px 10px -7px rgba(16,24,40,.22);
            transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
            animation: dh-rise .5s ease both;
            display: flex; flex-direction: column;
        }}
        .dh-choice:hover {{
            transform: translateY(-3px);
            border-color: var(--dh-accent, {BRAND['orange']});
            box-shadow: 0 16px 28px -20px rgba(16,24,40,.42);
        }}
        .dh-choice .ico {{
            width: 52px; height: 52px; border-radius: 14px;
            display: flex; align-items: center; justify-content: center;
            margin-bottom: 13px; background: var(--dh-wash, {tint(BRAND['orange'], .92)});
        }}
        .dh-choice .ico img {{ width: 30px; height: 30px; object-fit: contain; }}
        .dh-choice h3 {{
            font-family: {FONT_DISPLAY}; font-size: 17px; font-weight: 800;
            color: {NEUTRAL['text']}; margin: 0 0 6px 0;
        }}
        .dh-choice .desc {{
            font-size: 12.5px; color: {NEUTRAL['text_muted']}; line-height: 1.55;
            margin: 0 0 12px 0; flex: 1 1 auto;
        }}
        .dh-choice .fills {{
            font-size: 11.5px; color: {NEUTRAL['text']}; line-height: 1.5;
            border-top: 1px dashed {NEUTRAL['border']}; padding-top: 10px;
        }}
        .dh-choice .fills b {{ color: var(--dh-accent, {BRAND['orange']}); font-weight: 800; }}
        .dh-choice .body {{ display: flex; flex-direction: column; flex: 1 1 auto; }}

        /* Kartu kalkulator: selebar layar, ikon di kiri, isi mengalir ke kanan. */
        .dh-choice-wide {{
            flex-direction: row; align-items: flex-start; gap: 18px;
            min-height: 0; padding: 20px 22px;
        }}
        .dh-choice-wide .ico {{ margin-bottom: 0; flex: 0 0 auto; }}
        .dh-choice-wide .desc {{ margin-bottom: 10px; }}

        /* pemisah berlabel antara baris form dan kartu kalkulator */
        .dh-ldivider {{
            display: flex; align-items: center; gap: 14px;
            margin: 22px 0 14px 0;
        }}
        .dh-ldivider::before, .dh-ldivider::after {{
            content: ""; flex: 1 1 auto; height: 1px; background: {NEUTRAL['border']};
        }}
        .dh-ldivider span {{
            font-size: 10.5px; font-weight: 800; letter-spacing: .12em;
            text-transform: uppercase; color: {NEUTRAL['text_soft']};
        }}

        /* tombol landing: dibuat konsisten, tidak memakai merah bawaan Streamlit */
        div[class*="st-key-go_"] button {{
            border-radius: 11px !important; font-weight: 700 !important;
            height: 44px; border: 1px solid {NEUTRAL['border']} !important;
            background: {NEUTRAL['card']} !important; color: {NEUTRAL['text']} !important;
        }}
        div[class*="st-key-go_"] button:hover {{
            border-color: {BRAND['orange']} !important; color: {BRAND['orange']} !important;
        }}
        div[class*="st-key-go_calc"] button {{
            background: linear-gradient(135deg, {BRAND['orange_deep']}, {BRAND['orange']}) !important;
            color: #fff !important; border: none !important;
            box-shadow: 0 6px 16px -7px rgba(217,78,0,.65);
        }}
        div[class*="st-key-go_calc"] button:hover {{ color: #fff !important; }}
        div[class*="st-key-how_to"] button {{
            border-radius: 11px !important; height: 44px; font-weight: 700 !important;
            border: 1px solid {NEUTRAL['border']} !important;
            background: {NEUTRAL['card']} !important; color: {NEUTRAL['text_muted']} !important;
        }}

        /* panel How to use */
        .dh-howto {{ max-width: 720px; }}
        .dh-howto .blk {{ margin-bottom: 18px; }}
        .dh-howto .blk:last-child {{ margin-bottom: 0; }}
        .dh-howto .t {{
            font-family: {FONT_DISPLAY}; font-size: 14px; font-weight: 800;
            color: {NEUTRAL['text']};
        }}
        .dh-howto .s {{
            font-size: 11.5px; font-weight: 700; color: {BRAND['orange']};
            text-transform: uppercase; letter-spacing: .06em; margin-bottom: 8px;
        }}
        .dh-howto ol {{ margin: 0; padding-left: 18px; }}
        .dh-howto li {{
            font-size: 12.5px; color: {NEUTRAL['text_muted']}; line-height: 1.6;
            margin-bottom: 6px;
        }}
        .dh-howto li b {{ color: {NEUTRAL['text']}; font-weight: 700; }}

        /* nilai read-only di sidebar (datang dari BACKEND, bukan input user) */
        .dh-sreadout {{
            background: {NEUTRAL['wash']}; border: 1px solid {NEUTRAL['border']};
            border-radius: 10px; padding: 10px 12px; margin-bottom: 10px;
        }}
        .dh-sreadout .lbl {{
            font-size: 9.5px; font-weight: 800; letter-spacing: .08em;
            text-transform: uppercase; color: {NEUTRAL['text_soft']};
        }}
        .dh-sreadout .val {{
            font-family: {FONT_DISPLAY}; font-size: 22px; font-weight: 800;
            color: {NEUTRAL['text']}; line-height: 1.2; font-variant-numeric: tabular-nums;
        }}
        .dh-sreadout .note {{ font-size: 10.5px; color: {NEUTRAL['text_muted']}; }}
        .dh-sreadout .rows {{ margin-top: 4px; }}
        .dh-sreadout .row {{
            display: flex; justify-content: space-between; align-items: center;
            font-size: 12px; color: {NEUTRAL['text_muted']}; padding: 3px 0;
        }}
        .dh-sreadout .row b {{
            color: {NEUTRAL['text']}; font-weight: 800; font-variant-numeric: tabular-nums;
        }}

        /* keterangan asumsi tarif di bawah tabel cost */
        .dh-assume {{
            margin-top: 8px; padding-top: 8px;
            border-top: 1px dashed {NEUTRAL['border']};
        }}
        .dh-assume .lbl {{
            font-size: 9.5px; font-weight: 800; letter-spacing: .08em;
            text-transform: uppercase; color: {NEUTRAL['text_soft']}; margin-bottom: 5px;
        }}
        .dh-assume .chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
        .dh-assume .chip {{
            background: {NEUTRAL['wash']}; border: 1px solid {NEUTRAL['border']};
            border-radius: 7px; padding: 3px 8px; font-size: 11px;
            color: {NEUTRAL['text_muted']}; font-variant-numeric: tabular-nums;
        }}
        .dh-assume .chip b {{
            color: {NEUTRAL['text']}; font-weight: 800; margin-right: 5px;
        }}

        /* label parameter yang digambar manual (widget-nya label_visibility=collapsed) */
        .dh-plabel {{
            font-size: 13px; font-weight: 500; color: {NEUTRAL['text']};
            line-height: 1.5; padding-bottom: 2px; white-space: nowrap;
            overflow: hidden; text-overflow: ellipsis;
        }}

        /* ---- Tombol info (ikon "i") ----------------------------------
           Dipakai dua tempat: pojok kanan-atas kartu departemen di landing
           page, dan ujung kanan baris label parameter di mode Calculator.
           Label tombol dikosongkan; ikonnya digambar sebagai background. */
        div[class*="st-key-help_"] button,
        div[class*="st-key-info_"] button {{
            min-height: 0 !important; height: 26px !important; width: 26px !important;
            padding: 0 !important; border-radius: 999px !important;
            border: none !important; background: transparent !important;
            background-image: url("{info_uri}") !important;
            background-size: 20px 20px !important;
            background-position: center !important;
            background-repeat: no-repeat !important;
            opacity: .8; transition: opacity .15s ease, transform .15s ease;
            color: transparent !important; font-size: 0 !important;
            box-shadow: none !important;
        }}
        div[class*="st-key-help_"] button:hover,
        div[class*="st-key-info_"] button:hover {{
            opacity: 1; transform: scale(1.12); background-color: transparent !important;
        }}
        /* chevron bawaan popover disembunyikan supaya yang tampil hanya ikonnya */
        div[class*="st-key-help_"] button svg,
        div[class*="st-key-info_"] button svg {{ display: none !important; }}
        div[class*="st-key-help_"] button > div,
        div[class*="st-key-info_"] button > div {{ gap: 0 !important; }}

        div[class*="st-key-help_"] {{ display: flex; justify-content: flex-end; }}

        /* kartu departemen jadi jangkar posisi untuk ikon info di pojoknya */
        div[class*="st-key-dept_"] {{ position: relative; }}
        div[class*="st-key-info_"] {{
            position: absolute; top: 14px; right: 12px; width: 30px; z-index: 6;
        }}
        /* tanda seru kecil di sebelah label parameter */
        .dh-info {{
            display: inline-flex; align-items: center; justify-content: center;
            width: 15px; height: 15px; border-radius: 50%;
            background: {tint(BRAND['orange'], .86)}; color: {BRAND['orange_deep']};
            font-size: 10px; font-weight: 900; margin-left: 6px; cursor: help;
            vertical-align: middle;
        }}

        /* halaman embed: iframe dibuat rata dengan kanvas, tanpa kesan "kotak" */
        div[class*="st-key-embed_frame"] iframe {{
            border: 1px solid {NEUTRAL['border']} !important;
            border-radius: 14px !important;
            background: {NEUTRAL['card']};
            box-shadow: 0 2px 12px -8px rgba(16,24,40,.35);
        }}

        /* Pemilih periode di section Cost — digayakan seperti tombol navy
           supaya terbaca sebagai kontrol, bukan sebagai input form.
           Streamlit versi ini merender selectbox lewat react-aria (bukan
           BaseWeb lagi), jadi selectornya menyasar .react-aria-ComboBox. */
        div[class*="st-key-period_pick"] {{ margin-top: 18px; }}
        div[class*="st-key-period_pick"] .react-aria-ComboBox > div {{
            background: {BRAND['navy']} !important;
            border: 1px solid {BRAND['navy']} !important;
            border-radius: 9px !important;
            min-height: 42px !important;
            cursor: pointer !important;
            transition: background .16s ease;
        }}
        div[class*="st-key-period_pick"] .react-aria-ComboBox > div:hover {{
            background: #1C2E48 !important;
        }}
        div[class*="st-key-period_pick"] .react-aria-ComboBox input {{
            color: #FFFFFF !important;
            font-weight: 800 !important;
            font-size: 13px !important;
            cursor: pointer !important;
            caret-color: transparent;
        }}
        div[class*="st-key-period_pick"] .react-aria-ComboBox svg {{
            fill: #FFFFFF !important; color: #FFFFFF !important;
        }}
        div[class*="st-key-period_pick"] .react-aria-ComboBox button {{
            background: transparent !important;
        }}

        /* daftar statistik ringkas di kartu (dipakai di bawah gauge cost) */
        .dh-stats {{ margin-top: 10px; }}
        .dh-stats .row {{
            display: flex; align-items: baseline; justify-content: space-between; gap: 12px;
            padding: 10px 2px; border-top: 1px dashed {NEUTRAL['border']};
        }}
        .dh-stats .row:first-child {{ border-top: none; }}
        .dh-stats .k {{ font-size: 11.5px; color: {NEUTRAL['text_muted']}; font-weight: 600; }}
        .dh-stats .v {{
            font-size: 12.5px; color: {NEUTRAL['text']}; font-weight: 800;
            font-variant-numeric: tabular-nums; white-space: nowrap;
        }}

        .dh-note {{
            font-size: 11px; color: {NEUTRAL['text_soft']}; margin-top: 2px;
        }}
        .dh-legend {{ display: flex; gap: 14px; flex-wrap: wrap; margin-top: 12px;
                       padding-top: 10px; border-top: 1px dashed {NEUTRAL['border_soft']}; }}
        .dh-legend .it {{
            display: inline-flex; align-items: center; gap: 5px;
            font-size: 11px; font-weight: 600; color: {NEUTRAL['text_muted']};
        }}
        .dh-legend .it .sw {{ width: 10px; height: 10px; border-radius: 3px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Komponen
# ---------------------------------------------------------------------------
def header_band(title: str, subtitle: str = "", chips: list[str] | None = None) -> str:
    logo = image_uri("logo_putih (2).png")
    logo_html = f'<img class="logo" src="{logo}" alt="PT Darma Henwa"/><div class="rule"></div>' if logo else ""
    chips_html = "".join(f'<div class="chip">{c}</div>' for c in (chips or []))
    return (
        f'<div class="dh-band">{logo_html}'
        f'<div class="heading"><div class="title">{title}</div>'
        f'<div class="sub">{subtitle}</div></div>'
        f'<div class="chips">{chips_html}</div></div>'
    )


def legend_strip(left: str, items: list[tuple[str, str]]) -> str:
    """items = [(label, hex), ...]"""
    its = "".join(
        f'<div class="item"><span class="sw" style="background:{c}"></span>{lbl}</div>'
        for lbl, c in items
    )
    return f'<div class="dh-strip"><div class="left">{left}</div><div class="items">{its}</div></div>'


def kpi_card(label: str, value: str, sub: str = "", accent: str | None = None,
             site: str | None = None, emoji: str = "", value_size: int = 25) -> str:
    accent = accent or SITE_COLORS.get(site or "", BRAND["orange"])
    ico = f"<span>{emoji}</span>"
    return (
        f'<div class="kpi" style="--accent:{accent};--tint:{tint(accent, .88)};--vsize:{value_size}px">'
        f'<div class="ico">{ico}</div>'
        f'<div class="body"><div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'<div class="sub">{sub}</div></div></div>'
    )


@contextmanager
def card(key: str, title: str = "", sub: str = "", accent: str | None = None):
    """Kartu yang benar-benar membungkus isinya.

    Pemakaian:
        with theme.card("cost", "Estimasi Cost", "per bulan"):
            st.plotly_chart(fig)
    """
    import streamlit as st

    accent = accent or BRAND["orange"]
    container = st.container(key=f"card_{key}")
    with container:
        if title:
            s = f'<div class="s">{sub}</div>' if sub else ""
            st.markdown(
                f'<div class="dh-card-head" style="--accent:{accent}">'
                f'<span class="bar"></span><span class="t">{title}</span>{s}</div>',
                unsafe_allow_html=True,
            )
        yield container


def _fmt_id(v, dec: int = 0) -> str:
    """Angka format Indonesia (ribuan titik, desimal koma), selalu positif.

    Arah selisih dibawa oleh panah di dev_cell, bukan oleh tanda +/-, jadi
    fungsi ini sengaja tidak lagi menerima nilai bertanda.
    """
    return f"{abs(v):,.{dec}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def table_html(headers: list[str], rows: list[list], total_row: list | None = None,
               total_col: int | None = None) -> str:
    """Tabel ringkas dengan kolom total DAN baris total sekaligus."""
    def cls(i):
        return ' class="tc"' if total_col is not None and i == total_col else ""

    thead = "<tr>" + "".join(f"<th{cls(i)}>{h}</th>" for i, h in enumerate(headers)) + "</tr>"
    tbody = "".join(
        "<tr>" + "".join(f"<td{cls(i)}>{v}</td>" for i, v in enumerate(r)) + "</tr>"
        for r in rows
    )
    if total_row is not None:
        tbody += '<tr class="tr-total">' + "".join(
            f"<td{cls(i)}>{v}</td>" for i, v in enumerate(total_row)
        ) + "</tr>"
    return f'<table class="dh-table"><thead>{thead}</thead><tbody>{tbody}</tbody></table>'


def empty_state(title: str, body: str, emoji: str = "📊") -> str:
    return (
        f'<div class="dh-empty"><div class="ico">{emoji}</div>'
        f"<h4>{title}</h4><p>{body}</p></div>"
    )


def inline_note(html: str, warn: bool = False, block: bool = False) -> str:
    """Catatan kecil di bawah kartu.

    Bentuk bawaannya flex — cocok untuk satu baris pendek. Untuk catatan
    beberapa kalimat pakai `block=True`: tanpa itu setiap <b> menjadi kolom
    flex-nya sendiri dan kalimatnya terpotong-potong menyamping.
    """
    cls = "dh-inline-note"
    if warn:
        cls += " warn"
    if block:
        cls += " block"
    return f'<div class="{cls}">{html}</div>'


def donut_legend(items: list[tuple[str, str, str, str]]) -> str:
    """Legend donut: [(warna, label, "8 FTE", "100,0%"), ...]."""
    rows = "".join(
        f'<div class="row"><span class="sw" style="background:{color}"></span>'
        f'<span class="nm">{label}</span>'
        f'<span class="ft">{fte}</span><span class="pc">{pct}</span></div>'
        for color, label, fte, pct in items
    )
    return f'<div class="dh-plegend">{rows}</div>'


def info_grid(items: list[tuple[str, str, str]]) -> str:
    """Grid parameter: [(label, nilai, catatan), ...]. Catatan boleh string kosong."""
    cells = "".join(
        f'<div class="cell{"" if value else " mut"}">'
        f'<div class="k">{label}</div>'
        f'<div class="v">{value or "&ndash;"}</div>'
        + (f'<div class="n">{note}</div>' if note else "")
        + "</div>"
        for label, value, note in items
    )
    return f'<div class="dh-infogrid">{cells}</div>'


def section_heading(no: int, title: str, sub: str = "", tag: str = "") -> str:
    """Judul section ramping dengan nomor urut, aksen garis bawah tipis."""
    tag_html = f'<span class="tag">{tag}</span>' if tag else ""
    return (
        f'<div class="dh-section"><span class="no">{no}</span>'
        f'<span class="ttl">{title}</span>'
        f'<span class="sub">{sub}</span>{tag_html}</div>'
    )


def hero(logo_uri: str, eyebrow: str, title: str, action: bool = False) -> str:
    """Band oranye landing page.

    `action=True` menyisakan ruang kosong di sisi kanan band supaya tombol
    "Open Calculator" bisa ditempel ke sana secara absolut (tombol Streamlit
    tidak bisa ditaruh di dalam string HTML ini).
    """
    logo_html = (f'<img class="logo" src="{logo_uri}" alt=""/>'
                 f'<div class="rule"></div>') if logo_uri else ""
    cls = "dh-hero dh-hero-action" if action else "dh-hero"
    return (
        f'<div class="{cls}"><div class="row">{logo_html}'
        f'<div><div class="eyebrow">{eyebrow}</div><h1>{title}</h1></div>'
        f"</div></div>"
    )


def how_to_use(sections: list[dict]) -> str:
    """Isi panel 'How to use' pada landing page."""
    out = ['<div class="dh-howto">']
    for sec in sections:
        steps = "".join(f"<li>{s}</li>" for s in sec["steps"])
        out.append(
            f'<div class="blk"><div class="t">{sec["title"]}</div>'
            f'<div class="s">{sec["subtitle"]}</div>'
            f'<ol>{steps}</ol></div>'
        )
    out.append("</div>")
    return "".join(out)


def side_readout(label: str, value: str, note: str = "") -> str:
    """Nilai read-only di sidebar — untuk parameter yang datang dari BACKEND,
    bukan dari input pengguna."""
    n = f'<div class="note">{note}</div>' if note else ""
    return (
        f'<div class="dh-sreadout"><div class="lbl">{label}</div>'
        f'<div class="val">{value}</div>{n}</div>'
    )


def side_readout_list(label: str, items: list[tuple[str, str]]) -> str:
    rows = "".join(
        f'<div class="row"><span>{k}</span><b>{v}</b></div>' for k, v in items
    )
    return (
        f'<div class="dh-sreadout"><div class="lbl">{label}</div>'
        f'<div class="rows">{rows}</div></div>'
    )


def info_dot(text: str) -> str:
    """Tanda seru kecil dengan tooltip — dipakai di sebelah label parameter."""
    return f'<span class="dh-info" title="{text}">!</span>'


def assumption_note(label: str, items: list[tuple[str, str]]) -> str:
    """Keterangan asumsi tarif di bawah tabel cost.

    Tarif cost bukan berasal dari BACKEND melainkan konstanta di config.py,
    jadi angkanya ditulis terbuka di dashboard supaya isi tabel bisa
    ditelusuri tanpa harus membuka kode.
    """
    chips = "".join(
        f'<span class="chip"><b>{k}</b>{v}</span>' for k, v in items
    )
    return (
        f'<div class="dh-assume"><div class="lbl">{label}</div>'
        f'<div class="chips">{chips}</div></div>'
    )


def stat_list(items: list[tuple[str, str]]) -> str:
    """items = [(label, value), ...] — daftar 'label kiri / nilai kanan'."""
    rows = "".join(
        f'<div class="row"><span class="k">{k}</span><span class="v">{v}</span></div>'
        for k, v in items
    )
    return f'<div class="dh-stats">{rows}</div>'


def legend_html(items: list[tuple[str, str]]) -> str:
    its = "".join(
        f'<div class="it"><span class="sw" style="background:{c}"></span>{lbl}</div>'
        for lbl, c in items
    )
    return f'<div class="dh-legend">{its}</div>'


# ---------------------------------------------------------------------------
# Komponen khas HR Recruitment Portal
#
# CATATAN PENTING: berbeda dengan komponen warisan FTE di atas, semua fungsi
# di blok ini MENG-ESCAPE teks yang berasal dari data. Portal ini menampilkan
# nama kandidat, nama posisi, dan alasan keterlambatan yang diketik manusia —
# satu tanda "<" atau "&" di sana akan merusak layout kalau tidak di-escape.
# ---------------------------------------------------------------------------
def esc(v) -> str:
    """Escape nilai apa pun untuk disisipkan ke HTML. None/NaN jadi em-dash."""
    if v is None:
        return "—"
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "nat", "none"):
        return "—"
    return html.escape(s, quote=True)


def result_pill(code: str) -> str:
    """Badge status akhir kandidat: Hired / On Progress / Failed / Hold."""
    code = str(code or "").strip().upper()
    color = RESULT_COLORS.get(code, NEUTRAL["text_soft"])
    label = RESULT_LABEL.get(code, code.title() or "—")
    return (
        f'<span class="dh-pill" style="background:{tint(color, .90)};color:{color};'
        f'border-color:{tint(color, .74)}">{html.escape(label)}</span>'
    )


def sla_pill(state: str, days=None, budget=None) -> str:
    """Chip SLA satu tahap. state: Ontime / Late / Running / kosong."""
    state = str(state or "").strip().title()
    color = SLA_COLORS.get(state, NEUTRAL["text_soft"])
    if days is None:
        text = state or "—"
    else:
        text = f"{days} hr" + (f" / {budget}" if budget is not None else "")
    return (
        f'<span class="dh-pill" style="background:{tint(color, .90)};color:{color};'
        f'border-color:{tint(color, .74)}">{html.escape(text)}</span>'
    )


def progress_bar(done: int, total: int, label: str = "Recruitment Progress",
                 failed: bool = False) -> str:
    """Progress terhadap tahap yang BERLAKU untuk kandidat itu.

    `total` harus sudah dikurangi tahap yang tidak berlaku (mis. Technical Test
    untuk level Staff) — kalau tidak, kandidat yang sudah onboarding tidak akan
    pernah mencapai 100%.
    """
    total = max(int(total or 0), 1)
    done = max(min(int(done or 0), total), 0)
    pct = done / total * 100
    color = STATUS["bad"] if failed else BRAND["orange"]
    return (
        f'<div class="dh-prog">'
        f'<div class="top"><span class="lab">{html.escape(label)}</span>'
        f'<span class="cnt">{done} dari {total} tahap selesai</span></div>'
        f'<div class="track"><div class="fill" style="width:{pct:.0f}%;background:{color}"></div></div>'
        f'<div class="pct" style="color:{color}">{pct:.0f}%</div>'
        f"</div>"
    )


def bar_row(label: str, value: float, max_value: float, display: str,
            color: str | None = None, note: str = "") -> str:
    """Satu baris bar mendatar — dipakai heatmap SLA & funnel di Overview."""
    max_value = max(float(max_value or 0), 1e-9)
    pct = min(max(float(value or 0) / max_value, 0), 1) * 100
    color = color or BRAND["orange"]
    return (
        f'<div class="dh-barrow">'
        f'<span class="lab">{html.escape(str(label))}</span>'
        f'<span class="track"><span class="fill" style="width:{pct:.1f}%;background:{color}"></span></span>'
        f'<span class="val">{html.escape(display)}</span>'
        f'<span class="note">{html.escape(note)}</span>'
        f"</div>"
    )


def stage_table(stages: list[dict]) -> str:
    """Tabel tahap seleksi satu kandidat.

    Tiap item: {name, status, start, end, lt, budget, sla, applicable}
    status: done / active / idle / failed / na
    """
    icon_map = {"done": "✓", "failed": "✕", "na": "–"}
    badge_map = {"done": "Done", "failed": "Failed di sini", "active": "Berjalan",
                 "idle": "Belum mulai", "na": "Tidak berlaku"}
    color_map = {"done": STATUS["good"], "failed": STATUS["bad"],
                 "active": BRAND["orange"], "idle": NEUTRAL["text_soft"],
                 "na": NEUTRAL["text_soft"]}

    cols = ("", "Tahap", "Status", "Mulai → Selesai", "LT / Budget", "SLA")
    head = "".join(
        f'<th class="dh-num">{h}</th>' if h == "LT / Budget" else f"<th>{h}</th>"
        for h in cols
    )
    body = []
    for i, s in enumerate(stages):
        st = s.get("status", "idle")
        color = color_map.get(st, NEUTRAL["text_soft"])
        icon = icon_map.get(st, str(i + 1))
        lt, bud = s.get("lt"), s.get("budget")
        lt_txt = "—" if lt is None else f"{lt} hr" + (f" / {bud}" if bud is not None else "")
        dim = ' style="opacity:.55"' if st == "na" else ""
        body.append(
            f"<tr{dim}>"
            f'<td class="ix"><span class="dh-dot" style="background:{tint(color, .88)};'
            f'color:{color};border-color:{tint(color, .70)}">{icon}</span></td>'
            f'<td class="nm">{esc(s.get("name"))}</td>'
            f"<td>{result_pill('') if False else ''}"
            f'<span class="dh-pill" style="background:{tint(color, .90)};color:{color};'
            f'border-color:{tint(color, .74)}">{badge_map.get(st, "—")}</span></td>'
            f'<td class="dt">{esc(s.get("start"))}<br>→ {esc(s.get("end"))}</td>'
            f'<td class="dh-num">{html.escape(lt_txt)}</td>'
            f"<td>{sla_pill(s.get('sla'))}</td>"
            f"</tr>"
        )
    return (
        f'<table class="dh-table dh-stage"><thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
    )


STAGE_CSS = f"""
<style>
.dh-pill {{
  display:inline-block; padding:2px 9px; border-radius:999px;
  border:1px solid transparent; font-family:{FONT_BODY};
  font-size:10.5px; font-weight:700; letter-spacing:.03em; white-space:nowrap;
}}
.dh-dot {{
  display:inline-flex; align-items:center; justify-content:center;
  width:22px; height:22px; border-radius:50%; border:1px solid transparent;
  font-size:10.5px; font-weight:800; font-family:{FONT_DISPLAY};
}}
.dh-stage td.ix {{ width:38px; padding-left:12px; }}
.dh-stage td.nm {{ font-weight:600; }}
.dh-stage td.dt {{ font-size:11px; color:{NEUTRAL["text_muted"]}; line-height:1.45; }}

.dh-prog {{
  background:{NEUTRAL["card"]}; border:1px solid {NEUTRAL["border"]};
  border-radius:11px; padding:13px 16px; box-shadow:0 1px 2px rgba(17,24,39,.05);
}}
.dh-prog .top {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px; }}
.dh-prog .lab {{ font-family:{FONT_DISPLAY}; font-size:13px; font-weight:700; color:{NEUTRAL["text"]}; }}
.dh-prog .cnt {{ font-size:11px; color:{NEUTRAL["text_soft"]}; }}
.dh-prog .track {{ height:6px; background:{NEUTRAL["border"]}; border-radius:999px; overflow:hidden; }}
.dh-prog .fill {{ height:100%; border-radius:999px; transition:width .3s ease; }}
.dh-prog .pct {{ text-align:right; font-family:{FONT_DISPLAY}; font-size:12px;
  font-weight:800; margin-top:5px; font-variant-numeric:tabular-nums; }}

.dh-table.dh-portal td.dh-l, .dh-table.dh-portal th.dh-l {{ text-align:left; }}
.dh-table.dh-portal td.dh-r, .dh-table.dh-portal th.dh-r {{ text-align:right; }}
.dh-table.dh-portal td:first-child {{ font-weight:600; }}
.dh-tablewrap {{ overflow-x:auto; }}

/* Tabel tahap: kolom keterangan rata kiri, kolom angka rata kanan. Tanpa ini
   nama tahap ikut rata kanan karena aturan warisan .dh-table. */
.dh-table.dh-stage td, .dh-table.dh-stage th {{ text-align:left; }}
.dh-table.dh-stage td.dh-num, .dh-table.dh-stage th.dh-num {{ text-align:right; }}
.dh-table.dh-stage td:first-child, .dh-table.dh-stage th:first-child {{ text-align:center; }}

.dh-barrow {{
  display:grid; grid-template-columns:150px 1fr 78px 120px;
  align-items:center; gap:10px; padding:5px 0;
  border-bottom:1px dashed {NEUTRAL["border_soft"]};
}}
.dh-barrow:last-child {{ border-bottom:none; }}
.dh-barrow .lab {{ font-size:12px; font-weight:600; color:{NEUTRAL["text"]}; }}
.dh-barrow .track {{ height:7px; background:{NEUTRAL["wash"]};
  border:1px solid {NEUTRAL["border_soft"]}; border-radius:999px; overflow:hidden; }}
.dh-barrow .fill {{ display:block; height:100%; border-radius:999px; }}
.dh-barrow .val {{ text-align:right; font-size:12px; font-weight:800;
  font-variant-numeric:tabular-nums; color:{NEUTRAL["text"]}; }}
.dh-barrow .note {{ font-size:11px; color:{NEUTRAL["text_soft"]}; }}
@media (max-width:720px) {{
  .dh-barrow {{ grid-template-columns:110px 1fr 64px; }}
  .dh-barrow .note {{ display:none; }}
}}
</style>
"""


def data_table(headers: list[str], rows: list[list], align: str | None = None,
               total_row: list | None = None) -> str:
    """Tabel portal dengan perataan kolom yang ditentukan pemanggil.

    `align` = string kode per kolom: "l" rata kiri, "r" rata kanan.
    Contoh: data_table(["Nama", "Hari"], rows, align="lr")

    Kenapa tidak memakai table_html() warisan FTE: di sana SEMUA kolom selain
    yang pertama rata kanan, karena tabel FTE isinya angka. Tabel portal banyak
    berisi nama orang dan nama posisi, yang rata kanan jadi sulit dibaca.

    Isi sel diasumsikan SUDAH di-escape oleh pemanggil (pakai esc()), supaya
    penanda seperti warna achievement tetap bisa disisipkan.
    """
    align = align or "l" * len(headers)
    align = (align + "l" * len(headers))[:len(headers)]

    def cls(i):
        return "dh-r" if align[i] == "r" else "dh-l"

    thead = "".join(f'<th class="{cls(i)}">{h}</th>' for i, h in enumerate(headers))
    body = []
    for r in rows:
        body.append("<tr>" + "".join(
            f'<td class="{cls(i)}">{v}</td>' for i, v in enumerate(r)) + "</tr>")
    tot = ""
    if total_row:
        tot = ('<tr class="tr-total">' + "".join(
            f'<td class="{cls(i)}">{v}</td>' for i, v in enumerate(total_row)) + "</tr>")
    return (f'<div class="dh-tablewrap"><table class="dh-table dh-portal">'
            f"<thead><tr>{thead}</tr></thead><tbody>{''.join(body)}{tot}</tbody>"
            f"</table></div>")


def inject_portal_css():
    """CSS tambahan khas portal. Panggil SETELAH inject_css()."""
    import streamlit as st
    st.markdown(STAGE_CSS, unsafe_allow_html=True)
