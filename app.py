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
# ① OVERVIEW — menggantikan embed Looker
# ===========================================================================
def page_overview():
    df, sf, lt = data_or_stop()

    site = st.selectbox("Site", ["Semua site"] + list(C.SITES), key="ov_site")
    if site != "Semua site":
        keys = set(_site_filter(df, site)["cand_key"])
        df, sf, lt = (df[df["cand_key"].isin(keys)], sf[sf["cand_key"].isin(keys)],
                      lt[lt["cand_key"].isin(keys)])

    h = M.headline(df, lt)
    if not len(df):
        st.markdown(theme.empty_state("Tidak ada kandidat", "Belum ada data untuk site ini."),
                    unsafe_allow_html=True)
        return

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
                                   emoji="✅", accent=theme.STATUS["good"]),
                    unsafe_allow_html=True)
    with k[2]:
        med = f'{n(h["median_lt"])}' if h["median_lt"] else "—"
        st.markdown(theme.kpi_card("Median time-to-hire", med,
                                   f'hari kerja · P90 {n(h["p90_lt"])} · n={h["lt_n"]}',
                                   emoji="⏱️"), unsafe_allow_html=True)
    with k[3]:
        ov = f'{n(h["over_pct"], 1)}%' if h["over_pct"] is not None else "—"
        col = theme.STATUS["bad"] if (h["over_pct"] or 0) > 20 else theme.STATUS["warn"]
        st.markdown(theme.kpi_card("Hire lewat budget", ov,
                                   f'{h["over_n"]} dari {h["scored_n"]} hire', emoji="⚠️",
                                   accent=col), unsafe_allow_html=True)
    with k[4]:
        st.markdown(theme.kpi_card("Gagal", n(h["failed"]),
                                   f'{h["failed"] / h["candidates"] * 100:.1f}% dari total',
                                   emoji="✕", accent=theme.STATUS["bad"]),
                    unsafe_allow_html=True)

    # Kualitas data ditaruh di depan, bukan disembunyikan. Angka di halaman ini
    # hanya sebaik data yang mengisinya.
    if h["date_errors"] or h["dup_names"]:
        bits = []
        if h["date_errors"]:
            bits.append(f'<b>{h["date_errors"]} kandidat</b> punya tanggal terbalik '
                        "(selesai mendahului mulai) — lead time-nya tidak bisa dipercaya")
        if h["dup_names"]:
            bits.append(f'<b>{h["dup_names"]} baris</b> memakai nama yang kembar; '
                        "portal membedakannya dengan Position ID")
        st.markdown(theme.inline_note("Perlu dirapikan di sumber: " + " · ".join(bits),
                                      warn=True, block=True),
                    unsafe_allow_html=True)

    st.markdown(theme.section_heading(2, "Funnel & tren", "dari screening sampai onboarding"),
                unsafe_allow_html=True)
    c1, c2 = st.columns([1.15, 1], gap="small")
    with c1:
        with theme.card("ov_funnel", "Funnel seleksi",
                        "kandidat yang minimal sampai tahap tersebut · PRF, Technical Test, dan Psikotes di luar jalur utama"):
            st.plotly_chart(charts.funnel_bars(M.funnel(sf)), width="stretch",
                            config={"displayModeBar": False})
    with c2:
        with theme.card("ov_status", "Komposisi status", "seluruh kandidat"):
            st.plotly_chart(charts.status_donut({
                "CLOSE": h["hired"], "OPEN": h["open"], "FAILED": h["failed"],
            }), width="stretch", config={"displayModeBar": False})
        with theme.card("ov_source", "Hire rate per sumber CV", "hire dibagi kandidat masuk"):
            st.plotly_chart(charts.source_bars(M.source_effectiveness(df)), width="stretch",
                            config={"displayModeBar": False})

    with theme.card("ov_trend", "Tren median time-to-hire",
                    "per bulan onboarding · level Non Staff dikecualikan"):
        st.plotly_chart(charts.trend_line(M.hire_trend(df, lt), budget=61), width="stretch",
                        config={"displayModeBar": False})

    st.markdown(theme.section_heading(3, "Kepatuhan SLA",
                                      "aktual vs budget resmi per level"), unsafe_allow_html=True)
    with theme.card("ov_sla", "Keterlambatan per tahap",
                    "hari kerja, dibandingkan matriks SLA Monitoring 2026 › Backend"):
        sla = M.sla_summary(sf)
        if sla.empty:
            st.markdown(theme.empty_state("Belum ada tahap selesai", "—"), unsafe_allow_html=True)
        else:
            rows = "".join(
                theme.bar_row(
                    r.stage, r.late_pct, 100, f"{n(r.late_pct, 1)}%",
                    color=(theme.STATUS["bad"] if r.late_pct >= 40 else
                           theme.STATUS["warn"] if r.late_pct >= 15 else theme.STATUS["good"]),
                    note=f"{n(r.late)}/{n(r.n)} · median {n(r.median_lt)} vs budget {n(r.budget)}",
                )
                for r in sla.itertuples()
            )
            st.markdown(rows, unsafe_allow_html=True)
        st.markdown(theme.inline_note(
            "Budget <b>PRF Approval</b> resminya 1 hari kerja sementara median aktualnya 2 hari — "
            "sebagian besar \"terlambat\" di sini hanya telat satu hari. Kemungkinan targetnya "
            "yang perlu ditinjau, bukan orangnya.", block=True), unsafe_allow_html=True)

    st.markdown(theme.section_heading(4, "Dashboard Looker", "visualisasi yang sudah ada"),
                unsafe_allow_html=True)
    with theme.card("ov_looker", "Looker Studio", "Recruitment Dashboard"):
        # Looker tetap disematkan atas keputusan Navi. Filter site di atas TIDAK
        # ikut mengubah isinya — Looker punya filternya sendiri di dalam frame.
        if hasattr(st, "iframe"):
            st.iframe(C.LOOKER_EMBED_URL, height=C.LOOKER_EMBED_HEIGHT)
        else:
            st.components.v1.iframe(C.LOOKER_EMBED_URL, height=C.LOOKER_EMBED_HEIGHT,
                                    scrolling=True)
        st.markdown(theme.inline_note(
            "Filter site di atas hanya berlaku untuk kartu dan chart portal. Looker punya "
            "filter sendiri di dalam frame, dan angkanya dihitung terpisah — kalau ada yang "
            "berbeda dengan kartu di atas, yang di atas memakai budget SLA resmi per level.",
            block=True),
            unsafe_allow_html=True)

    with theme.card("ov_fail", "Di tahap mana kandidat gugur", "dari seluruh kandidat FAILED"):
        fail = M.failure_by_stage(df)
        if fail.empty:
            st.markdown(theme.empty_state("Tidak ada kegagalan tercatat", "—"),
                        unsafe_allow_html=True)
        else:
            st.markdown(theme.data_table(
                ["Tahap terakhir", "Gagal", "Porsi"],
                [[theme.esc(r.stage), n(r.n), f"{n(r.pct, 1)}%"] for r in fail.itertuples()],
                align="lrr",
            ), unsafe_allow_html=True)


