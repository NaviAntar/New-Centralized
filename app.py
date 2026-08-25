"""
HR Recruitment Portal — PT Darma Henwa
Entrypoint Streamlit. Jalankan: streamlit run app.py

Struktur mengikuti pola repo FTE Calculator:
  - theme.inject_css() sekali di module level, satu blok CSS besar
  - router manual lewat st.session_state["page"], bukan folder pages/
  - tombol nav di-style lewat prefiks key (st.container(key="nav_..."))
  - cache ada di sini, data_loader & metrics tetap murni pandas

Bedanya dari FTE: halaman ini berisi data orang, jadi ada gerbang login di
paling depan dan seluruh teks dari data di-escape sebelum masuk HTML.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="PTDH HR Recruitment Portal",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

import auth  # noqa: E402
import charts  # noqa: E402
import config as C  # noqa: E402
import data_loader as DL  # noqa: E402
import metrics as M  # noqa: E402
import theme  # noqa: E402

theme.inject_css()
theme.inject_portal_css()

NAV = [
    ("overview", "Overview"),
    ("weekly", "Weekly Report"),
    ("tracking_candidate", "Tracking Kandidat"),
    ("tracking_position", "Tracking Posisi"),
    ("rec_room", "Recruitment Room"),
]


# ===========================================================================
# Data — cache di lapisan ini, loader tetap bisa dipanggil tanpa Streamlit
# ===========================================================================
@st.cache_data(ttl=C.CACHE_TTL_SECONDS, show_spinner="Mengambil data kandidat…")
def get_data():
    """Kembalikan (kandidat, tabel tahap, lead time). Kalender libur dipasang dulu.

    Urutannya penting: set_holidays() harus jalan SEBELUM stage_frame(), karena
    seluruh lead time dihitung dalam hari kerja terhadap kalender itu.
    """
    M.set_holidays(DL.load_holidays())
    df = M.prepare(DL.load_candidates())
    sf = M.stage_frame(df)
    return df, sf, M.lead_time(df, sf)


@st.cache_data(ttl=C.CACHE_TTL_SECONDS, show_spinner="Mengambil data MPP…")
def get_mpp():
    """Sheet 'Update MPP' dari spreadsheet Report — sumber daftar karyawan resign.

    Mengembalikan None kalau tidak terbaca, supaya halaman bisa menjelaskan
    keadaannya alih-alih gagal seluruhnya. Bagian lain Weekly Report tidak
    bergantung pada data ini.
    """
    try:
        return DL.load_mpp()
    except Exception:
        return None


def _site_of(loc: str) -> str | None:
    loc = str(loc or "").strip().upper()
    for key, cfg in C.SITES.items():
        if loc in [v.upper() for v in cfg["loc_values"]]:
            return key
    return None


def _site_filter(df: pd.DataFrame, site_key: str | None) -> pd.DataFrame:
    if not site_key or site_key == "Semua site":
        return df
    vals = [v.upper() for v in C.SITES[site_key]["loc_values"]]
    return df[df["loc"].isin(vals)]


def n(x, dec: int = 0) -> str:
    return charts.num(x, dec)


# ===========================================================================
# Kerangka halaman
# ===========================================================================
def shell(title: str, subtitle: str, chips: list[str] | None = None):
    base = [auth.role_badge(), pd.Timestamp.today().strftime("%d %b %Y")]
    st.markdown(theme.header_band(title, subtitle, chips=(chips or []) + base),
                unsafe_allow_html=True)


def navbar():
    pages = [(k, label) for k, label in NAV if auth.can_view(k)]
    cols = st.columns(len(pages) + 1, gap="small")
    for col, (key, label) in zip(cols, pages):
        with col, st.container(key=f"nav_{key}"):
            if st.button(label, width="stretch", key=f"btn_{key}",
                         type="primary" if st.session_state.page == key else "secondary"):
                st.session_state.page = key
                st.rerun()
    with cols[-1], st.container(key="nav_logout"):
        if st.button("Keluar", width="stretch", key="btn_logout"):
            auth.logout()
            st.rerun()


def data_or_stop():
    try:
        return get_data()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Data tidak bisa diambil.\n\n{exc}")
        st.stop()


# ===========================================================================
# Pembantu bersama
# ===========================================================================
def filterbar(key: str, specs: list[dict]):
    """Baris filter dalam satu panel putih.

    Dibungkus st.container(key="filterbar_…") supaya CSS bisa menyasarnya dan
    memberi latar putih. Tanpa itu kontrol Streamlit melayang di atas latar abu
    dan hampir tidak terlihat sebagai sesuatu yang bisa diklik.
    """
    hasil = []
    with st.container(key=f"filterbar_{key}"):
        cols = st.columns([s.get("width", 1) for s in specs], gap="medium")
        for col, s in zip(cols, specs):
            with col:
                jenis = s.get("kind", "select")
                if jenis == "select":
                    hasil.append(st.selectbox(s["label"], s["options"], key=s["key"],
                                              index=s.get("index", 0)))
                elif jenis == "multi":
                    hasil.append(st.multiselect(
                        s["label"], s["options"], key=s["key"],
                        default=s.get("default", []),
                        placeholder=s.get("placeholder", "Semua")))
                elif jenis == "text":
                    hasil.append(st.text_input(s["label"], key=s["key"],
                                               placeholder=s.get("placeholder", "")))
    return hasil


def periode_terpilih(tahun_pilih, bulan_pilih) -> list[tuple[int, int]]:
    """Gabungkan pilihan tahun x bulan jadi daftar (tahun, bulan)."""
    if not tahun_pilih or not bulan_pilih:
        return []
    return [(int(t), M.BULAN_NAMA_BALIK[b]) for t in tahun_pilih for b in bulan_pilih]


# ===========================================================================
# ① OVERVIEW — hanya dua bagian: ringkasan dan Looker
# ===========================================================================
def page_overview():
    df, sf, lt = data_or_stop()

    (site,) = filterbar("ov", [
        {"label": "Site", "key": "ov_site", "options": ["Semua site"] + list(C.SITES)},
    ])

    if site != "Semua site":
        keys = set(_site_filter(df, site)["cand_key"])
        df, lt = df[df["cand_key"].isin(keys)], lt[lt["cand_key"].isin(keys)]

    if not len(df):
        st.markdown(theme.empty_state("Tidak ada kandidat", "Belum ada data untuk site ini."),
                    unsafe_allow_html=True)
        return

    h = M.headline(df, lt)

    st.markdown(theme.section_heading(1, "Ringkasan", "kondisi pipeline saat ini"),
                unsafe_allow_html=True)
    k = st.columns(5, gap="small")
    with k[0]:
        st.markdown(theme.kpi_card("Total kandidat", n(h["candidates"]),
                                   f'{n(h["open"])} masih berjalan', emoji="👥",
                                   accent=theme.BRAND["navy"], value_size=28),
                    unsafe_allow_html=True)
    with k[1]:
        st.markdown(theme.kpi_card("Berhasil onboarding", n(h["hired"]),
                                   f'{h["hired"] / h["candidates"] * 100:.1f}% dari total',
                                   emoji="✅", accent=theme.STATUS["good"], value_size=28),
                    unsafe_allow_html=True)
    with k[2]:
        med = n(h["median_lt"]) if h["median_lt"] else "—"
        st.markdown(theme.kpi_card("Median time-to-hire", med,
                                   f'hari kerja · P90 {n(h["p90_lt"])} · n={h["lt_n"]}',
                                   emoji="⏱️", value_size=28), unsafe_allow_html=True)
    with k[3]:
        ov = f'{n(h["over_pct"], 1)}%' if h["over_pct"] is not None else "—"
        warna = theme.STATUS["bad"] if (h["over_pct"] or 0) > 20 else theme.STATUS["warn"]
        st.markdown(theme.kpi_card("Hire lewat budget", ov,
                                   f'{h["over_n"]} dari {h["scored_n"]} hire', emoji="⚠️",
                                   accent=warna, value_size=28), unsafe_allow_html=True)
    with k[4]:
        st.markdown(theme.kpi_card("Gagal", n(h["failed"]),
                                   f'{h["failed"] / h["candidates"] * 100:.1f}% dari total',
                                   emoji="✕", accent=theme.STATUS["bad"], value_size=28),
                    unsafe_allow_html=True)

    if h["date_errors"] or h["dup_names"]:
        bits = []
        if h["date_errors"]:
            bits.append(f'<b>{h["date_errors"]} kandidat</b> punya tanggal terbalik')
        if h["dup_names"]:
            bits.append(f'<b>{h["dup_names"]} baris</b> memakai nama kembar')
        st.markdown(theme.inline_note("Perlu dirapikan di sumber: " + " · ".join(bits)
                                      + ". Lead time baris itu tidak bisa dipercaya.",
                                      warn=True, block=True), unsafe_allow_html=True)

    st.markdown(theme.section_heading(2, "Dashboard Looker", "Recruitment Dashboard"),
                unsafe_allow_html=True)
    with theme.card("ov_looker", "Looker Studio", "visualisasi lengkap"):
        # Filter site di atas TIDAK mengubah isi Looker — Looker punya filternya
        # sendiri di dalam frame.
        if hasattr(st, "iframe"):
            st.iframe(C.LOOKER_EMBED_URL, height=C.LOOKER_EMBED_HEIGHT)
        else:
            st.components.v1.iframe(C.LOOKER_EMBED_URL, height=C.LOOKER_EMBED_HEIGHT,
                                    scrolling=True)


# ===========================================================================
# ② TRACKING KANDIDAT
# ===========================================================================
def page_tracking_candidate():
    df, sf, lt = data_or_stop()

    cari, site, status = filterbar("tc", [
        {"label": "Cari kandidat", "key": "tc_q", "kind": "text", "width": 2,
         "placeholder": "ketik sebagian nama, lalu pilih dari daftar di bawah"},
        {"label": "Site", "key": "tc_site", "options": ["Semua site"] + list(C.SITES)},
        {"label": "Status", "key": "tc_status",
         "options": ["Semua", "OPEN", "CLOSE", "FAILED"]},
    ])

    pool = _site_filter(df, site)
    if status != "Semua":
        pool = pool[pool["status1"] == status]
    if cari.strip():
        pool = pool[pool["candidate_id"].str.contains(cari.strip(), case=False,
                                                      na=False, regex=False)]

    if pool.empty:
        st.markdown(theme.empty_state(
            "Tidak ada yang cocok",
            "Longgarkan filternya, atau periksa lagi ejaan namanya."), unsafe_allow_html=True)
        return

    # Satu daftar pilihan saja. Versi sebelumnya punya kotak cari DAN dropdown
    # terpisah yang isinya juga nama, jadi orang bingung mana yang menentukan.
    # Sekarang kotak cari hanya menyaring; dropdown ini yang memilih.
    #
    # Label memakai NAMA POSISI, bukan Position ID — kode seperti "R22R030012"
    # tidak berarti apa-apa saat dibaca sekilas.
    pool = pool.copy()
    pool["_label"] = (pool["candidate_id"].astype(str) + "  ·  "
                      + pool["position_name"].fillna("(tanpa posisi)").astype(str)
                      + "  ·  " + pool["loc"].fillna("—").astype(str))
    peta = dict(zip(pool["_label"], pool["cand_key"]))
    label = st.selectbox(f"Kandidat — {len(pool)} cocok", sorted(peta), key="tc_pick")
    pilih = peta[label]

    row = pool[pool["cand_key"] == pilih].iloc[0]
    stages = sf[sf["cand_key"] == pilih].sort_values("stage_no")
    ltrow = lt[lt["cand_key"] == pilih].iloc[0]
    hstat = str(row["status1"] or "").upper()

    st.markdown(theme.section_heading(
        1, theme.esc(row["candidate_id"]), theme.esc(row.get("position_name")),
        tag=theme.RESULT_LABEL.get(hstat, hstat)), unsafe_allow_html=True)

    if row["is_duplicate_name"]:
        st.markdown(theme.inline_note(
            "Nama ini muncul lebih dari sekali — biasanya karena melamar lebih dari satu "
            f'posisi. Yang ditampilkan: <b>{theme.esc(row.get("position_name"))}</b>.',
            warn=True, block=True), unsafe_allow_html=True)

    st.markdown(theme.info_grid([
        ("Posisi", theme.esc(row.get("position_name")), theme.esc(row.get("position_id"))),
        ("Departemen", theme.esc(row.get("departement")), theme.esc(row.get("divisi"))),
        ("Level", theme.esc(row["level"]), f'budget {C.total_budget(row["level"])} hari kerja'),
        ("Lokasi", theme.esc(row.get("loc")), ""),
        ("Sumber CV", theme.esc(row.get("source_cv")), ""),
        ("Tahap terakhir", theme.esc(row.get("last_progress")), ""),
    ]), unsafe_allow_html=True)

    berlaku = stages[stages["applicable"]]
    selesai = int(berlaku["end"].notna().sum())
    st.markdown(theme.progress_bar(selesai, len(berlaku), failed=(hstat == "FAILED")),
                unsafe_allow_html=True)

    m = st.columns(4, gap="small")
    kartu = [
        ("Lead time berjalan", n(ltrow["lt_elapsed"]), "hari kerja, ujung ke ujung",
         "⏱️", theme.BRAND["orange"]),
        ("Jumlah durasi tahap", n(ltrow["lt_stage_sum"]), "hari yang benar-benar dikerjakan",
         "🧮", theme.BRAND["navy"]),
        ("Waktu menganggur", n(ltrow["lt_idle"]), "menunggu di antara tahap", "⏸️",
         theme.STATUS["bad"] if (ltrow["lt_idle"] or 0) > 10 else theme.STATUS["warn"]),
        ("Tahap terlambat", n(int(ltrow["stages_late"])), f'dari {selesai} tahap selesai',
         "⚠️", theme.STATUS["bad"] if int(ltrow["stages_late"]) else theme.STATUS["good"]),
    ]
    for col, (lab, val, sub, emo, warna) in zip(m, kartu):
        with col:
            st.markdown(theme.kpi_card(lab, val, sub, emoji=emo, accent=warna, value_size=22),
                        unsafe_allow_html=True)

    with theme.card("tc_stages", "Tahap seleksi",
                    "lead time dalam hari kerja, dibandingkan budget level ini"):
        rows = []
        for s in stages.itertuples():
            if not s.applicable:
                kode = "na"
            elif pd.notna(s.end):
                kode = "done"
            elif pd.notna(s.start):
                kode = "active"
            else:
                kode = "idle"
            rows.append({
                "name": s.stage, "status": kode,
                "start": s.start.date() if pd.notna(s.start) else None,
                "end": s.end.date() if pd.notna(s.end) else None,
                "lt": int(s.lt) if pd.notna(s.lt) else None,
                "budget": int(s.budget) if pd.notna(s.budget) else None,
                "sla": s.sla,
            })
        if hstat == "FAILED":
            ada = [i for i, r in enumerate(rows) if r["start"] or r["end"]]
            if ada:
                rows[ada[-1]]["status"] = "failed"
        st.markdown(theme.stage_table(rows), unsafe_allow_html=True)


# ===========================================================================
# ③ TRACKING POSISI
# ===========================================================================
def page_tracking_position():
    df, sf, lt = data_or_stop()

    cari, level, status = filterbar("tp", [
        {"label": "Cari posisi", "key": "tp_q", "kind": "text", "width": 2,
         "placeholder": "mis. supervisor, foreman, officer…"},
        {"label": "Level", "key": "tp_level",
         "options": ["Semua level"] + sorted(df["level"].dropna().unique().tolist())},
        {"label": "Tampilkan", "key": "tp_status",
         "options": ["Semua posisi", "Masih ada yang berjalan", "Belum ada hire"]},
    ])

    pool = df if level == "Semua level" else df[df["level"] == level]
    hasil = M.position_search(pool, cari)

    if status == "Masih ada yang berjalan":
        hasil = hasil[hasil["berjalan"] > 0]
    elif status == "Belum ada hire":
        hasil = hasil[hasil["hire"] == 0]

    if hasil.empty:
        st.markdown(theme.empty_state(
            "Tidak ada posisi yang cocok",
            "Coba kata kunci yang lebih pendek — pencarian mencocokkan sebagian nama."),
            unsafe_allow_html=True)
        return

    st.markdown(theme.section_heading(
        1, "Hasil pencarian", f"{len(hasil)} posisi · site tertera di tiap baris"),
        unsafe_allow_html=True)

    with theme.card("tp_list", "Posisi", "diurutkan dari yang paling banyak berjalan"):
        baris = []
        for r in hasil.itertuples():
            warna = theme.SITE_COLORS.get(_site_of(r.loc) or "", theme.NEUTRAL["text_soft"])
            chip = (f'<span class="dh-pill" style="background:{theme.tint(warna, .88)};'
                    f'color:{warna};border-color:{theme.tint(warna, .70)}">'
                    f"{theme.esc(r.loc)}</span>")
            baris.append([
                theme.esc(r.position_name), chip, theme.esc(r.level),
                theme.esc(r.departement), n(r.kandidat), n(r.hire),
                (f'<b style="color:{theme.STATUS["warn"]}">{n(r.berjalan)}</b>'
                 if r.berjalan else "0"),
                n(r.gagal),
            ])
        st.markdown(theme.data_table(
            ["Posisi", "Site", "Level", "Departemen", "Kandidat", "Hire", "Berjalan", "Gagal"],
            baris, align="llllrrrr"), unsafe_allow_html=True)

    # Satu posisi bisa ada di beberapa site, jadi pilihannya menyertakan site.
    hasil = hasil.copy()
    hasil["_label"] = hasil["position_name"].astype(str) + "  ·  " + hasil["loc"].astype(str)
    pilih = st.selectbox("Lihat kandidatnya", hasil["_label"].tolist(), key="tp_pick")
    baris_pos = hasil[hasil["_label"] == pilih].iloc[0]

    st.markdown(theme.section_heading(
        2, theme.esc(baris_pos["position_name"]),
        f'{theme.esc(baris_pos["loc"])} · {theme.esc(baris_pos["departement"])}',
        tag=theme.esc(baris_pos["position_id"])), unsafe_allow_html=True)

    kand = M.position_candidates(df, baris_pos["position_name"], baris_pos["loc"])
    k = st.columns(4, gap="small")
    for col, (lab, val, emo, warna) in zip(k, [
        ("Total kandidat", n(baris_pos["kandidat"]), "👥", theme.BRAND["navy"]),
        ("Hire", n(baris_pos["hire"]), "✅", theme.STATUS["good"]),
        ("Masih berjalan", n(baris_pos["berjalan"]), "⏳", theme.STATUS["warn"]),
        ("Gagal", n(baris_pos["gagal"]), "✕", theme.STATUS["bad"]),
    ]):
        with col:
            st.markdown(theme.kpi_card(lab, val, "", emoji=emo, accent=warna, value_size=24),
                        unsafe_allow_html=True)

    with theme.card("tp_kand", "Kandidat untuk posisi ini", f"{len(kand)} orang"):
        if kand.empty:
            st.markdown(theme.empty_state("Belum ada kandidat", "—"), unsafe_allow_html=True)
        else:
            st.markdown(theme.data_table(
                ["Kandidat", "Level", "Status", "Tahap terakhir", "Sumber CV",
                 "Screening", "Onboarding"],
                [[theme.esc(r.candidate_id), theme.esc(r.level),
                  theme.result_pill(r.status1), theme.esc(r.last_progress),
                  theme.esc(r.source_cv),
                  theme.esc(r.start_screening_cv.date() if pd.notna(r.start_screening_cv) else None),
                  theme.esc(r.date_onboarding.date() if pd.notna(r.date_onboarding) else None)]
                 for r in kand.itertuples()], align="lllllll"), unsafe_allow_html=True)


# ===========================================================================
# ④ WEEKLY REPORT
# ===========================================================================
def _recruiter_extra() -> dict:
    """Pemetaan inisial tambahan yang dimasukkan lewat panel di halaman ini."""
    return st.session_state.setdefault("recruiter_extra", {})


def page_weekly():
    df, sf, lt = data_or_stop()

    tahun_ada = sorted(sf["screening_date"].dropna().dt.year.unique().tolist(), reverse=True)
    bulan_ada = list(M.BULAN_NAMA.values())
    thn_default = [str(tahun_ada[0])] if tahun_ada else []

    tahun_pilih, bulan_pilih = filterbar("wk", [
        {"label": "Tahun", "key": "wk_year", "kind": "multi",
         "options": [str(y) for y in tahun_ada], "default": thn_default, "width": 1,
         "placeholder": "Pilih tahun"},
        {"label": "Bulan", "key": "wk_month", "kind": "multi",
         "options": bulan_ada, "default": [], "width": 3,
         "placeholder": "Semua bulan — pilih beberapa untuk membandingkan"},
    ])

    periods = periode_terpilih(tahun_pilih, bulan_pilih)
    if tahun_pilih and not bulan_pilih:
        # Tidak memilih bulan berarti seluruh bulan pada tahun yang dipilih.
        periods = [(int(t), b) for t in tahun_pilih for b in range(1, 13)]

    if periods:
        dari = min(pd.Timestamp(t, b, 1) for t, b in periods)
        sampai = max(pd.Timestamp(t, b, 1) + pd.offsets.MonthEnd(1) for t, b in periods)
        label_periode = f"{dari.date()} s/d {sampai.date()}"
    else:
        dari = sampai = None
        label_periode = "sepanjang waktu"

    # ── Performance ────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(
        1, "Performance recruiter",
        "rata-rata tiap tahap dijumlahkan — bukan lead time PRF sampai akhir"),
        unsafe_allow_html=True)

    perf = M.recruiter_performance(sf, dari, sampai, extra_map=_recruiter_extra())
    with theme.card("wk_perf", "Performance", f"periode screening CV · {label_periode}"):
        baris = []
        for r in perf.itertuples():
            ach = r.achievement
            warna = (theme.STATUS["good"] if pd.notna(ach) and ach >= 100
                     else theme.STATUS["bad"] if pd.notna(ach) else theme.NEUTRAL["text_soft"])
            baris.append([
                theme.esc(r.name),
                n(r.sla_actual, 1) if pd.notna(r.sla_actual) else "—",
                n(r.sla_budget, 1) if pd.notna(r.sla_budget) else "—",
                (f'<span style="color:{warna};font-weight:800">{n(ach, 1)}%</span>'
                 if pd.notna(ach) else "—"),
                n(r.stages), n(r.candidates), n(r.onboarding),
            ])
        st.markdown(theme.data_table(
            ["Nama", "SLA Actual", "SLA Budget", "Achievement", "Tahap", "Kandidat",
             "Onboarding"], baris, align="lrrrrrr"), unsafe_allow_html=True)
        st.markdown(theme.inline_note(
            "<b>SLA Actual</b> dihitung dua langkah: tiap tahap yang orang itu pegang "
            "dirata-ratakan dulu, lalu rata-rata antar tahap dijumlahkan. <b>SLA Budget</b> "
            "mengikuti tahap yang sama, jadi keduanya selalu sebanding. <b>Achievement</b> = "
            "Budget ÷ Actual; di atas 100% berarti lebih cepat dari target. Kolom "
            "<b>Onboarding</b> tidak bisa dijumlahkan ke bawah — satu kandidat ditangani "
            "beberapa PIC dan masing-masing mendapat kreditnya.",
            block=True), unsafe_allow_html=True)

    punya_data = perf[perf["stages"] > 0]["name"].tolist()
    if punya_data:
        with st.expander("Rincian per tahap — dari mana angka di atas berasal"):
            siapa = st.selectbox("Recruiter", punya_data, key="wk_detail")
            rinci = M.recruiter_stage_detail(sf, siapa, dari, sampai,
                                             extra_map=_recruiter_extra())
            if rinci.empty:
                st.markdown(theme.empty_state("Belum ada data", "—"), unsafe_allow_html=True)
            else:
                total = [ "TOTAL", n(rinci["kandidat"].sum()), n(rinci["avg_lt"].sum(), 1),
                          n(rinci["avg_budget"].sum(), 1), "" ]
                st.markdown(theme.data_table(
                    ["Tahap", "Kandidat", "Rata-rata LT", "Rata-rata budget", "Achievement"],
                    [[theme.esc(r.stage), n(r.kandidat), n(r.avg_lt, 1), n(r.avg_budget, 1),
                      f"{n(r.achievement, 1)}%" if pd.notna(r.achievement) else "—"]
                     for r in rinci.itertuples()],
                    align="lrrrr", total_row=total), unsafe_allow_html=True)

    if auth.can_do("edit_recruiter"):
        with st.expander("Kelola recruiter — petakan inisial ke nama lengkap"):
            st.markdown(theme.inline_note(
                "Database lama memakai inisial, tim sekarang memakai nama lengkap. Pemetaan "
                "di sini berlaku untuk sesi ini saja. Supaya permanen, tambahkan ke "
                "<code>RECRUITER_NAMES</code> di <code>config.py</code>.", block=True),
                unsafe_allow_html=True)
            belum = M.unmapped_initials(sf, extra_map=_recruiter_extra())
            if belum.empty:
                st.markdown(theme.empty_state("Semua inisial sudah terpetakan", "—", emoji="✅"),
                            unsafe_allow_html=True)
            else:
                st.markdown(theme.data_table(
                    ["Inisial", "Aktivitas", "Kandidat", "Onboarding"],
                    [[theme.esc(r.pic_initial), n(r.aktivitas), n(r.kandidat), n(r.onboarding)]
                     for r in belum.itertuples()], align="lrrr"), unsafe_allow_html=True)
            c1, c2, c3 = st.columns([1, 2, 1])
            with c1:
                ini = st.text_input("Inisial", key="wk_ini", placeholder="mis. AIC")
            with c2:
                nm = st.text_input("Nama lengkap", key="wk_nama")
            with c3:
                st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
                if st.button("Tambahkan", type="primary", width="stretch", key="wk_add"):
                    if ini.strip() and nm.strip():
                        _recruiter_extra()[ini.strip().upper()] = nm.strip()
                        st.rerun()
                    else:
                        st.warning("Isi inisial dan nama lengkapnya.")

    # ── New Hire ───────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(2, "New Hire", "onboarding per departemen"),
                unsafe_allow_html=True)
    with theme.card("wk_nh", "New Hire", label_periode):
        nh = M.new_hire_matrix(df, periods)
        if nh.empty:
            st.markdown(theme.empty_state(
                "Belum ada onboarding di periode ini",
                "Pilih tahun atau bulan lain di filter atas."), unsafe_allow_html=True)
        else:
            kolom = list(nh.columns)
            isi = [[theme.esc(r[0])] + [n(v) for v in r[1:]] for r in nh.values.tolist()]
            st.markdown(theme.data_table(kolom, isi[:-1], total_row=isi[-1],
                                         align="l" + "r" * (len(kolom) - 1)),
                        unsafe_allow_html=True)

    # ── Ringkasan per site ─────────────────────────────────────────────────
    st.markdown(theme.section_heading(3, "Ringkasan per site", "onboarding per site"),
                unsafe_allow_html=True)
    with theme.card("wk_sum", "Summary", label_periode):
        sm = M.summary_matrix(df, periods)
        if sm.empty:
            st.markdown(theme.empty_state(
                "Belum ada onboarding di periode ini",
                "Pilih tahun atau bulan lain di filter atas."), unsafe_allow_html=True)
        else:
            kolom = list(sm.columns)
            isi = [[theme.esc(r[0])] + [n(v) for v in r[1:]] for r in sm.values.tolist()]
            st.markdown(theme.data_table(kolom, isi[:-1], total_row=isi[-1],
                                         align="l" + "r" * (len(kolom) - 1)),
                        unsafe_allow_html=True)

    # ── On Progress ────────────────────────────────────────────────────────
    st.markdown(theme.section_heading(
        4, "On Progress", "bulan berjalan · mengikuti rumus sheet ONP"),
        unsafe_allow_html=True)
    panels = M.on_progress(df)
    cols = st.columns(3, gap="small")
    for col, (nama, sel) in zip(cols, panels.items()):
        with col, theme.card(f"wk_onp_{nama}", nama, f"{len(sel)} kandidat"):
            if sel.empty:
                st.markdown(theme.empty_state("Kosong", "Tidak ada di tahap ini.", emoji="—"),
                            unsafe_allow_html=True)
            else:
                st.markdown(theme.data_table(
                    ["Kandidat", "Posisi", "Site", "Tanggal"],
                    [[theme.esc(r.candidate_id), theme.esc(r.position_name), theme.esc(r.loc),
                      theme.esc(r.tanggal.date() if pd.notna(r.tanggal) else None)]
                     for r in sel.itertuples()], align="llll"), unsafe_allow_html=True)

    # ── Karyawan resign ────────────────────────────────────────────────────
    st.markdown(theme.section_heading(5, "Karyawan resign", "bulan berjalan"),
                unsafe_allow_html=True)
    with theme.card("wk_resign", "Resign", "level di bawah 11, berhenti sebelum kontrak habis"):
        mpp = get_mpp()
        if mpp is None:
            st.markdown(theme.empty_state(
                "Data MPP belum bisa diambil",
                "Sheet <b>Update MPP</b> di spreadsheet Report belum terbaca. Pastikan "
                "spreadsheet-nya di-share 'Anyone with the link — Viewer'.", emoji="🔌"),
                unsafe_allow_html=True)
        else:
            res = M.resign(mpp)
            if res.empty:
                st.markdown(theme.empty_state("Tidak ada yang resign bulan ini", "—"),
                            unsafe_allow_html=True)
            else:
                st.markdown(theme.data_table(
                    ["Karyawan", "Posisi", "Site", "Tanggal resign", "Akhir kontrak", "Level"],
                    [[theme.esc(r.Karyawan), theme.esc(r._2), theme.esc(r.Site),
                      theme.esc(r._4.date() if pd.notna(r._4) else None),
                      theme.esc(r._5.date() if pd.notna(r._5) else None),
                      n(r.Level)] for r in res.itertuples()],
                    align="lllllr"), unsafe_allow_html=True)


# ===========================================================================
# ⑤ RECRUITMENT ROOM
# ===========================================================================
def page_rec_room():
    st.markdown(theme.section_heading(
        1, "Form monitoring", "pilih site, salin linknya, lalu isi langsung di sini"),
        unsafe_allow_html=True)

    keys = list(C.SITES)
    labels = [f'{C.SITES[k]["icon"]}  {C.SITES[k]["label"]}' for k in keys]
    picked = st.radio("Site", labels, horizontal=True, key="rr_site",
                      label_visibility="collapsed")
    site = keys[labels.index(picked)]
    cfg = C.SITES[site]
    url = C.form_url_for(site)
    sheet = C.sheet_url_for(site)
    note = C.FORM_NOTES.get(site, "")

    with theme.card("rr_link", f'{cfg["label"]}', note):
        if url:
            st.markdown('<div class="dh-linklabel">Link form</div>', unsafe_allow_html=True)
            st.code(url, language=None)
        if sheet:
            st.markdown('<div class="dh-linklabel">Link spreadsheet</div>',
                        unsafe_allow_html=True)
            st.code(sheet, language=None)
        if not url and not sheet:
            st.markdown(theme.empty_state(
                "Belum ada link untuk site ini",
                "Tempel URL-nya di <code>FORM_URLS</code> dan <code>SHEET_URLS</code> pada "
                "<code>config.py</code>.", emoji="📝"), unsafe_allow_html=True)

        b1, b2, b3 = st.columns([1, 1, 2])
        with b1, st.container(key="rr_open"):
            if url:
                st.link_button("Buka form", url, width="stretch")
        with b2, st.container(key="rr_sheet"):
            if sheet:
                st.link_button("Buka sheet", sheet, width="stretch")

    if url:
        with theme.card("rr_embed", "Form", f'{cfg["label"]} · tersemat di halaman ini'):
            if hasattr(st, "iframe"):
                st.iframe(url, height=C.FORM_EMBED_HEIGHT)
            else:
                st.components.v1.iframe(url, height=C.FORM_EMBED_HEIGHT, scrolling=True)
            st.markdown(theme.inline_note(
                "Kalau kotak di atas kosong, Apps Script memblokir penyematan. Perbaikannya "
                "satu baris di <code>doGet()</code> pada <code>Code.gs</code>: tambahkan "
                "<code>.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)</code>, "
                "lalu deploy versi baru. Contoh lengkapnya ada di README.",
                warn=True, block=True), unsafe_allow_html=True)


# ===========================================================================
# Halaman yang belum dibangun — jujur soal apa yang belum ada
# ===========================================================================
def page_todo(title: str, isi: list[str], fase: str):
    st.markdown(theme.section_heading(1, title, f"dijadwalkan {fase}"), unsafe_allow_html=True)
    with theme.card("todo", title, "belum dibangun"):
        st.markdown(theme.empty_state(
            "Halaman ini belum ada isinya",
            "Yang akan masuk ke sini:<br>• " + "<br>• ".join(theme.esc(i) for i in isi),
            emoji="🚧",
        ), unsafe_allow_html=True)


# ===========================================================================
# Router
# ===========================================================================
def main():
    role = auth.require_login()
    st.session_state.setdefault("page", "overview")

    # Peran User tidak boleh mendarat di halaman yang tidak diizinkan, termasuk
    # kalau nilainya tertinggal dari sesi sebelumnya.
    if not auth.can_view(st.session_state.page):
        st.session_state.page = "overview"

    titles = {
        "overview": ("Overview", "Ringkasan pipeline dan dashboard Looker"),
        "weekly": ("Weekly Report", "Performance recruiter, New Hire, ringkasan site, On Progress, resign"),
        "tracking_candidate": ("Tracking Kandidat", "Proses seleksi per kandidat, tahap demi tahap"),
        "tracking_position": ("Tracking Posisi", "Cari posisi, site tertera di tiap baris"),
        "rec_room": ("Recruitment Room", "Form monitoring per site"),
    }
    title, subtitle = titles[st.session_state.page]
    shell(title, subtitle)
    navbar()
    st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

    page = st.session_state.page
    if page == "overview":
        page_overview()
    elif page == "rec_room":
        page_rec_room()
    elif page == "weekly":
        page_weekly()
    elif page == "tracking_candidate":
        page_tracking_candidate()
    elif page == "tracking_position":
        page_tracking_position()


main()