# ===========================================================================
# ② RECRUITMENT ROOM — pilih site, salin link, lalu form tampil di halaman
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

    note = C.FORM_NOTES.get(site, "")

    if not url:
        with theme.card("rr_none", f'Form — {cfg["label"]}', note):
            st.markdown(theme.empty_state(
                "Formnya belum ada",
                f'Deployment Apps Script untuk <b>{theme.esc(cfg["label"])}</b> belum dibuat. '
                "Begitu URL-nya siap, tempel di <code>FORM_URLS</code> pada "
                "<code>config.py</code> — tidak ada tempat lain yang perlu diubah.",
                emoji="📝"), unsafe_allow_html=True)
        return

    with theme.card("rr_link", f'Link form — {cfg["label"]}',
                    f'{note} · klik ikon salin di ujung kanan'):
        st.code(url, language=None)
        b1, b2, _ = st.columns([1, 1, 2])
        with b1, st.container(key="rr_open"):
            st.link_button("Buka di tab baru", url, width="stretch")
        with b2, st.container(key="rr_reload"):
            if st.button("Muat ulang form", width="stretch", key="rr_reload_btn"):
                st.rerun()

    with theme.card("rr_embed", "Form", f'{cfg["label"]} · tersemat di halaman ini'):
        # st.iframe baru ada di Streamlit terbaru; components.v1.iframe dipertahankan
        # sebagai cadangan supaya aplikasi tetap jalan di versi yang lebih lama.
        if hasattr(st, "iframe"):
            st.iframe(url, height=C.FORM_EMBED_HEIGHT)
        else:
            st.components.v1.iframe(url, height=C.FORM_EMBED_HEIGHT, scrolling=True)
        st.markdown(theme.inline_note(
            "Kalau kotak di atas kosong, Apps Script memblokir penyematan. Perbaikannya satu "
            "baris di <code>doGet()</code> pada <code>Code.gs</code>: tambahkan "
            "<code>.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)</code>, "
            "lalu deploy ulang. Contoh lengkapnya ada di README.", warn=True, block=True),
            unsafe_allow_html=True)


# ===========================================================================
# ③ TRACKING KANDIDAT
# ===========================================================================
def page_tracking_candidate():
    df, sf, lt = data_or_stop()

    f1, f2, f3 = st.columns([1, 1, 2])
    with f1:
        site = st.selectbox("Site", ["Semua site"] + list(C.SITES), key="tc_site")
    with f2:
        status = st.selectbox("Status", ["Semua", "OPEN", "CLOSE", "FAILED"], key="tc_status")
    with f3:
        cari = st.text_input("Cari nama kandidat", key="tc_q",
                             placeholder="ketik sebagian nama…")

    pool = _site_filter(df, site)
    if status != "Semua":
        pool = pool[pool["status1"] == status]
    if cari.strip():
        pool = pool[pool["candidate_id"].str.contains(cari.strip(), case=False, na=False)]

    if pool.empty:
        st.markdown(theme.empty_state("Tidak ada yang cocok",
                                      "Longgarkan filter atau kata kuncinya."),
                    unsafe_allow_html=True)
        return

    # Kunci gabungan nama + Position ID. Versi lama memakai nama saja lalu
    # mengambil baris pertama, sehingga 31 orang yang melamar dua posisi selalu
    # melihat proses yang bukan miliknya.
    pilih = st.selectbox(f"Kandidat ({len(pool)} cocok)", sorted(pool["cand_key"]),
                         key="tc_pick")
    row = pool[pool["cand_key"] == pilih].iloc[0]
    stages = sf[sf["cand_key"] == pilih].sort_values("stage_no")
    ltrow = lt[lt["cand_key"] == pilih].iloc[0]

    hstat = str(row["status1"] or "").upper()
    st.markdown(theme.section_heading(
        1, theme.esc(row["candidate_id"]), theme.esc(row.get("position_name")),
        tag=theme.RESULT_LABEL.get(hstat, hstat)), unsafe_allow_html=True)

    if row["is_duplicate_name"]:
        st.markdown(theme.inline_note(
            "Nama ini muncul lebih dari sekali di database — biasanya karena melamar "
            "lebih dari satu posisi. Yang ditampilkan adalah baris untuk "
            f"<b>{theme.esc(row.get('position_id'))}</b>.", warn=True, block=True),
            unsafe_allow_html=True)

    st.markdown(theme.info_grid([
        ("Position ID", theme.esc(row.get("position_id")), ""),
        ("Departemen", theme.esc(row.get("departement")), ""),
        ("Divisi", theme.esc(row.get("divisi")), ""),
        ("Level", theme.esc(row["level"]), f'budget {C.total_budget(row["level"])} hari kerja'),
        ("Lokasi", theme.esc(row.get("loc")), ""),
        ("Sumber CV", theme.esc(row.get("source_cv")), ""),
    ]), unsafe_allow_html=True)

    # Progres dihitung terhadap tahap yang BERLAKU untuk level ini. Tanpa itu
    # tidak ada kandidat yang pernah mencapai 100% (temuan T-04).
    berlaku = stages[stages["applicable"]]
    selesai = int(berlaku["end"].notna().sum())
    st.markdown(theme.progress_bar(selesai, len(berlaku), failed=(hstat == "FAILED")),
                unsafe_allow_html=True)

    m = st.columns(4, gap="small")
    with m[0]:
        st.markdown(theme.kpi_card("Lead time berjalan", n(ltrow["lt_elapsed"]),
                                   "hari kerja, ujung ke ujung", emoji="⏱️", value_size=22),
                    unsafe_allow_html=True)
    with m[1]:
        st.markdown(theme.kpi_card("Jumlah durasi tahap", n(ltrow["lt_stage_sum"]),
                                   "hari kerja yang benar-benar dikerjakan",
                                   emoji="🧮", value_size=22, accent=theme.BRAND["navy"]),
                    unsafe_allow_html=True)
    with m[2]:
        idle = ltrow["lt_idle"]
        st.markdown(theme.kpi_card("Waktu menganggur", n(idle),
                                   "menunggu di antara tahap", emoji="⏸️", value_size=22,
                                   accent=(theme.STATUS["bad"] if (idle or 0) > 10
                                           else theme.STATUS["warn"])),
                    unsafe_allow_html=True)
    with m[3]:
        telat = int(ltrow["stages_late"])
        st.markdown(theme.kpi_card("Tahap terlambat", n(telat),
                                   f'dari {selesai} tahap selesai', emoji="⚠️", value_size=22,
                                   accent=(theme.STATUS["bad"] if telat else
                                           theme.STATUS["good"])),
                    unsafe_allow_html=True)

    with theme.card("tc_stages", "Tahap seleksi",
                    "lead time dalam hari kerja, dibandingkan budget level ini"):
        rows = []
        for s in stages.itertuples():
            if not s.applicable:
                status_code = "na"
            elif s.end is not pd.NaT and pd.notna(s.end):
                status_code = "done"
            elif pd.notna(s.start):
                status_code = "active"
            else:
                status_code = "idle"
            rows.append({
                "name": s.stage,
                "status": status_code,
                "start": s.start.date() if pd.notna(s.start) else None,
                "end": s.end.date() if pd.notna(s.end) else None,
                "lt": int(s.lt) if pd.notna(s.lt) else None,
                "budget": int(s.budget) if pd.notna(s.budget) else None,
                "sla": s.sla,
            })

        # Kandidat yang gagal ditandai di tahap terakhir yang ada datanya, supaya
        # terlihat di mana prosesnya berhenti.
        if hstat == "FAILED":
            terakhir = [i for i, r in enumerate(rows) if r["start"] or r["end"]]
            if terakhir:
                rows[terakhir[-1]]["status"] = "failed"

        st.markdown(theme.stage_table(rows), unsafe_allow_html=True)


# ===========================================================================
# ④ WEEKLY REPORT
# ===========================================================================
def _recruiter_extra() -> dict:
    """Pemetaan inisial tambahan yang Navi masukkan lewat panel di halaman ini."""
    return st.session_state.setdefault("recruiter_extra", {})


def page_weekly():
    df, sf, lt = data_or_stop()

    st.markdown(theme.section_heading(
        1, "Performance recruiter",
        "SLA dihitung dari tahap yang orang itu pegang, bukan dari PRF sampai akhir"),
        unsafe_allow_html=True)

    tahun = sorted(sf["screening_date"].dropna().dt.year.unique().tolist(), reverse=True)
    bulan_nama = ["Semua bulan", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
                  "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    f1, f2, _ = st.columns([1, 1, 2])
    with f1:
        thn = st.selectbox("Tahun", ["Semua tahun"] + [str(y) for y in tahun], key="wk_year")
    with f2:
        bln = st.selectbox("Bulan", bulan_nama, key="wk_month")

    dari = sampai = None
    if thn != "Semua tahun":
        y = int(thn)
        if bln != "Semua bulan":
            mnum = bulan_nama.index(bln)
            dari = pd.Timestamp(y, mnum, 1)
            sampai = dari + pd.offsets.MonthEnd(1)
        else:
            dari, sampai = pd.Timestamp(y, 1, 1), pd.Timestamp(y, 12, 31)

    perf = M.recruiter_performance(sf, dari, sampai, extra_map=_recruiter_extra())
    periode = "sepanjang waktu" if dari is None else f"{dari.date()} s/d {sampai.date()}"

    with theme.card("wk_perf", "Performance", f"periode screening CV · {periode}"):
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
                n(r.candidates),
                n(r.onboarding),
            ])
        st.markdown(theme.data_table(
            ["Nama", "SLA Actual", "SLA Budget", "Achievement", "Kandidat", "Onboarding"],
            baris, align="lrrrrr"), unsafe_allow_html=True)

        st.markdown(theme.inline_note(
            "<b>Achievement</b> = Budget ÷ Actual. Di atas 100% berarti lebih cepat dari target. "
            "Kolom <b>Onboarding</b> tidak bisa dijumlahkan ke bawah: satu kandidat ditangani "
            "beberapa PIC dan masing-masing mendapat kreditnya, jadi jumlahnya lebih besar dari "
            "hire sebenarnya. Kolom <b>Kandidat</b> disertakan supaya Achievement bisa dibaca "
            "adil — orang yang hanya memegang screening wajar punya angka jauh lebih tinggi "
            "daripada yang memegang offering sampai MCU.", block=True), unsafe_allow_html=True)

    if auth.can_do("edit_recruiter"):
        with st.expander("Kelola recruiter — petakan inisial ke nama lengkap"):
            st.markdown(theme.inline_note(
                "Database lama memakai inisial, tim sekarang memakai nama lengkap. Pemetaan di "
                "sini berlaku untuk sesi ini saja. Supaya permanen, tambahkan ke "
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
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("Tambahkan", type="primary", width="stretch", key="wk_add"):
                    if ini.strip() and nm.strip():
                        _recruiter_extra()[ini.strip().upper()] = nm.strip()
                        st.rerun()
                    else:
                        st.warning("Isi inisial dan nama lengkapnya.")

            if _recruiter_extra():
                st.markdown(theme.stat_list(
                    [(k, v) for k, v in _recruiter_extra().items()]), unsafe_allow_html=True)

    st.markdown(theme.section_heading(2, "New Hire", "onboarding per departemen per bulan"),
                unsafe_allow_html=True)
    thn_nh = int(thn) if thn != "Semua tahun" else (tahun[0] if tahun else None)
    with theme.card("wk_nh", "New Hire", f"tahun {thn_nh}" if thn_nh else "seluruh data"):
        nh = M.new_hire_matrix(df, thn_nh)
        if nh.empty:
            st.markdown(theme.empty_state("Belum ada onboarding", "—"), unsafe_allow_html=True)
        else:
            kolom = list(nh.columns)
            baris = [[theme.esc(r[0])] + [n(v) for v in r[1:]] for r in nh.values.tolist()]
            st.markdown(theme.data_table(kolom, baris[:-1], total_row=baris[-1],
                                         align="l" + "r" * (len(kolom) - 1)),
                        unsafe_allow_html=True)

    st.markdown(theme.section_heading(3, "On Progress", "kandidat yang perlu ditindaklanjuti"),
                unsafe_allow_html=True)
    panels = M.on_progress(_site_filter(df, "Semua site"))
    cols = st.columns(3, gap="small")
    for col, (nama, sel) in zip(cols, panels.items()):
        with col, theme.card(f"wk_onp_{nama}", nama, f"{len(sel)} kandidat"):
            if sel.empty:
                st.markdown(theme.empty_state("Kosong", "Tidak ada yang di tahap ini.",
                                              emoji="—"), unsafe_allow_html=True)
            else:
                st.markdown(theme.data_table(
                    ["Kandidat", "Posisi", "Site", "Tahap"],
                    [[theme.esc(r.candidate_id), theme.esc(r.position_name),
                      theme.esc(r.loc), theme.esc(r.last_progress)]
                     for r in sel.itertuples()], align="llll"), unsafe_allow_html=True)

    st.markdown(theme.section_heading(4, "Ringkasan per site", "pipeline dan hasilnya"),
                unsafe_allow_html=True)
    with theme.card("wk_sum", "Summary", "per site dan departemen"):
        summ = M.department_summary(df)
        st.markdown(theme.data_table(
            ["Site", "Departemen", "Kandidat", "Hire", "Berjalan", "Gagal", "Hire rate"],
            [[theme.esc(r.loc), theme.esc(r.departement), n(r.kandidat), n(r.hire),
              n(r.berjalan), n(r.gagal), f"{n(r.hire_rate, 1)}%"]
             for r in summ.itertuples()], align="llrrrrr"), unsafe_allow_html=True)
        st.markdown(theme.inline_note(
            "Kolom <b>Need</b> belum ada di sini. Angka kebutuhan berasal dari weekly report, "
            "dan portal belum menyambungnya — menampilkan kolom Need yang kosong akan lebih "
            "menyesatkan daripada tidak menampilkannya.", block=True), unsafe_allow_html=True)


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
        "overview": ("Overview", "Kondisi pipeline rekrutmen seluruh site"),
        "weekly": ("Weekly Report", "Summary, New Hire, On Progress, dan performance recruiter"),
        "tracking_candidate": ("Tracking Kandidat", "Proses seleksi per kandidat, tahap demi tahap"),
        "tracking_position": ("Tracking Posisi", "Pemenuhan per Position ID"),
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
        page_todo("Tracking Posisi", [
            "Semua kandidat yang pernah diproses untuk satu Position ID",
            "Umur PRF dan status pemenuhannya",
            "Posisi yang belum tersentuh sama sekali",
        ], "Fase 4")


main()
