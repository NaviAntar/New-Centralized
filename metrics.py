"""
metrics.py — satu-satunya tempat angka rekrutmen dihitung.

Setiap halaman memanggil modul ini; tidak ada halaman yang boleh menghitung
lead time atau status SLA sendiri. Itu yang membuat versi lama menampilkan dua
angka berbeda untuk orang yang sama (`tot_lt` di halaman posisi vs `total_lt`
di halaman kandidat — temuan T-05).

Modul ini murni pandas: tidak mengimpor streamlit, jadi bisa dites dari skrip
biasa. Cache ada di lapisan aplikasi.

--- Cara lead time dihitung ---------------------------------------------------
Durasi diukur dalam HARI KERJA dan bersifat inklusif: mulai dan selesai di hari
kerja yang sama = 1 hari. Sabtu, Minggu, dan libur nasional tidak dihitung.

Ini bukan definisi baru — rumusnya dicocokkan ulang terhadap kolom LT yang
sudah ada di spreadsheet dan cocok 100% di sebelas tahap. Portal memakai
konvensi yang sama supaya angkanya bisa langsung dicocokkan dengan angka yang
biasa dilihat tim.

Modul menyediakan DUA ukuran yang sengaja dipisah:

  lt_stage_sum  jumlah durasi tahap. Ini definisi yang dipakai tim untuk
                menilai kinerja PIC — orang hanya bertanggung jawab atas tahap
                yang ia pegang.

  lt_elapsed    selisih tanggal ujung ke ujung. Ini yang dirasakan user dan
                manajemen, dan selalu lebih besar karena mencakup waktu tunggu
                ANTAR tahap.

Selisih keduanya (`lt_idle`) adalah waktu proses menganggur. Versi lama hanya
punya angka pertama dan menyebutnya "total lead time", sehingga keterlambatan
nyata tidak pernah terlihat (temuan T-01).
"""
from __future__ import annotations

import pandas as pd

import config as C
from theme import MAIN_FUNNEL, STAGE_ORDER

# ---------------------------------------------------------------------------
# Peta kolom: satu tahap -> kolom-kolom yang mewakilinya di fix_centralized.
# Ini SATU-SATUNYA tempat nama kolom database disebut. Kalau spreadsheet
# berubah, cukup ubah di sini.
# ---------------------------------------------------------------------------
# Pasangan tanggal di bawah BUKAN tebakan. Tiap pasangan diuji terhadap kolom
# LT yang sudah ada di spreadsheet memakai rumus hari kerja + kalender libur,
# dan hanya pasangan yang cocok 100% yang dipakai. Dua di antaranya berbeda dari
# dugaan awal:
#   MCU              -> berakhir di mcu_issue_date, bukan mcu_date
#   One Month Notice -> date_fit sampai date_onboarding (inilah masa notice
#                       30 hari; versi lama salah melabelinya "Onboarding")
STAGE_COLUMNS = {
    #                    start                    end                        lt sheet        sla sheet  result
    "PRF Approval":     ("start_prf_routing",     "complete_prf_routing",    "lt_prf",         "sla1",  None),
    "Screening CV":     ("start_screening_cv",    "complete_screening_cv",   "lt_screening",   "sla2",  "result_screening_cv"),
    "Interview HR":     ("start_interview_hr",    "complete_interview_hr",   "lt_hr_interview", "sla3", "result_interview_hr"),
    "Interview User":   ("start_interview_user",  "complete_interview_user", "lt_user_interview", "sla4", "result_interview_user"),
    "Technical Test":   ("start_technical_test",  "complete_technical_test", "lt_tech_test",   "sla11", "result_technical_test"),
    "Psychotest":       ("start_psychotest",      "complete_psychotest",     "lt_psikotest",   "sla5",  "result_psychotest"),
    "Offering":         ("start_offering",        "complete_offering",       "lt_offering",    "sla6",  "result_offering"),
    "MCU":              ("start_mcu",             "mcu_issue_date",          "lt_mcu",         "sla7",  None),
    "Review MCU":       ("start_review_mcu",      "review_mcu",              "lt_review_mcu",  "sla8",  None),
    "FU MCU":           ("start_fu_mcu",          "complete_fu_mcu",         "lt_fu_mcu",      "sla9",  "result_fu_mcu"),
    "One Month Notice": ("date_fit",              "date_onboarding",         "lt_omn",         "sla10", None),
    "Onboarding":       ("date_onboarding",       "date_onboarding",         None,             None,    None),
}

# Tanggal paling awal dan paling akhir dari seluruh proses, dipakai menghitung
# lt_elapsed. PRF sengaja TIDAK jadi titik awal: kolomnya hanya terisi di 422
# dari 1.396 baris, jadi memakainya akan membuat mayoritas kandidat kosong.
ELAPSED_START = "start_screening_cv"
ELAPSED_END = "date_onboarding"

_ID_COLS = ["candidate_id", "position_id", "position_name", "departement",
            "divisi", "level", "loc", "status1", "last_progress", "source_cv"]


# ===========================================================================
# Normalisasi
# ===========================================================================
def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Bersihkan frame mentah fix_centralized jadi tabel kandidat yang layak pakai.

    Yang dikerjakan:
      - buang baris kosong (sheet punya ~560 baris tanpa kandidat sama sekali)
      - normalisasi nama kolom & nilai teks
      - parse semua kolom tanggal
      - bangun kunci unik `cand_key` dan tandai duplikat (temuan T-03)
    """
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]

    if "candidate_id" not in df.columns:
        raise ValueError(
            "Column 'candidate_id' is missing. Most likely the fetch returned a "
            "tab other than fix_centralized — check the gid / tab name in config.py."
        )

    df = df[df["candidate_id"].notna() & (df["candidate_id"].astype(str).str.strip() != "")]
    df = df.reset_index(drop=True)

    for col in _ID_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": None, "": None})

    # Identitas ditambal SEBELUM apa pun dihitung: di fix_centralized kolom
    # position_name / departement / level / loc adalah lookup yang belum ditarik
    # ke bawah untuk baris baru. Kalau dibiarkan, kandidat SSCP tercatat tanpa
    # site (dan dulu ikut terhitung sebagai BPN) dan tanpa departemen.
    # fix_centralized tidak punya kolom nomor telepon sama sekali; kolomnya
    # disiapkan kosong supaya penambal identitas punya tempat mengisinya dari
    # sheet Backend Monitoring.
    if "phone" not in df.columns:
        df["phone"] = None
    df = _tambal_identitas(df)

    if "loc" in df.columns:
        df["loc"] = df["loc"].str.upper()
    if "status1" in df.columns:
        df["status1"] = df["status1"].str.upper()

    tanggal = {c for s, (a, b, *_r) in STAGE_COLUMNS.items() for c in (a, b)}
    # Dipakai panel On Progress tapi tidak masuk peta tahap, jadi harus
    # disebut terpisah — kalau tidak, perbandingan tanggalnya diam-diam gagal.
    tanggal |= {"ol_sent_to_candidate", "mcu_issue_date", "date_fit", "sent_mcu_to_doctor"}
    for col in tanggal:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # Kunci unik. Nama saja tidak cukup: 31 nama muncul dua kali karena orang
    # yang sama melamar lebih dari satu posisi. Versi lama memakai nama sebagai
    # kunci lalu mengambil baris pertama, jadi 31 orang melihat proses yang
    # bukan miliknya.
    pos = df["position_id"].fillna("—") if "position_id" in df.columns else "—"
    df["cand_key"] = df["candidate_id"].astype(str) + " · " + pos.astype(str)
    df["is_duplicate_name"] = df["candidate_id"].duplicated(keep=False)

    # Kalau kunci gabungan pun masih kembar, bedakan dengan nomor urut supaya
    # tidak ada dua baris yang tidak bisa dipilih terpisah di dropdown.
    dup_key = df["cand_key"].duplicated(keep=False)
    if dup_key.any():
        seq = df.groupby("cand_key").cumcount() + 1
        df.loc[dup_key, "cand_key"] = (
            df.loc[dup_key, "cand_key"] + " #" + seq[dup_key].astype(str)
        )

    df["level"] = df.get("level").fillna(C.LEVEL_FALLBACK) if "level" in df.columns else C.LEVEL_FALLBACK

    # Talent pool ditandai lewat kolom Result di tahap mana pun, bukan lewat satu
    # kolom khusus — form Apps Script menuliskannya di tahap tempat keputusan itu
    # diambil, dan tahapnya berbeda-beda per orang.
    df["talent_pool"] = _talent_pool_mask(df)
    df["talent_pool_stage"] = _talent_pool_stage(df)

    # Kolom departemen dibereskan di satu tempat, sebelum dipakai halaman mana
    # pun — kalau tidak, tiap laporan harus mengulang perbaikan yang sama.
    if "departement" in df.columns:
        df["departement"] = repair_department(df)
    return df


_ROW_MASTER: dict = {}
_TAMBAL_KOLOM = ("position_name", "departement", "level", "loc", "phone")


def set_row_master(bm: "pd.DataFrame | None") -> None:
    """Pasang sheet Backend Monitoring sebagai penambal identitas kandidat.

    Dipanggil sekali sebelum prepare(). Kuncinya nama + Position ID, sama dengan
    cand_key, supaya orang yang melamar dua posisi tidak tertukar.
    """
    global _ROW_MASTER
    _ROW_MASTER = {}
    if bm is None or getattr(bm, "empty", True):
        return
    for kol in ("candidate_id", "position_id"):
        if kol not in bm.columns:
            return
    d = bm.copy()
    d["_k"] = (d["candidate_id"].astype(str).str.strip().str.upper() + " | "
               + d["position_id"].astype(str).str.strip().str.upper())
    d = d.drop_duplicates("_k", keep="last").set_index("_k")
    ada = [c for c in _TAMBAL_KOLOM if c in d.columns]
    _ROW_MASTER = d[ada].to_dict("index")


def _tambal_identitas(df: pd.DataFrame) -> pd.DataFrame:
    """Isi position_name / departement / level / loc yang kosong dari sheet
    Backend Monitoring. Nilai yang sudah ada di fix_centralized tidak disentuh —
    penambalan ini hanya mengisi lubang, bukan menimpa.
    """
    if not _ROW_MASTER or "position_id" not in df.columns:
        return df
    kunci = (df["candidate_id"].astype(str).str.strip().str.upper() + " | "
             + df["position_id"].astype(str).str.strip().str.upper())
    for kol in _TAMBAL_KOLOM:
        if kol not in df.columns:
            continue
        kosong = df[kol].isna() | df[kol].astype(str).str.strip().isin(
            ["", "nan", "None", "-"])
        if not kosong.any():
            continue
        isi = kunci[kosong].map(
            lambda k: (_ROW_MASTER.get(k) or {}).get(kol))
        df.loc[kosong, kol] = isi
    return df


_POSITION_MASTER: dict = {"by_id": {}, "by_name": {}, "valid": set()}


def set_position_master(master: dict | None) -> None:
    """Pasang master posisi -> departemen. Panggil sekali saat startup."""
    global _POSITION_MASTER
    _POSITION_MASTER = master or {"by_id": {}, "by_name": {}, "valid": set()}


# Kolom Result tiap tahap, dipakai mendeteksi talent pool. Diambil dari peta
# tahap supaya tidak ada daftar kolom kedua yang bisa ketinggalan saat peta
# tahapnya berubah.
_RESULT_COLS = [r for *_x, r in STAGE_COLUMNS.values() if r]


def _talent_pool_mask(df: pd.DataFrame) -> pd.Series:
    """True kalau ada tahap yang hasilnya TALENT POOL."""
    hasil = pd.Series(False, index=df.index)
    for kol in _RESULT_COLS:
        if kol in df.columns:
            nilai = df[kol].astype(str).str.strip().str.upper()
            hasil |= nilai.eq(C.TALENT_POOL_RESULT)
    return hasil


def _talent_pool_stage(df: pd.DataFrame) -> pd.Series:
    """Tahap tempat kandidat masuk talent pool — tahap TERAKHIR yang menandainya.

    Dipakai di tabel Talent Pool: "berhenti di Interview User" memberi tahu
    seberapa jauh orangnya sudah dinilai, dan itu yang menentukan seberapa siap
    dia dipanggil lagi.
    """
    hasil = pd.Series(pd.NA, index=df.index, dtype=object)
    for tahap, (*_x, kol) in STAGE_COLUMNS.items():
        if not kol or kol not in df.columns:
            continue
        cocok = df[kol].astype(str).str.strip().str.upper().eq(C.TALENT_POOL_RESULT)
        hasil = hasil.mask(cocok, tahap)
    return hasil


def talent_pool(df: pd.DataFrame, sites=None) -> pd.DataFrame:
    """Daftar kandidat talent pool, siap ditampilkan.

    Kolomnya sesuai permintaan Navi — nama, nomor HP, posisi yang dilamar,
    departemen — ditambah tiga yang membuat daftarnya bisa langsung dipakai
    menelepon orang: SITE (menentukan siapa yang menghubungi), LEVEL (menentukan
    posisi apa yang pantas ditawarkan), dan TAHAP tempat dia masuk pool (semakin
    jauh tahapnya, semakin sedikit seleksi ulang yang perlu diulang).
    """
    d = df[df["talent_pool"]].copy()
    if sites:
        d = d[d["loc"].isin(C.loc_values_for(sites))]
    if d.empty:
        return pd.DataFrame(columns=["cand_key", "candidate_id", "phone",
                                     "position_name", "departement", "loc",
                                     "level", "stage"])
    d["stage"] = d["talent_pool_stage"]
    kol = ["cand_key", "candidate_id", "phone", "position_name", "departement",
           "loc", "level", "stage"]
    return d[[c for c in kol if c in d.columns]].sort_values(
        ["loc", "departement", "candidate_id"])


def repair_department(df: pd.DataFrame) -> pd.Series:
    """Kolom departemen yang sudah dibersihkan.

    Sebagian baris di database mengisi kolom `departement` dengan NAMA POSISI —
    "Foreman - DMS Operation", "Supervisor - HV Electrical", dan sejenisnya —
    sehingga di laporan New Hire nama posisi muncul seolah-olah departemen.

    Urutan penyelamatannya:
      1. Nilai yang memang ada di daftar departemen resmi dipakai apa adanya.
      2. Kalau tidak, cari departemen lewat Position ID di master MPP 2026.
      3. Kalau tidak ketemu, cari lewat nama posisi.
      4. Kalau tetap tidak ketemu, cari posisi yang sama di baris lain database
         yang departemennya sudah benar.
      5. Sisanya dikumpulkan ke satu baris berlabel jelas — BUKAN dibiarkan
         tampil sebagai departemen palsu.
    """
    dept = df["departement"].astype(str).str.strip().replace({"nan": None, "": None})
    valid = set(_POSITION_MASTER.get("valid") or set())
    if len(valid) < 20:
        # Master gagal diambil atau cuma terbaca sepotong — kalau tetap dipakai,
        # SEMUA departemen asli ikut dianggap tidak sah dan laporan New Hire
        # runtuh jadi satu baris. Acuan cadangannya: nilai yang paling sering
        # dipakai di database itu sendiri.
        valid |= set(dept.value_counts()[lambda s: s >= 3].index)

    sah = dept.isin(valid)
    hasil = dept.where(sah)

    pid = df.get("position_id", pd.Series(index=df.index, dtype=object))
    pnm = df.get("position_name", pd.Series(index=df.index, dtype=object))
    pid = pid.astype(str).str.strip()
    pnm = pnm.astype(str).str.strip()

    # Sheet Backend Monitoring lebih dulu: itu departemen yang tim lihat sendiri
    # di dashboard monitoring, jadi paling tepat untuk baris yang di
    # fix_centralized malah terisi nama posisi.
    if _ROW_MASTER:
        kunci = (df["candidate_id"].astype(str).str.strip().str.upper()
                 + " | " + pid.str.upper())
        hasil = hasil.fillna(kunci.map(
            lambda k: (_ROW_MASTER.get(k) or {}).get("departement")))

    hasil = hasil.fillna(pid.map(_POSITION_MASTER.get("by_id", {})))
    hasil = hasil.fillna(pnm.map(_POSITION_MASTER.get("by_name", {})))

    # Posisi yang sama, tapi departemennya benar di baris lain.
    benar = df[sah]
    if len(benar):
        peta = (benar.assign(_p=pid[sah])
                     .groupby("_p")["departement"]
                     .agg(lambda s: s.mode().iat[0] if len(s.mode()) else None))
        hasil = hasil.fillna(pid.map(peta))

    # Satu departemen yang ditulis dengan beberapa ejaan disatukan paling akhir,
    # supaya tidak muncul dua baris untuk departemen yang sama.
    hasil = hasil.replace(getattr(C, "DEPT_ALIASES", {}))
    return hasil.fillna(C.DEPT_UNMAPPED_LABEL)


_HOLIDAYS: "np.ndarray | None" = None


def set_holidays(dates) -> None:
    """Pasang kalender libur (dari sheet Backend). Panggil sekali saat startup."""
    global _HOLIDAYS
    import numpy as np
    parsed = pd.to_datetime(pd.Series(list(dates)), errors="coerce").dropna()
    _HOLIDAYS = parsed.dt.normalize().values.astype("datetime64[D]")


def _holidays():
    global _HOLIDAYS
    if _HOLIDAYS is None:
        set_holidays(C.HOLIDAYS_FALLBACK)
    return _HOLIDAYS


def working_days(start: pd.Series, end: pd.Series) -> pd.Series:
    """Durasi dalam HARI KERJA, inklusif — mulai & selesai di hari sama = 1.

    Sabtu, Minggu, dan libur nasional tidak dihitung. Rumus ini diverifikasi
    terhadap kolom LT yang sudah ada di spreadsheet: cocok 100% di sebelas
    tahap. Jadi angka portal bisa dicocokkan langsung dengan angka yang biasa
    dilihat tim — bukan definisi baru yang bersaing.

    Tanggal terbalik (selesai mendahului mulai) menghasilkan nilai negatif dan
    sengaja TIDAK dipaksa jadi nol, supaya kesalahan input tetap terlihat.
    """
    import numpy as np
    out = pd.Series(np.nan, index=start.index, dtype="float64")
    mask = start.notna() & end.notna()
    if not mask.any():
        return out
    s = start[mask].dt.normalize().values.astype("datetime64[D]")
    e = (end[mask].dt.normalize() + pd.Timedelta(days=1)).values.astype("datetime64[D]")
    fwd = e >= s
    days = np.empty(len(s), dtype="float64")
    days[fwd] = np.busday_count(s[fwd], e[fwd], holidays=_holidays())
    # Untuk tanggal terbalik, hitung mundur lalu beri tanda negatif.
    if (~fwd).any():
        back = np.busday_count(
            (end[mask][~fwd].dt.normalize()).values.astype("datetime64[D]"),
            (start[mask][~fwd].dt.normalize() + pd.Timedelta(days=1)).values.astype("datetime64[D]"),
            holidays=_holidays(),
        )
        days[~fwd] = -back
    out[mask] = days
    return out


# ===========================================================================
# Tabel panjang: 1 baris per kandidat per tahap
# ===========================================================================
def stage_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Ubah tabel wide jadi long — bentuk yang dipakai hampir semua metrik.

    Kolom hasil: cand_key, candidate_id, position_name, departement, level, loc,
    status1, stage, stage_no, start, end, lt (inklusif, dihitung dari tanggal),
    lt_sheet, budget, applicable, sla, pic_initial, pic_name, result.
    """
    rows = []
    for stage in STAGE_ORDER:
        s_col, e_col, lt_col, sla_col, res_col = STAGE_COLUMNS[stage]
        if s_col not in df.columns:
            continue

        start = df[s_col]
        end = df[e_col] if e_col in df.columns else pd.Series(pd.NaT, index=df.index)

        block = pd.DataFrame({
            "cand_key": df["cand_key"],
            "candidate_id": df["candidate_id"],
            "position_id": df.get("position_id"),
            "position_name": df.get("position_name"),
            "departement": df.get("departement"),
            "level": df["level"],
            "loc": df.get("loc"),
            "status1": df.get("status1"),
            "stage": stage,
            "stage_no": STAGE_ORDER.index(stage) + 1,
            "start": start,
            "end": end,
            "screening_date": df.get(ELAPSED_START),
        })

        block["lt"] = working_days(start, end)
        block["lt_sheet"] = (pd.to_numeric(df[lt_col], errors="coerce")
                             if lt_col and lt_col in df.columns else pd.NA)
        block["budget"] = df["level"].map(lambda lv, st=stage: C.stage_budget(lv, st))
        block["applicable"] = block["budget"].notna()
        block["result"] = (df[res_col].astype(str).str.strip().str.upper()
                           if res_col and res_col in df.columns else None)

        pic_col = C.STAGE_PIC_COLUMN.get(stage)
        if pic_col and pic_col in df.columns:
            pic = df[pic_col].astype(str).str.strip().str.upper()
            # Angka serial tanggal Excel yang salah tempel dibuang di sini,
            # supaya tidak muncul sebagai recruiter baru di tabel Performance.
            block["pic_initial"] = pic.where(pic.map(C.is_valid_initial))
        else:
            block["pic_initial"] = None

        rows.append(block)

    out = pd.concat(rows, ignore_index=True)
    out["sla"] = _sla_state(out)
    out["over_days"] = (out["lt"] - out["budget"]).where(out["lt"].notna() & out["budget"].notna())
    return out


def _sla_state(sf: pd.DataFrame) -> pd.Series:
    """Status SLA dihitung ulang dari tanggal + budget resmi per level.

    Sengaja TIDAK memakai kolom sla1..sla11 dari sheet: kolom itu dibandingkan
    terhadap budget yang salah (temuan T-01b), jadi hampir semuanya "Ontime".
    """
    state = pd.Series("", index=sf.index, dtype="object")
    has_budget = sf["budget"].notna()
    done = sf["lt"].notna() & has_budget
    state[done & (sf["lt"] <= sf["budget"])] = "Ontime"
    state[done & (sf["lt"] > sf["budget"])] = "Late"
    running = sf["start"].notna() & sf["end"].isna() & has_budget
    state[running] = "Running"
    return state


# ===========================================================================
# Lead time per kandidat
# ===========================================================================
def lead_time(df: pd.DataFrame, sf: pd.DataFrame | None = None) -> pd.DataFrame:
    """Tiga ukuran lead time per kandidat + status terhadap budget resmi."""
    sf = stage_frame(df) if sf is None else sf

    stage_sum = sf.groupby("cand_key")["lt"].sum(min_count=1)
    stages_done = sf[sf["end"].notna()].groupby("cand_key").size()
    stages_late = sf[sf["sla"] == "Late"].groupby("cand_key").size()

    out = pd.DataFrame({"cand_key": df["cand_key"]}).set_index("cand_key")
    out["level"] = df.set_index("cand_key")["level"]
    out["status1"] = df.set_index("cand_key")["status1"]
    out["lt_stage_sum"] = stage_sum
    idx = df.set_index("cand_key")
    out["lt_elapsed"] = (working_days(idx[ELAPSED_START], idx[ELAPSED_END])
                         if ELAPSED_END in df.columns else pd.NA)
    out["lt_idle"] = out["lt_elapsed"] - out["lt_stage_sum"]
    out["budget_total"] = out["level"].map(C.total_budget)
    out["stages_done"] = stages_done.reindex(out.index).fillna(0).astype(int)
    out["stages_late"] = stages_late.reindex(out.index).fillna(0).astype(int)

    over = out["lt_elapsed"] > out["budget_total"]
    out["lt_status"] = pd.Series("", index=out.index, dtype="object")
    out.loc[out["lt_elapsed"].notna() & ~over, "lt_status"] = "Onbudget"
    out.loc[out["lt_elapsed"].notna() & over, "lt_status"] = "Overbudget"

    # Tanggal terbalik. Ada 13 baris seperti ini di data (terendah -113 hari);
    # ditandai supaya bisa ditampilkan sebagai daftar perbaikan, bukan diam-diam
    # ikut merusak rata-rata.
    out["date_error"] = (out["lt_elapsed"] < 0) | (sf.groupby("cand_key")["lt"].min() < 0)
    return out.reset_index()


# ===========================================================================
# Ringkasan untuk Overview
# ===========================================================================
def sla_summary(sf: pd.DataFrame) -> pd.DataFrame:
    """Tingkat keterlambatan per tahap, diurutkan dari yang paling parah."""
    done = sf[sf["sla"].isin(["Ontime", "Late"])]
    g = done.groupby("stage").agg(
        n=("sla", "size"),
        late=("sla", lambda s: (s == "Late").sum()),
        median_lt=("lt", "median"),
        budget=("budget", "median"),
    )
    g["late_pct"] = (g["late"] / g["n"] * 100).round(1)
    g["stage_no"] = [STAGE_ORDER.index(s) + 1 for s in g.index]
    return g.reset_index().sort_values("late_pct", ascending=False)


def funnel(sf: pd.DataFrame) -> pd.DataFrame:
    """Jumlah kandidat yang menyentuh tiap tahap, mengikuti urutan proses.

    Hanya menghitung tahap yang BERLAKU untuk kandidat itu, sehingga konversi
    tidak lagi melompat di atas 100% seperti pada versi lama (Technical Test
    hanya untuk Non Staff, tapi dulu ikut jadi pembagi untuk semua orang).
    """
    touched = sf[sf["applicable"] & sf["start"].notna()]
    if touched.empty:
        return pd.DataFrame(columns=["stage", "stage_no", "n", "conv_pct",
                                     "of_base_pct", "drop"])

    # Dihitung sebagai "kandidat yang MINIMAL sampai tahap ini", memakai tahap
    # terjauh yang pernah ia sentuh. Menghitung sentuhan mentah per tahap tidak
    # bisa dipakai: banyak kandidat melewati Psikotes dan sebagian besar tidak
    # punya tanggal PRF, sehingga angkanya naik-turun dan konversi melompat di
    # atas 100% — persis yang terjadi di versi lama.
    #
    # PRF Approval dikeluarkan dari funnel: itu persetujuan permintaan, bukan
    # tahap seleksi kandidat, dan kolomnya cuma terisi di 422 dari 1.396 baris.
    furthest = touched.groupby("cand_key")["stage_no"].max()
    rows = []
    base = None
    prev = None
    for stage in MAIN_FUNNEL:
        i = STAGE_ORDER.index(stage) + 1
        n = int((furthest >= i).sum())
        if base is None:
            base = n
        rows.append({
            "stage": stage,
            "stage_no": i,
            "n": n,
            "conv_pct": round(n / prev * 100, 1) if prev else None,
            "of_base_pct": round(n / base * 100, 1) if base else None,
            "drop": (prev - n) if prev is not None else None,
        })
        prev = n
    return pd.DataFrame(rows)


def failure_by_stage(df: pd.DataFrame) -> pd.DataFrame:
    """Di tahap mana kandidat gugur."""
    failed = df[df["status1"] == "FAILED"]
    g = failed["last_progress"].value_counts().rename_axis("stage").reset_index(name="n")
    total = g["n"].sum()
    g["pct"] = (g["n"] / total * 100).round(1) if total else 0
    return g


def source_effectiveness(df: pd.DataFrame) -> pd.DataFrame:
    """Hire rate per sumber CV."""
    if "source_cv" not in df.columns:
        return pd.DataFrame(columns=["source_cv", "n", "hired", "rate"])
    g = df.assign(_h=df["status1"] == "CLOSE").groupby("source_cv").agg(
        n=("cand_key", "size"), hired=("_h", "sum"))
    g["rate"] = (g["hired"] / g["n"] * 100).round(1)
    return g.reset_index().sort_values("rate", ascending=False)


# ===========================================================================
# Performance recruiter — tabel di halaman Weekly Report
# ===========================================================================
def recruiter_name(initial: str, extra_map: dict | None = None) -> str | None:
    """Isi kolom PIC -> nama di roster. None kalau bukan orang roster.

    Logikanya ada di config.resolve_recruiter(): kolom PIC berisi campuran
    inisial lama dan nama lengkap dengan ejaan yang tidak seragam.
    """
    return C.resolve_recruiter(initial, extra_map)


def recruiter_owned(sf: pd.DataFrame, extra_map: dict | None = None) -> pd.DataFrame:
    """Peta kandidat -> recruiter yang menanganinya.

    Seseorang dianggap menangani sebuah kandidat kalau namanya muncul sebagai PIC
    di tahap mana pun. Satu kandidat bisa dimiliki lebih dari satu orang; itu
    disengaja, karena proses rekrutmen memang dikerjakan bergantian.
    """
    pic = sf[sf["pic_initial"].notna()][["cand_key", "pic_initial", "loc",
                                         "screening_date"]].copy()
    pic["name"] = pic["pic_initial"].map(lambda i: recruiter_name(i, extra_map))
    pic["name"] = pic["name"].fillna(C.OTHER_RECRUITER_LABEL)
    pic = pic.drop_duplicates(["cand_key", "name"])

    # Kandidat yang TIDAK punya PIC di tahap mana pun tetap harus punya pemilik,
    # kalau tidak SLA-nya hilang dari tabel dan baris "PIC Site …" tampil kosong
    # padahal orangnya ada. Yang seperti ini dikelompokkan per site.
    yatim = sf[~sf["cand_key"].isin(set(pic["cand_key"]))]
    if len(yatim):
        yatim = (yatim[["cand_key", "loc", "screening_date"]]
                 .drop_duplicates("cand_key").copy())
        yatim["pic_initial"] = None
        yatim["name"] = (yatim["loc"].map(C.site_pic_label)
                         .fillna(C.OTHER_RECRUITER_LABEL))
        pic = pd.concat([pic, yatim[pic.columns]], ignore_index=True)
    return pic


def _screening_owner(sf: pd.DataFrame, extra_map, date_from=None, date_to=None,
                     sites=None) -> pd.DataFrame:
    """Kandidat beserta PIC Screening CV-nya — dasar hitungan Kandidat & Onboarding.

    Screening CV dipilih sebagai penentu kepemilikan karena itu pintu masuk
    kandidat: tiap kandidat punya tepat satu PIC screening, jadi tidak ada yang
    terhitung dua kali.

    Frame yang dikembalikan membawa DUA tanggal — screening dan onboarding —
    karena kedua kolom di tabel Performance bertumpu pada tanggal yang berbeda;
    lihat recruiter_performance().
    """
    scr = sf[sf["stage"] == "Screening CV"].copy()
    ob = (sf[sf["stage"] == "Onboarding"].drop_duplicates("cand_key")
            .set_index("cand_key")["end"])
    scr["onboarding_date"] = scr["cand_key"].map(ob)

    # Kandidat yang PIC screening-nya kosong TIDAK dibuang. Dulu baris ini
    # disaring keluar, dan 21 dari 127 orang yang onboarding Jun-Sep 2026 hilang
    # dari tabel Performance tanpa jejak — 18 di antaranya SSCP. Sekarang
    # dikelompokkan per site: di lapangan memang site yang menanganinya.
    nama = scr["pic_initial"].map(lambda i: recruiter_name(i, extra_map))
    kosong = scr["pic_initial"].isna() | ~scr["pic_initial"].map(C.is_valid_initial)
    scr["name"] = nama.where(~kosong, scr["loc"].map(C.site_pic_label))
    scr["name"] = scr["name"].fillna(C.OTHER_RECRUITER_LABEL)

    if sites:
        scr = scr[scr["loc"].isin(C.loc_values_for(sites))]
    return scr.drop_duplicates(["cand_key", "name"])


def recruiter_performance(sf: pd.DataFrame, date_from=None, date_to=None,
                          extra_map: dict | None = None, sites=None) -> pd.DataFrame:
    """Tabel performance per recruiter.

    Cara hitungnya, sesuai arahan Navi:

      1. Kumpulkan kandidat yang ditangani orang itu.
      2. Untuk SETIAP tahap proses — dari PRF Approval sampai Onboarding —
         hitung rata-rata lead time dan rata-rata budget di antara kandidat tadi.
      3. Jumlahkan rata-rata itu lintas tahap. Tidak dibagi lagi.

    Yang penting di langkah 2: SELURUH tahap ikut, bukan hanya tahap yang punya
    kolom PIC di database. Versi sebelumnya hanya menghitung tujuh tahap ber-PIC,
    sehingga One Month Notice yang budget-nya saja 30 hari ikut terbuang dan
    total budget keluar cuma ~20 hari — jelas tidak masuk akal untuk proses yang
    targetnya 60+ hari. Sekarang budget totalnya sejalan dengan matriks SLA di
    Monitoring 2026 > Backend.

    Kolom Kandidat dan Onboarding memakai basis tanggal yang BERBEDA, dan itu
    disengaja: Kandidat memakai tanggal Screening CV ("berapa CV yang saya proses
    periode ini"), Onboarding memakai tanggal onboarding ("berapa yang mulai
    kerja periode ini"). Dengan begitu kolom Onboarding kalau dijumlahkan ke
    bawah sama persis dengan total Ringkasan per site di periode yang sama.

    SLA memakai kandidat yang orang itu tangani di periode screening.
    """
    # SATU populasi untuk seluruh kolom: kandidat yang PIC Screening CV-nya orang
    # itu. Sebelumnya SLA memakai populasi lain — "semua kandidat yang tahap mana
    # pun pernah ia pegang" — sementara Kandidat dan Onboarding memakai screening.
    # Akibatnya satu baris berisi angka dari dua kelompok orang yang berbeda, dan
    # baris seperti "PIC Site SSCP" tampil punya 83 kandidat tapi SLA kosong,
    # karena SLA kandidat itu tercatat di baris orang lain.
    pemilik = _screening_owner(sf, extra_map, sites=sites)

    kolom = ["name", "sla_actual", "sla_budget", "stages", "candidates",
             "onboarding", "achievement"]
    if pemilik.empty:
        g = pd.DataFrame(columns=kolom[1:], index=pd.Index([], name="name"))
    else:
        def dalam(kolom_tanggal):
            m = pemilik[kolom_tanggal].notna()
            if date_from is not None:
                m &= pemilik[kolom_tanggal] >= pd.Timestamp(date_from)
            if date_to is not None:
                m &= pemilik[kolom_tanggal] <= pd.Timestamp(date_to)
            return pemilik[m]

        periode = dalam("screening_date")

        # SLA memakai SELURUH tahap proses kandidat itu — bukan hanya tahap yang
        # orangnya pegang sendiri. Versi lama hanya menghitung tujuh tahap ber-PIC
        # sehingga One Month Notice yang budget-nya saja 30 hari ikut terbuang.
        semua = sf.merge(periode[["cand_key", "name"]], on="cand_key", how="inner")
        terpakai = semua[semua["applicable"] & semua["budget"].notna()]

        per_stage = terpakai.groupby(["name", "stage"]).agg(
            lt=("lt", "mean"),
            budget=("budget", "mean"),
        ).reset_index()

        g = per_stage.groupby("name").agg(
            sla_actual=("lt", "sum"),
            sla_budget=("budget", "sum"),
            stages=("stage", "nunique"),
        )
        # Nama yang punya kandidat tapi belum punya tahap ber-budget tetap harus
        # muncul; penempelan kolom di bawah mengikuti indeks yang sudah ada.
        g = g.reindex(g.index.union(pemilik["name"].unique(), sort=False))

        # Dua kolom, dua basis tanggal — dan itu memang disengaja:
        #   Kandidat  : tanggal SCREENING CV  -> "berapa CV yang saya proses"
        #   Onboarding: tanggal ONBOARDING    -> "berapa yang mulai kerja"
        # Sebelumnya keduanya memakai tanggal screening, sehingga orang yang
        # di-screening Mei tapi onboarding Juli tidak terhitung di periode
        # Jun-Sep. Akibatnya kolom Onboarding tidak pernah bisa dicocokkan
        # dengan Ringkasan per site, padahal sumbernya sama.
        g["candidates"] = periode.groupby("name")["cand_key"].nunique()

        # Syarat CLOSE dipakai persis seperti di summary_matrix(): ada 4 orang di
        # 2026 yang tanggal onboarding-nya terisi tapi statusnya FAILED — batal di
        # detik terakhir. Tanpa syarat ini kolom Onboarding kelebihan 4 dari
        # Ringkasan per site, dan selisih kecil yang tidak dijelaskan justru
        # paling melelahkan untuk ditelusuri.
        tutup = dalam("onboarding_date")
        tutup = tutup[tutup["status1"] == "CLOSE"]
        g["onboarding"] = tutup.groupby("name")["cand_key"].nunique()
        # Dipotong di ACHIEVEMENT_MAX: lihat alasannya di config.
        g["achievement"] = ((g["sla_budget"] / g["sla_actual"] * 100)
                            .where(g["sla_actual"] > 0)
                            .clip(upper=C.ACHIEVEMENT_MAX))

    # Roster selalu tampil lengkap, termasuk orang yang belum punya data —
    # baris nol lebih jujur daripada nama yang hilang begitu saja.
    g = g.reindex(g.index.union(C.RECRUITER_ROSTER, sort=False))
    for c in ("candidates", "stages", "onboarding"):
        g[c] = g[c].fillna(0).astype(int)

    # Baris "PIC Site …" yang kosong sama sekali di periode ini dibuang. Nama
    # roster tetap ditampilkan walau nol — baris nol untuk orang itu informasi
    # ("belum ada yang ia pegang"), sedangkan baris nol untuk site cuma sampah.
    kosong = ((g["candidates"] == 0) & (g["onboarding"] == 0)
              & g["sla_actual"].isna()
              & pd.Series([str(n).startswith("PIC Site") for n in g.index],
                          index=g.index))
    g = g[~kosong]

    # Urutannya: roster dulu, lalu baris per site, lalu "Recruiter lain".
    # Baris site bukan orang, jadi tidak pantas berdiri di antara nama orang —
    # tapi juga bukan sisa-sisa, jadi tidak pantas ikut tenggelam di paling bawah.
    order = {n: i for i, n in enumerate(C.RECRUITER_ROSTER)}
    g["_sort"] = [
        order.get(n, 90 if n == C.OTHER_RECRUITER_LABEL
                  else 70 if str(n).startswith("PIC Site") else 50)
        for n in g.index
    ]
    g = g.sort_values(["_sort"]).drop(columns="_sort")

    return g.reset_index().rename(columns={"index": "name"}).round(
        {"sla_actual": 1, "sla_budget": 1, "achievement": 1})[kolom]


def unmapped_initials(sf: pd.DataFrame, extra_map: dict | None = None) -> pd.DataFrame:
    """Inisial yang belum punya nama lengkap, diurutkan dari yang tersibuk.

    Dipakai panel "Kelola recruiter" supaya Navi bisa langsung melihat inisial
    mana yang paling berdampak kalau dipetakan.
    """
    work = sf[sf["pic_initial"].notna()]
    known = work["pic_initial"].map(lambda i: recruiter_name(i, extra_map)).notna()
    g = work[~known].groupby("pic_initial").agg(
        aktivitas=("stage", "size"),
        kandidat=("cand_key", "nunique"),
        onboarding=("status1", lambda s: (s == "CLOSE").sum()),
    )
    return g.sort_values("aktivitas", ascending=False).reset_index()


def hire_trend(df: pd.DataFrame, lt: pd.DataFrame, exclude_levels=("Non Staff",)) -> pd.DataFrame:
    """Median time-to-hire per bulan onboarding.

    Non Staff dikecualikan secara default: 163 dari 164 hire Non Staff punya
    tanggal screening, interview, dan onboarding yang persis sama (input borongan
    di KCP), jadi lead time-nya nol dan akan menarik median ke bawah secara palsu.
    """
    onboard = df.set_index("cand_key")[ELAPSED_END]
    j = lt.set_index("cand_key").join(onboard.rename("onboard_date"))
    j = j[(j["status1"] == "CLOSE") & j["lt_elapsed"].notna() & (j["lt_elapsed"] > 0)]
    if exclude_levels:
        j = j[~j["level"].isin(exclude_levels)]
    if j.empty:
        return pd.DataFrame(columns=["period", "n", "median_lt"])

    j["period"] = j["onboard_date"].dt.to_period("M")
    g = j.groupby("period").agg(n=("lt_elapsed", "size"), median_lt=("lt_elapsed", "median"))
    return g.reset_index().sort_values("period")


def headline(df: pd.DataFrame, lt: pd.DataFrame) -> dict:
    """Angka-angka untuk baris KPI di Overview."""
    staff = lt[(lt["status1"] == "CLOSE") & (lt["level"] != "Non Staff")
               & lt["lt_elapsed"].notna() & (lt["lt_elapsed"] > 0)]
    scored = staff[staff["lt_status"].isin(["Onbudget", "Overbudget"])]
    counts = df["status1"].value_counts()

    # CLOSE sekarang punya dua arti. Sejak talent pool dipakai, sebuah proses
    # bisa "selesai" karena orangnya masuk kerja ATAU karena orangnya disimpan
    # untuk kebutuhan berikutnya. Menjumlahkan keduanya membuat pencapaian
    # rekrutmen terlihat lebih besar dari kenyataan, jadi dipisah di sini.
    tutup = df["status1"] == "CLOSE"
    pool = df["talent_pool"] if "talent_pool" in df.columns else pd.Series(
        False, index=df.index)
    return {
        "candidates": len(df),
        "hired": int((tutup & ~pool).sum()),
        "close_total": int(counts.get("CLOSE", 0)),
        # Seluruh orang di pool, apa pun status1-nya: sebagian baris masih
        # tertulis OPEN di sheet karena statusnya belum ditutup, padahal
        # keputusannya sudah diambil di kolom Result.
        "talent_pool": int(pool.sum()),
        "close_talent_pool": int((tutup & pool).sum()),
        "open": int(counts.get("OPEN", 0)),
        "failed": int(counts.get("FAILED", 0)),
        "median_lt": float(staff["lt_elapsed"].median()) if len(staff) else None,
        "p90_lt": float(staff["lt_elapsed"].quantile(0.9)) if len(staff) else None,
        "lt_n": len(staff),
        "over_pct": (float((scored["lt_status"] == "Overbudget").mean() * 100)
                     if len(scored) else None),
        "over_n": int((scored["lt_status"] == "Overbudget").sum()),
        "scored_n": len(scored),
        "date_errors": int(lt["date_error"].sum()),
        "dup_names": int(df["is_duplicate_name"].sum()),
    }


# ===========================================================================
# Weekly Report
# ===========================================================================
BULAN_NAMA = {1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
              7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"}


BULAN_NAMA_BALIK = {v: k for k, v in BULAN_NAMA.items()}


def periode_label(tahun: int, bulan: int, banyak_tahun: bool = False) -> str:
    """Label kolom untuk satu periode. Tahun ikut ditulis kalau lebih dari satu."""
    return f"{BULAN_NAMA[bulan]} {str(tahun)[-2:]}" if banyak_tahun else BULAN_NAMA[bulan]


def _periode_kolom(periods: list[tuple[int, int]]) -> list[tuple[tuple[int, int], str]]:
    banyak = len({t for t, _ in periods}) > 1
    return [(p, periode_label(p[0], p[1], banyak)) for p in sorted(periods)]


def new_hire_matrix(df: pd.DataFrame, periods: list[tuple[int, int]],
                    sites=None) -> pd.DataFrame:
    """Onboarding per departemen untuk periode yang dipilih.

    `periods` = daftar (tahun, bulan). Tiap periode jadi satu kolom, ditutup
    kolom Total. Baris terakhir adalah total per kolom.

    Berbeda dengan sheet aslinya, angka Total di sini SELALU sama dengan jumlah
    isinya karena dihitung, bukan diketik (temuan T-06).
    """
    if not periods:
        return pd.DataFrame()

    h = df[(df["status1"] == "CLOSE") & df["date_onboarding"].notna()].copy()
    if sites:
        h = h[h["loc"].isin(C.loc_values_for(sites))]
    if h.empty:
        return pd.DataFrame()

    h["_dept"] = (h["departement"].astype(str).str.strip()
                  .replace({"": None, "nan": None, "None": None})
                  .fillna(C.DEPT_UNMAPPED_LABEL))
    kolom = _periode_kolom(periods)

    hasil = {}
    for (thn, bln), label in kolom:
        sel = h[(h["date_onboarding"].dt.year == thn) & (h["date_onboarding"].dt.month == bln)]
        hasil[label] = sel.groupby("_dept").size()

    tabel = pd.DataFrame(hasil).fillna(0).astype(int)
    if tabel.empty:
        return pd.DataFrame()
    tabel["Total"] = tabel.sum(axis=1)
    tabel = tabel[tabel["Total"] > 0].sort_values("Total", ascending=False)
    tabel.loc["TOTAL"] = tabel.sum()
    return tabel.reset_index().rename(columns={"_dept": "Department", "index": "Department"})


def summary_matrix(df: pd.DataFrame, periods: list[tuple[int, int]],
                   sites=None) -> pd.DataFrame:
    """Onboarding per SITE untuk periode yang dipilih — bentuknya sama dengan New Hire.

    Periodenya memakai tanggal onboarding, jadi angkanya bisa disandingkan
    langsung dengan tabel New Hire di atasnya.
    """
    if not periods:
        return pd.DataFrame()

    h = df[(df["status1"] == "CLOSE") & df["date_onboarding"].notna()].copy()
    if sites:
        h = h[h["loc"].isin(C.loc_values_for(sites))]
    if h.empty:
        return pd.DataFrame()

    # Baris tanpa kode site itu Balikpapan yang tidak terisi saat input
    # (arahan Navi), jadi dimasukkan ke BPN alih-alih jadi baris "(tanpa site)".
    h["_site"] = (h["loc"].astype(str).str.strip()
                  .replace({"": None, "nan": None, "None": None})
                  .fillna("BPN"))
    kolom = _periode_kolom(periods)

    hasil = {}
    for (thn, bln), label in kolom:
        sel = h[(h["date_onboarding"].dt.year == thn) & (h["date_onboarding"].dt.month == bln)]
        hasil[label] = sel.groupby("_site").size()

    tabel = pd.DataFrame(hasil).fillna(0).astype(int)
    if tabel.empty:
        return pd.DataFrame()
    tabel["Total"] = tabel.sum(axis=1)
    tabel = tabel[tabel["Total"] > 0].sort_values("Total", ascending=False)
    tabel.loc["TOTAL"] = tabel.sum()
    return tabel.reset_index().rename(columns={"_site": "Site", "index": "Site"})


# ===========================================================================
# Tracking Posisi
# ===========================================================================
def candidate_options(df: pd.DataFrame) -> dict[str, str]:
    """Label pencarian -> cand_key, untuk kotak pencarian Tracking Kandidat.

    Label ditulis NAMA dulu, baru posisi dan site — supaya saran yang muncul
    sambil mengetik sudah cukup untuk membedakan dua orang bernama mirip tanpa
    memilih dulu satu per satu.

    Halaman memakai `filter_mode="contains"`, bukan fuzzy bawaan Streamlit. Fuzzy
    mencocokkan huruf yang terserak (mengetik "tika" ikut menarik label mana pun
    yang punya t-i-k-a berurutan di mana saja), dan itu yang dulu membuat hasil
    pencarian terasa acak.
    """
    d = df.sort_values("candidate_id").copy()
    ekor = ("  ·  " + d["position_name"].fillna("—").astype(str)
            + "  ·  " + d["loc"].fillna("—").astype(str))
    label = d["candidate_id"].astype(str) + ekor

    # Nama + posisi + site pun masih bisa kembar (orang yang sama dua kali di
    # posisi yang sama). Diberi nomor supaya dua baris tetap bisa dipilih
    # terpisah — dropdown tidak boleh punya dua entri yang tidak terbedakan.
    kembar = label.duplicated(keep=False)
    if kembar.any():
        urut = label.groupby(label).cumcount() + 1
        label = label.where(~kembar, label + "  #" + urut.astype(str))
    return dict(zip(label, d["cand_key"]))


def position_options(df: pd.DataFrame) -> dict[str, tuple[str, str]]:
    """Label pencarian -> (nama posisi, site), untuk kotak Tracking Posisi.

    Sama seperti candidate_options: NAMA POSISI dulu, baru site dan departemen —
    posisi yang sama sering ada di beberapa site, dan tanpa keduanya tertulis di
    saran, orang harus memilih dulu untuk tahu mana yang dimaksud.
    """
    d = df[df["position_name"].notna()].copy()
    if d.empty:
        return {}
    g = (d.groupby(["position_name", "loc"], dropna=False)
           .agg(departement=("departement", "first"), kandidat=("cand_key", "nunique"))
           .reset_index()
           .sort_values(["position_name", "loc"]))

    label = (g["position_name"].astype(str)
             + "  ·  " + g["loc"].fillna("—").astype(str)
             + "  ·  " + g["departement"].fillna("—").astype(str))
    return dict(zip(label, zip(g["position_name"], g["loc"])))


def position_candidates(df: pd.DataFrame, lt: pd.DataFrame, position_name: str,
                        loc: str | None = None, sf: pd.DataFrame | None = None,
                        estimasi: pd.Series | None = None) -> pd.DataFrame:
    """Kandidat untuk satu posisi di satu site, lengkap dengan total lead time.

    Kolomnya sengaja dibatasi pada yang dipakai saat menilai pemenuhan posisi:
    nama, posisi, departemen, level, lokasi, tahap terakhir, total LT, status.
    """
    d = df[df["position_name"] == position_name]
    if loc:
        d = d[d["loc"] == loc]
    if d.empty:
        return pd.DataFrame(columns=["candidate_id", "position_name", "position_id",
                                     "departement", "level", "loc", "last_progress",
                                     "total_lt", "budget_total", "estimasi",
                                     "status1"])

    # Sheet sumber sudah punya kolom bernama total_lt, tapi isinya jumlah durasi
    # tahap — bukan lead time end-to-end (temuan T-01). Kolom itu dibuang lebih
    # dulu supaya tidak ada dua kolom bernama sama dengan arti berbeda.
    d = d.drop(columns=[c for c in ("total_lt", "tot_lt") if c in d.columns])
    d = d.merge(lt[["cand_key", "budget_total"]], on="cand_key", how="left")

    # SLA dijumlahkan dari tiap tahap, jadi kandidat OPEN dan FAILED pun punya
    # angka — cara lama (selisih tanggal ujung ke ujung) hanya terisi untuk yang
    # sudah onboarding, dan sisanya kosong (arahan Navi, 7 Sep 2026).
    if sf is not None:
        d["total_lt"] = d["cand_key"].map(sla_per_candidate(sf))
        d["estimasi"] = d["cand_key"].map(estimasi)
    else:
        d["total_lt"] = pd.NA
        d["estimasi"] = pd.NA

    # Yang sudah selesai tidak perlu diperkirakan — targetnya diisi budget SLA
    # level itu, yaitu "harusnya selesai berapa hari".
    d.loc[d["status1"] != "OPEN", "estimasi"] = pd.NA
    kol = ["candidate_id", "position_name", "position_id", "departement", "level",
           "loc", "last_progress", "total_lt", "budget_total", "estimasi",
           "status1"]
    kol = [c for c in kol if c in d.columns]
    urut = {"OPEN": 0, "CLOSE": 1, "FAILED": 2}
    d["_u"] = d["status1"].map(urut).fillna(3)
    return d.sort_values(["_u", "candidate_id"])[kol]




# ===========================================================================
# On Progress & Karyawan resign — replikasi rumus sheet Report
# ===========================================================================
# Ketiga panel ONP dan panel resign MEREPLIKASI rumus QUERY milik tim, bukan
# tafsiran sendiri. Rumus aslinya membaca sheet "Backend Monitoring"; kolom yang
# dipakai dipetakan ke fix_centralized seperti ini:
#
#   Backend Monitoring        fix_centralized
#   K  STATUS                 status1
#   M  LAST PROGRESS          last_progress
#   BG START REQ OFFERING     start_offering
#   BH OL SENT TO CANDIDATE   ol_sent_to_candidate
#   CL RESULT MCU             result_fu_mcu
#   CN DATE OF ONBOARDING     date_onboarding
#
# Backend Monitoring memakai satu label "Offering", sementara fix_centralized
# memecahnya jadi "Req Offering" dan "Offering Negotiation" — keduanya diterima.
ONP_OFFERING_PROGRESS = {"OFFERING", "REQ OFFERING", "OFFERING NEGOTIATION"}
ONP_MCU_PROGRESS = {"MCU", "REVIEW MCU", "FU MCU"}


def _month_bounds(ref=None):
    """Awal bulan berjalan dan awal bulan berikutnya — persis EOMONTH di rumus."""
    ref = pd.Timestamp(ref) if ref is not None else pd.Timestamp.today()
    awal = ref.normalize().replace(day=1)
    return awal, awal + pd.offsets.MonthBegin(1)


def _periode_mask(seri: pd.Series, periods) -> pd.Series:
    """True untuk baris yang tanggalnya jatuh di salah satu (tahun, bulan) terpilih."""
    if not periods:
        return pd.Series(True, index=seri.index)
    ok = pd.Series(False, index=seri.index)
    for thn, bln in periods:
        ok |= (seri.dt.year == thn) & (seri.dt.month == bln)
    return ok & seri.notna()


def on_progress(df: pd.DataFrame, periods=None, sites=None) -> dict[str, pd.DataFrame]:
    """Tiga panel On Progress, mengikuti rumus sheet ONP.

    Offering    status OPEN, tahap Offering, START REQ OFFERING di periode terpilih
    MCU         status OPEN, tahap MCU/Review MCU/FU MCU, OL SENT di periode terpilih
    Onboarding  hasil MCU FIT TO WORK, tanggal onboarding di periode terpilih

    Rumus aslinya mematok bulan berjalan lewat EOMONTH(TODAY()). Di portal, "bulan
    berjalan" itu diganti periode yang dipilih di filter; kalau filternya kosong,
    hasilnya sama persis dengan rumus aslinya.
    """
    d = df
    if sites:
        d = d[d["loc"].isin(C.loc_values_for(sites))]

    prog = d["last_progress"].astype(str).str.strip().str.upper()
    buka = d["status1"] == "OPEN"
    kol = ["candidate_id", "position_name", "departement", "loc", "last_progress", "level"]

    def _ambil(mask, tgl_col):
        sel = d[mask].copy()
        sel["tanggal"] = sel[tgl_col]
        return sel[kol + ["tanggal"]].sort_values(["loc", "candidate_id"])

    offering = _ambil(
        buka & prog.isin(ONP_OFFERING_PROGRESS)
        & _periode_mask(d["start_offering"], periods), "start_offering")

    mcu = _ambil(
        buka & prog.isin(ONP_MCU_PROGRESS)
        & _periode_mask(d["ol_sent_to_candidate"], periods), "ol_sent_to_candidate")

    fit = d["result_fu_mcu"].astype(str).str.strip().str.upper() == "FIT TO WORK"
    if periods:
        onboard = _ambil(fit & _periode_mask(d["date_onboarding"], periods), "date_onboarding")
    else:
        # Tanpa filter, ikuti rumus aslinya: yang akan datang, bukan riwayat.
        hari_ini = pd.Timestamp.today().normalize()
        onboard = _ambil(fit & (d["date_onboarding"] > hari_ini), "date_onboarding")

    return {"Offering": offering, "MCU": mcu, "Onboarding": onboard}


def _tanggal_mpp(s) -> pd.Series:
    """Tanggal di sheet Update MPP ditulis hari-dulu: 03/01/2026 = 3 Januari.

    Kalau dibaca dengan tebakan bawaan pandas, tanggal 1-12 terbalik jadi bulan
    dan daftar resign ikut salah bulan. Format eksplisit dulu; sisa nilai yang
    tidak cocok (misal sudah berupa ISO) baru ditebak.
    """
    s = pd.Series(s)
    teks = s.astype(str).str.strip()
    hasil = pd.to_datetime(teks, format="%d/%m/%Y", errors="coerce")
    sisa = hasil.isna() & teks.ne("") & ~teks.isin(["nan", "None", "NaT", "-"])
    if sisa.any():
        hasil[sisa] = pd.to_datetime(teks[sisa], errors="coerce", dayfirst=True)
    return hasil


def resign(mpp: pd.DataFrame, periods=None, sites=None) -> pd.DataFrame:
    """Karyawan resign — replikasi rumus sheet "Karyawan Resign".

    Rumus aslinya menggabungkan dua QUERY atas sheet "Update MPP":
      End Date terisi · Level < 11 · Position Name bukan 'Internship'
      · End Date di bulan berjalan
      · DAN (End Date < Contract End Date  ATAU  Contract End Date kosong)

    Di portal "bulan berjalan" diganti periode yang dipilih di filter, dan filter
    site memakai peta nama lokasi panjang (ACP = Asam-Asam Coal Project). Tanpa
    filter, hasilnya sama persis dengan rumus aslinya.

    Diverifikasi: 18 dari 18 nama cocok dengan sheet untuk Agustus 2026.
    """
    kosong = pd.DataFrame(columns=["Karyawan", "Position Name", "Site",
                                   "Resign Date", "End Contract", "Level"])
    if mpp is None or getattr(mpp, "empty", True):
        return kosong

    d = mpp.copy()
    d.columns = [str(c).strip() for c in d.columns]

    # Kalau yang terambil ternyata tab lain, berhenti di sini dengan tabel kosong
    # — panelnya menjelaskan keadaannya, bukan meledak sebagai KeyError di tengah
    # halaman dan menjatuhkan seluruh Weekly Report.
    perlu = ["Employee Name", "Position Name", "Location Name",
             "End Date", "Contract End Date", "Level"]
    if not set(perlu) <= set(d.columns):
        return kosong

    for c in ("End Date", "Contract End Date"):
        d[c] = _tanggal_mpp(d.get(c))
    d["Level"] = pd.to_numeric(d.get("Level"), errors="coerce")

    if periods:
        periode_ok = _periode_mask(d["End Date"], periods)
    else:
        awal, berikut = _month_bounds()
        periode_ok = d["End Date"].between(awal, berikut, inclusive="left")

    # Level >= 11 itu non-staff operator, tidak masuk laporan ini.
    mask = (
        d["End Date"].notna()
        & (d["Level"] < 11)
        & (d.get("Position Name") != "Internship")
        & periode_ok
        & ((d["End Date"] < d["Contract End Date"]) | d["Contract End Date"].isna())
    )
    if sites:
        mask &= d["Location Name"].isin(C.location_names_for(sites))

    out = d[mask][["Employee Name", "Position Name", "Location Name",
                   "End Date", "Contract End Date", "Level"]]
    if out.empty:
        return kosong
    out.columns = ["Karyawan", "Position Name", "Site", "Resign Date",
                   "End Contract", "Level"]
    return out.sort_values(["Site", "Resign Date"])


# ===========================================================================
# PRF Tracking
# ===========================================================================
# Satu baris di sheet "PRF Tracking" = satu pengajuan posisi. Kartu dan tabel
# menghitung BARIS PRF, bukan qty orang: satu PRF bisa meminta 14 orang, dan
# menjumlahkan qty membuat "berapa PRF yang sudah approved" jadi pertanyaan yang
# berbeda dari yang ditanyakan. Qty tetap ditampilkan per baris di tabel.
PRF_COLS = ["prf_id", "prf_class", "qty", "position_name", "site", "divisi",
            "level", "level_type", "tracking", "status"]


def prepare_prf(df: pd.DataFrame) -> pd.DataFrame:
    """Rapikan sheet PRF Tracking jadi bentuk yang dipakai halaman.

    Yang dikerjakan di sini dan tidak di halaman:
      · `prf_id` — Request Number kalau ada, kalau kosong pakai ID PRF. Dua kolom
        untuk satu identitas membingungkan di tabel, jadi digabung sejak awal.
      · `level_type` — Staff / Non Staff, dari daftar level Staff di config.
      · Nilai Tracking dan Status di-uppercase supaya "Open" dan "OPEN" tidak
        jadi dua kategori berbeda di filter.
    """
    d = df.copy()
    d.columns = [str(c).strip() for c in d.columns]

    def teks(kolom: str) -> pd.Series:
        s = d.get(kolom, pd.Series(index=d.index, dtype=object))
        return (s.astype(str).str.strip()
                 .replace({"nan": None, "": None, "None": None, "-": None}))

    req, idp = teks("request_number"), teks("ID PRF")
    out = pd.DataFrame(index=d.index)
    out["prf_id"] = req.fillna(idp).fillna("—")
    out["prf_class"] = teks("prf_class").fillna("—")
    out["qty"] = pd.to_numeric(d.get("qty"), errors="coerce").fillna(0).astype(int)
    out["position_name"] = teks("position_name").fillna("—")
    out["site"] = teks("Site").fillna(teks("loc")).fillna("—").str.upper()
    out["divisi"] = teks("divisi").fillna("—")
    out["level"] = teks("level").fillna("—")

    staf = {s.strip().lower() for s in C.PRF_STAFF_LEVELS}
    out["level_type"] = out["level"].str.lower().map(
        lambda v: "Staff" if v in staf else "Non Staff")
    # Level yang belum terisi bukan Non Staff — itu klaim yang tidak ada dasarnya.
    out.loc[out["level"] == "—", "level_type"] = "—"

    out["tracking"] = teks("Tracking PRF").fillna("—").str.upper()
    out["status"] = teks("Status").fillna("—").str.upper()
    out["tanggal_pengajuan"] = pd.to_datetime(d.get("Tanggal Pengajuan"),
                                              errors="coerce")
    out["tanggal_approved"] = pd.to_datetime(d.get("Tanggal Approved"),
                                             errors="coerce")
    return out.reset_index(drop=True)


def filter_prf(df: pd.DataFrame, sites=None, levels=None, level_types=None,
               trackings=None, statuses=None) -> pd.DataFrame:
    """Terapkan kelima filter halaman. Daftar kosong berarti 'semua'."""
    d = df
    for kolom, pilihan in (("site", sites), ("level", levels),
                           ("level_type", level_types), ("tracking", trackings),
                           ("status", statuses)):
        if pilihan:
            d = d[d[kolom].isin(list(pilihan))]
    return d


def prf_summary(df: pd.DataFrame) -> dict:
    """Angka untuk kartu di atas halaman PRF.

    Approved dan Not Approved dihitung dari kolom Tracking PRF — itu yang
    menyatakan pengajuannya sudah disetujui atau masih berjalan. Close dihitung
    dari kolom Status, dan persentasenya terhadap TOTAL PRF (bukan terhadap yang
    approved saja) sesuai permintaan.
    """
    total = len(df)
    approved = int((df["tracking"] == "APPROVED").sum()) if total else 0
    close = int((df["status"] == "CLOSE").sum()) if total else 0

    def persen(n: int) -> float:
        return round(n / total * 100, 1) if total else 0.0

    return {
        "total": total,
        "qty": int(df["qty"].sum()) if total else 0,
        "approved": approved,
        "approved_pct": persen(approved),
        "not_approved": total - approved,
        "not_approved_pct": persen(total - approved),
        "close": close,
        "close_pct": persen(close),
    }


# ===========================================================================
# Jelajah posisi — tiga cara masuk ke data yang sama
# ===========================================================================
# Halaman Tracking Posisi dulu hanya bisa dimasuki lewat nama posisi. Itu
# menjawab "bagaimana posisi X?" tapi tidak menjawab "di site ini yang lagi
# jalan apa saja?" — padahal itu pertanyaan pertama yang biasanya diajukan.
#
# Ketiganya membaca data yang sama dan memakai definisi yang sama:
#   ongoing = status1 OPEN        proses masih berjalan
#   hired   = CLOSE, bukan talent pool
#   pool    = talent pool         lolos tapi belum ditempatkan
#   gagal   = FAILED
def _ringkas(d: pd.DataFrame) -> dict:
    pool = d["talent_pool"] if "talent_pool" in d.columns else pd.Series(
        False, index=d.index)
    tutup = d["status1"] == "CLOSE"
    return {
        "kandidat": int(d["cand_key"].nunique()),
        "ongoing": int((d["status1"] == "OPEN").sum()),
        "hired": int((tutup & ~pool).sum()),
        "pool": int(pool.sum()),
        "gagal": int((d["status1"] == "FAILED").sum()),
    }


def _terpakai(df: pd.DataFrame, sites=None, departemen=None) -> pd.DataFrame:
    d = df
    if sites:
        d = d[d["loc"].isin(C.loc_values_for(sites))]
    if departemen:
        d = d[d["departement"].isin(list(departemen))]
    return d


def site_summary(df: pd.DataFrame, sites=None) -> pd.DataFrame:
    """Satu baris per site: berapa departemen, posisi, dan kandidat yang jalan."""
    d = _terpakai(df, sites)
    if d.empty:
        return pd.DataFrame(columns=["site", "departemen", "posisi", "kandidat",
                                     "ongoing", "hired", "pool", "gagal"])
    baris = []
    for site, g in d.groupby("loc", dropna=False):
        baris.append({
            "site": site or "—",
            "departemen": g["departement"].nunique(),
            "posisi": g["position_name"].nunique(),
            **_ringkas(g),
        })
    return pd.DataFrame(baris).sort_values("kandidat", ascending=False)


def department_summary(df: pd.DataFrame, sites=None) -> pd.DataFrame:
    """Satu baris per departemen — dasar mode Per Site dan Per Departemen."""
    d = _terpakai(df, sites)
    if d.empty:
        return pd.DataFrame(columns=["departement", "posisi", "kandidat",
                                     "ongoing", "hired", "pool", "gagal"])
    baris = []
    for dep, g in d.groupby("departement", dropna=False):
        baris.append({
            "departement": dep or "—",
            "posisi": g["position_name"].nunique(),
            **_ringkas(g),
        })
    out = pd.DataFrame(baris)
    # Diurutkan dari yang paling banyak SEDANG BERJALAN, bukan dari total: yang
    # dicari orang di halaman ini adalah pekerjaan yang masih harus dikerjakan.
    return out.sort_values(["ongoing", "kandidat"], ascending=False)


def position_summary(df: pd.DataFrame, departemen=None, sites=None) -> pd.DataFrame:
    """Satu baris per posisi di dalam satu departemen."""
    d = _terpakai(df, sites, [departemen] if isinstance(departemen, str) else departemen)
    if d.empty:
        return pd.DataFrame(columns=["position_name", "loc", "level", "kandidat",
                                     "ongoing", "hired", "pool", "gagal"])
    baris = []
    for (pos, loc), g in d.groupby(["position_name", "loc"], dropna=False):
        baris.append({
            "position_name": pos or "—",
            "loc": loc or "—",
            "level": g["level"].mode().iat[0] if len(g["level"].mode()) else "—",
            **_ringkas(g),
        })
    return pd.DataFrame(baris).sort_values(["ongoing", "kandidat"], ascending=False)


def ongoing_candidates(df: pd.DataFrame, lt: pd.DataFrame, departemen=None,
                       sites=None, position_name=None,
                       sf: pd.DataFrame | None = None,
                       estimasi: pd.Series | None = None) -> pd.DataFrame:
    """Kandidat yang prosesnya masih berjalan, siap ditampilkan apa adanya."""
    d = _terpakai(df, sites, [departemen] if isinstance(departemen, str) else departemen)
    d = d[d["status1"] == "OPEN"]
    if position_name:
        d = d[d["position_name"] == position_name]
    if d.empty:
        return pd.DataFrame(columns=["candidate_id", "position_name", "loc",
                                     "level", "last_progress", "lt_elapsed",
                                     "budget_total", "estimasi"])
    d = d.merge(lt[["cand_key", "budget_total"]], on="cand_key", how="left")
    d["lt_elapsed"] = d["cand_key"].map(sla_per_candidate(sf)) if sf is not None else pd.NA
    d["estimasi"] = d["cand_key"].map(estimasi) if estimasi is not None else pd.NA
    kol = ["candidate_id", "position_name", "loc", "level", "last_progress",
           "lt_elapsed", "budget_total", "estimasi"]
    return d[kol].sort_values(["position_name", "candidate_id"])


# ===========================================================================
# Monitoring — pengganti membaca spreadsheet mentah
# ===========================================================================
# Sheet aslinya 100+ kolom: tiap tahap punya start, done, LT, budget, LT
# contribution, variance, reason, dan result. Delapan kolom per tahap dikali dua
# belas tahap adalah alasan orang berhenti membacanya dan mulai men-scroll
# sembarangan.
#
# Di sini yang selalu tampil hanya identitas + posisi terakhir + status. Tahap
# ditambahkan sendiri oleh pembaca, dan tiap tahap hanya membawa DUA kolom: LT
# dan hasil SLA-nya. Kolom variance dan LT contribution sengaja tidak dibawa —
# keduanya turunan dari LT dan budget yang sudah tampil, jadi tidak menambah apa
# pun selain lebar.
MONITORING_STAGE_COLS = ("LT", "SLA")


def monitoring_pic(sf: pd.DataFrame, extra_map: dict | None = None) -> pd.Series:
    """cand_key -> PIC Screening CV (nama lengkap).

    Screening CV dipakai sebagai penanda kepemilikan, sama seperti di tabel
    Performance: tiap kandidat punya tepat satu PIC screening, jadi filter PIC di
    halaman ini menghasilkan angka yang sama dengan tabel Performance.
    """
    pem = _screening_owner(sf, extra_map)
    return pem.set_index("cand_key")["name"].groupby(level=0).first()


def monitoring_table(df: pd.DataFrame, sf: pd.DataFrame, lt: pd.DataFrame,
                     stages: list[str] | None = None,
                     extra_map: dict | None = None) -> pd.DataFrame:
    """Tabel monitoring: inti selalu ada, tahap ditambahkan sesuai permintaan."""
    pic = monitoring_pic(sf, extra_map)
    out = df[["cand_key", "candidate_id", "position_name", "departement", "loc",
              "level", "last_progress", "status1", "talent_pool"]].copy()
    out["pic"] = out["cand_key"].map(pic).fillna("—")
    out = out.merge(lt[["cand_key", "lt_elapsed", "stages_late"]],
                    on="cand_key", how="left")

    # Status yang dipakai di layar memisahkan dua arti CLOSE, sama seperti di
    # Overview — supaya orang tidak perlu mengingat bahwa CLOSE bisa berarti dua
    # hal yang berbeda.
    out["status"] = out["status1"]
    out.loc[out["talent_pool"], "status"] = "TALENT POOL"

    for tahap in (stages or []):
        blok = sf[sf["stage"] == tahap].set_index("cand_key")
        out[f"{tahap} · LT"] = out["cand_key"].map(blok["lt"])
        out[f"{tahap} · SLA"] = out["cand_key"].map(blok["sla"]).replace(
            {"": None}).fillna("—")
    return out


def filter_monitoring(d: pd.DataFrame, sites=None, pics=None, departemen=None,
                      statuses=None, levels=None, level_types=None) -> pd.DataFrame:
    """Filter halaman monitoring. Daftar kosong berarti 'semua'."""
    staf = {s.strip().lower() for s in C.PRF_STAFF_LEVELS}
    if sites:
        d = d[d["loc"].isin(C.loc_values_for(sites))]
    if pics:
        d = d[d["pic"].isin(list(pics))]
    if departemen:
        d = d[d["departement"].isin(list(departemen))]
    if statuses:
        d = d[d["status"].isin(list(statuses))]
    if levels:
        d = d[d["level"].isin(list(levels))]
    if level_types:
        jenis = d["level"].astype(str).str.strip().str.lower().map(
            lambda v: "Staff" if v in staf else "Non Staff")
        d = d[jenis.isin(list(level_types))]
    return d


# ---------------------------------------------------------------------------
# Filter bulan berbasis tanggal Screening CV
# ---------------------------------------------------------------------------
# Screening CV dipakai sebagai patokan periode di seluruh portal: itu tanggal
# kandidat masuk proses, jadi satu kandidat selalu utuh dalam satu bulan. Kalau
# patokannya tanggal tahap terakhir, orang yang sama pindah-pindah bulan setiap
# prosesnya maju, dan angka bulan lalu berubah sendiri.
def screening_month(df: pd.DataFrame, sf: pd.DataFrame) -> pd.Series:
    """cand_key -> Timestamp awal bulan screening CV-nya."""
    scr = sf[sf["stage"] == "Screening CV"][["cand_key", "screening_date"]]
    scr = scr.dropna(subset=["screening_date"]).drop_duplicates("cand_key")
    peta = dict(zip(scr["cand_key"], scr["screening_date"].dt.to_period("M")))
    return df["cand_key"].map(peta)


def month_options(df: pd.DataFrame, sf: pd.DataFrame) -> list[str]:
    """Daftar bulan yang benar-benar ada datanya, terbaru dulu."""
    per = screening_month(df, sf).dropna().unique()
    return [f"{BULAN_NAMA[p.month]} {p.year}" for p in sorted(per, reverse=True)]


def screening_date(df: pd.DataFrame, sf: pd.DataFrame) -> pd.Series:
    """cand_key -> tanggal Screening CV-nya (bukan bulannya).

    Dipakai filter rentang tanggal, yang butuh tanggal utuh. Tanggal Screening
    CV yang dipakai sebagai patokan, bukan tanggal onboarding: yang ditanya
    "kandidat yang masuk pipeline dalam periode ini", dan itu ditandai kapan
    CV-nya mulai diproses.
    """
    scr = sf[sf["stage"] == "Screening CV"][["cand_key", "screening_date"]]
    scr = scr.dropna(subset=["screening_date"]).drop_duplicates("cand_key")
    peta = dict(zip(scr["cand_key"], scr["screening_date"]))
    return df["cand_key"].map(peta)


def filter_date_range(df: pd.DataFrame, sf: pd.DataFrame,
                      mulai=None, akhir=None) -> pd.DataFrame:
    """Kandidat yang AKTIF dalam rentang [mulai, akhir].

    Bukan "yang masuk dalam rentang ini". Kandidat punya rentang aktifnya
    sendiri — dari tanggal tahap paling awal sampai tahap paling akhir, atau
    sampai hari ini kalau prosesnya masih berjalan — dan dia ikut kalau rentang
    itu BERSINGGUNGAN dengan rentang yang dipilih.

    Bedanya penting. Kalau yang dipakai tanggal Screening CV saja, memilih
    "bulan ini" akan membuang semua orang yang masuk bulan Juni dan sampai
    sekarang masih di tahap MCU — padahal justru merekalah isi kolom "In
    process" hari ini. Tabel yang menyatakan nol kandidat berjalan padahal
    puluhan orang sedang diproses bukan filter, itu salah baca.

    Kandidat yang tidak punya tanggal sama sekali tidak ikut saat rentangnya
    diisi: tidak ada dasar untuk menyatakan dia aktif kapan.
    """
    if mulai is None and akhir is None:
        return df
    tanggal = pd.concat([sf[["cand_key", "start"]].rename(columns={"start": "d"}),
                         sf[["cand_key", "end"]].rename(columns={"end": "d"})])
    tanggal = tanggal.dropna(subset=["d"])
    if tanggal.empty:
        return df.iloc[0:0]
    rentang = tanggal.groupby("cand_key")["d"].agg(["min", "max"])

    # Proses yang masih berjalan dianggap aktif sampai hari ini, bukan sampai
    # tanggal terakhir yang kebetulan terisi.
    buka = set(df[df["status1"] == "OPEN"]["cand_key"])
    hari_ini = pd.Timestamp.today().normalize()
    rentang.loc[rentang.index.isin(buka), "max"] = hari_ini

    awal = df["cand_key"].map(rentang["min"])
    akhir_k = df["cand_key"].map(rentang["max"])
    ada = awal.notna()
    if akhir is not None:
        ada &= awal <= pd.Timestamp(akhir).normalize()
    if mulai is not None:
        ada &= akhir_k >= pd.Timestamp(mulai).normalize()
    return df[ada]


def filter_month(df: pd.DataFrame, sf: pd.DataFrame, labels) -> pd.DataFrame:
    """Saring kandidat ke bulan-bulan yang dipilih. Kosong berarti semua."""
    if not labels:
        return df
    mau = set()
    for lab in labels:
        nama, tahun = str(lab).rsplit(" ", 1)
        mau.add(pd.Period(year=int(tahun), month=BULAN_NAMA_BALIK[nama], freq="M"))
    return df[screening_month(df, sf).isin(mau)]


def last_progress_breakdown(d: pd.DataFrame) -> list[tuple[str, int]]:
    """Sebaran tahap terakhir kandidat yang masih berjalan, urut proses.

    Diurutkan mengikuti urutan tahap, bukan besar-kecil angkanya: yang dicari
    orang adalah "macetnya di mana", dan itu hanya terbaca kalau tahapnya berdiri
    di urutan yang sama dengan perjalanan aslinya.
    """
    jalan = d[d["status1"] == "OPEN"]
    if jalan.empty:
        return []
    hitung = jalan["last_progress"].fillna("Not started").value_counts().to_dict()
    urut = {t: i for i, t in enumerate(STAGE_ORDER)}
    return sorted(hitung.items(), key=lambda kv: urut.get(kv[0], 99))


# ===========================================================================
# SLA per kandidat & estimasi onboarding
# ===========================================================================
# Dua hal yang dulu kosong dan sekarang selalu terisi:
#
#   SLA kandidat  Jumlah lead time TIAP TAHAP yang sudah berjalan, bukan selisih
#                 tanggal ujung ke ujung. Kandidat OPEN dan FAILED belum punya
#                 tanggal onboarding, jadi lt_elapsed-nya kosong — dan kolom SLA
#                 mereka ikut kosong, padahal prosesnya jelas sudah memakan
#                 waktu. Menjumlahkan per tahap membuat angkanya ada sejak tahap
#                 pertama selesai (arahan Navi, 7 Sep 2026).
#
#   Estimasi      Untuk kandidat OPEN: sisa budget tahap yang sedang berjalan,
#   onboarding    ditambah rata-rata tiap tahap yang belum dijalani. Rata-ratanya
#                 dihitung PER TAHAP dulu baru dijumlahkan — bukan semua durasi
#                 dikumpulkan lalu dirata-rata sekali, karena tahap yang datanya
#                 banyak akan menenggelamkan tahap yang datanya sedikit.
def sla_per_candidate(sf: pd.DataFrame) -> pd.Series:
    """cand_key -> jumlah lead time seluruh tahap yang sudah punya durasi."""
    ada = sf[sf["lt"].notna()]
    return ada.groupby("cand_key")["lt"].sum()


def estimate_date(days, base=None):
    """Sisa hari kerja -> TANGGAL perkiraan onboarding.

    Navi minta targetnya dibaca sebagai tanggal, bukan "berapa hari lagi":
    "11 hari" tidak menjawab kapan, "23 Sep 2026" menjawab. Angkanya
    DIBULATKAN KE ATAS — setengah hari kerja tetap butuh satu hari kerja, dan
    perkiraan yang kepagian lebih merugikan daripada yang kesorean.

    Kalender liburnya sama dengan yang dipakai seluruh lead time, jadi tanggal
    yang keluar tidak pernah jatuh di Sabtu, Minggu, atau libur nasional.
    """
    import math
    import numpy as np
    if days is None or (isinstance(days, float) and pd.isna(days)) or pd.isna(days):
        return None
    n = max(int(math.ceil(float(days))), 0)
    awal = pd.Timestamp(base).normalize() if base is not None else pd.Timestamp.today().normalize()
    hasil = np.busday_offset(awal.to_numpy().astype("datetime64[D]"), n,
                             roll="forward", holidays=_holidays())
    return pd.Timestamp(hasil)


def estimate_dates(days: pd.Series, base=None) -> pd.Series:
    """Versi borongan estimate_date() untuk kolom tabel."""
    if days is None or not len(days):
        return pd.Series(dtype="datetime64[ns]")
    return days.map(lambda v: estimate_date(v, base))


def average_to_hire(sf: pd.DataFrame, df: pd.DataFrame | None = None) -> dict:
    """Rata-rata TOTAL waktu sampai onboarding = jumlah rata-rata TIAP tahap.

    Arahan Navi (7 Sep 2026): "sla screening total dirata-ratakan + rata-rata
    sla interview + rata-rata sla masing-masing stage, termasuk routing PRF".
    Jadi tiap tahap dirata-rata DULU, baru dijumlahkan — bukan seluruh durasi
    dikumpulkan lalu dirata-rata sekali.

    Bedanya nyata: tahap yang datanya sedikit (Psychotest, Technical Test) akan
    tenggelam kalau semuanya dicampur, padahal tahap itu justru yang paling
    sering jadi penyebab molor. Dengan cara ini tiap tahap punya bobot yang
    sama besar dalam angka akhirnya.

    Hasil: {"total", "per_stage" [(tahap, hari, n)], "n_stage", "n_cand"}.
    """
    ada = sf[sf["lt"].notna() & sf["applicable"] & (sf["lt"] > 0)]
    if ada.empty:
        return {"total": None, "per_stage": [], "n_stage": 0, "n_cand": 0}

    rata = ada.groupby("stage")["lt"].mean()
    jumlah = ada.groupby("stage")["lt"].size()
    urut = [s for s in STAGE_ORDER if s in rata.index and s != "Onboarding"]
    per_stage = [(s, float(rata[s]), int(jumlah[s])) for s in urut]
    return {
        "total": float(sum(v for _s, v, _n in per_stage)) if per_stage else None,
        "per_stage": per_stage,
        "n_stage": len(per_stage),
        "n_cand": int(ada["cand_key"].nunique()),
    }


def stage_averages(sf: pd.DataFrame, by_name: pd.Series | None = None) -> dict:
    """Rata-rata lead time per tahap, dipakai memperkirakan sisa proses.

    Mengembalikan {"umum": {tahap: hari}, "per_pic": {(nama, tahap): hari}}.
    Yang per-PIC dipakai lebih dulu supaya perkiraannya memakai kecepatan orang
    yang benar-benar memegang kandidat itu; rata-rata umum hanya menambal tahap
    yang orangnya belum pernah kerjakan.
    """
    ada = sf[sf["lt"].notna() & sf["applicable"]]
    umum = ada.groupby("stage")["lt"].mean().to_dict()

    per_pic = {}
    if by_name is not None and len(by_name):
        d = ada.copy()
        d["_nm"] = d["cand_key"].map(by_name)
        d = d[d["_nm"].notna()]
        if len(d):
            per_pic = d.groupby(["_nm", "stage"])["lt"].mean().to_dict()
    return {"umum": umum, "per_pic": per_pic}


def estimate_onboarding(sf: pd.DataFrame, cand_key: str, rata: dict,
                        pic: str | None = None) -> dict:
    """Perkiraan sisa hari kerja sampai onboarding untuk satu kandidat OPEN.

    Hasilnya: {"sisa_tahap_ini", "tahap_berikutnya", "total", "rincian"}.
    `rincian` menyebut tiap tahap dan sumber angkanya, supaya perkiraannya bisa
    ditelusuri dan bukan sekadar satu angka yang muncul entah dari mana.
    """
    baris = sf[sf["cand_key"] == cand_key].sort_values("stage_no")
    baris = baris[baris["applicable"]]
    if baris.empty:
        return {"sisa_tahap_ini": None, "tahap_berikutnya": None,
                "total": None, "rincian": []}

    def rata_tahap(tahap):
        if pic is not None:
            v = rata["per_pic"].get((pic, tahap))
            if v is not None and pd.notna(v):
                return float(v), "recruiter average"
        v = rata["umum"].get(tahap)
        if v is not None and pd.notna(v):
            return float(v), "overall average"
        return None, None

    rincian = []
    sisa_ini = 0.0

    # Tahap yang sedang berjalan: sudah mulai, belum selesai. Sisanya diukur
    # terhadap RATA-RATA LAMA TAHAP ITU DIKERJAKAN, bukan terhadap budget SLA
    # (arahan Navi, 8 Sep 2026). Alasannya: budget adalah janji, rata-rata adalah
    # kenyataan. Tahap yang budgetnya 5 hari tapi kenyataannya selalu 12 hari
    # akan terus menghasilkan perkiraan yang meleset kalau yang dipakai budget.
    # Kalau rata-ratanya sudah terlampaui, sisanya nol — "tinggal diselesaikan".
    jalan = baris[baris["start"].notna() & baris["end"].isna()]
    for r in jalan.itertuples():
        terpakai = working_days(pd.Series([r.start]),
                                pd.Series([pd.Timestamp.today().normalize()])).iloc[0]
        acuan, dasar = rata_tahap(r.stage)
        if acuan is None:
            acuan = float(r.budget) if pd.notna(r.budget) else None
            dasar = "SLA budget (no history yet)"
        if acuan is None:
            continue
        sisa = max(acuan - float(terpakai or 0), 0.0)
        sisa_ini += sisa
        rincian.append({"tahap": r.stage, "hari": round(sisa, 1),
                        "dasar": f"{dasar} {acuan:.1f} days, "
                                 f"{int(terpakai or 0)} used"})

    # Tahap yang belum mulai DAN memang masih di depan. Tahap yang nomornya lebih
    # kecil dari tahap terjauh yang sudah dijalani bukan sisa pekerjaan — itu
    # tahap yang dilewati atau tanggalnya tidak pernah diisi (PRF Approval paling
    # sering). Menghitungnya sebagai sisa membuat perkiraannya kepanjangan.
    sudah = baris[baris["start"].notna() | baris["end"].notna()]
    batas = sudah["stage_no"].max() if len(sudah) else -1
    belum = baris[baris["start"].isna() & baris["end"].isna()
                  & (baris["stage_no"] > batas)]
    berikut = 0.0
    for r in belum.itertuples():
        v, dasar = rata_tahap(r.stage)
        if v is None:
            v = float(r.budget) if pd.notna(r.budget) else None
            dasar = "SLA budget (no history yet)"
        if v is None:
            continue
        berikut += v
        rincian.append({"tahap": r.stage, "hari": round(v, 1), "dasar": dasar})

    total = sisa_ini + berikut
    return {"sisa_tahap_ini": round(sisa_ini, 1),
            "tahap_berikutnya": round(berikut, 1),
            "total": round(total, 1), "rincian": rincian}


def estimate_all(sf: pd.DataFrame, df: pd.DataFrame,
                 by_name: pd.Series | None = None) -> pd.Series:
    """Perkiraan sisa hari untuk SEMUA kandidat OPEN sekaligus.

    Versi borongan dari estimate_onboarding(), dipakai tabel yang menampilkan
    banyak kandidat. Logikanya sama persis — dihitung vektor supaya halaman yang
    berisi ratusan baris tidak memanggil fungsi per baris.
    """
    rata = stage_averages(sf, by_name)
    buka = set(df[df["status1"] == "OPEN"]["cand_key"])
    d = sf[sf["cand_key"].isin(buka) & sf["applicable"]].copy()
    if d.empty:
        return pd.Series(dtype=float)

    hari_ini = pd.Timestamp.today().normalize()
    jalan = d[d["start"].notna() & d["end"].isna()].copy()
    if len(jalan):
        terpakai = working_days(jalan["start"],
                                pd.Series([hari_ini] * len(jalan), index=jalan.index))
        # Acuan tahap berjalan = rata-rata lama tahap itu dikerjakan (per PIC
        # kalau ada riwayatnya), bukan budget SLA-nya. Lihat alasannya di
        # estimate_onboarding(). Budget hanya menambal tahap yang belum pernah
        # ada riwayatnya sama sekali.
        if by_name is not None:
            jalan["_pic"] = jalan["cand_key"].map(by_name)
            acuan = pd.Series([
                rata["per_pic"].get((p, st), rata["umum"].get(st))
                for p, st in zip(jalan["_pic"], jalan["stage"])
            ], index=jalan.index, dtype="float64")
        else:
            acuan = jalan["stage"].map(rata["umum"]).astype("float64")
        acuan = acuan.fillna(jalan["budget"])
        jalan["_sisa"] = (acuan - terpakai.astype(float)).clip(lower=0)
        jalan = jalan[jalan["_sisa"].notna()]
        sisa_ini = jalan.groupby("cand_key")["_sisa"].sum()
    else:
        sisa_ini = pd.Series(dtype=float)

    # Batas per kandidat: tahap terjauh yang sudah dijalani. Lihat alasannya di
    # estimate_onboarding().
    dijalani = d[d["start"].notna() | d["end"].notna()]
    batas = dijalani.groupby("cand_key")["stage_no"].max()
    belum = d[d["start"].isna() & d["end"].isna()].copy()
    belum = belum[belum["stage_no"] > belum["cand_key"].map(batas).fillna(-1)]
    if len(belum):
        nm = belum["cand_key"].map(by_name) if by_name is not None else None
        if nm is not None:
            belum["_pic"] = nm
            belum["_v"] = [
                rata["per_pic"].get((p, s), rata["umum"].get(s))
                for p, s in zip(belum["_pic"], belum["stage"])
            ]
        else:
            belum["_v"] = belum["stage"].map(rata["umum"])
        belum["_v"] = belum["_v"].fillna(belum["budget"])
        berikut = belum.groupby("cand_key")["_v"].sum()
    else:
        berikut = pd.Series(dtype=float)

    total = sisa_ini.add(berikut, fill_value=0)
    return total.round(1)


# ===========================================================================
# Summary by Division — MPP vs Actual vs proses rekrutmen
# ===========================================================================
# Menirukan sheet "Summary by Division" di spreadsheet Report, tapi bisa
# ditelusuri: All -> site -> divisi -> level -> orangnya. Sheet aslinya berhenti
# di Staff/Non Staff; level baru terlihat kalau pivot-nya dibongkar sendiri.
#
# Tiga sumber, tiga peran yang berbeda:
#   MPP Reforecast      berapa yang DIRENCANAKAN  (Budget & Reforecast per posisi)
#   Update Employee List berapa yang ADA sekarang  (karyawan aktif)
#   Database kandidat    berapa yang SEDANG DIPROSES (pipeline rekrutmen)
#
# Divisi seorang karyawan diambil dari HURUF PERTAMA Position Code — aturan yang
# sama dengan yang dipakai sheet aslinya. Sudah dicocokkan terhadap blok BCP:
# seluruh divisi sama persis kecuali dua yang selisih satu orang karena snapshot
# sheet-nya beda hari.
def prepare_reforecast(df: pd.DataFrame) -> pd.DataFrame:
    """Rapikan MPP Reforecast jadi (site, divisi, level, status, mpp)."""
    d = df.copy()
    d.columns = [str(c).strip() for c in d.columns]
    out = pd.DataFrame({
        "site": d["Loc"].astype(str).str.strip().str.upper(),
        "divisi": d["Divisi"].astype(str).str.strip(),
        "level_code": d["Level Code"].astype(str).str.strip(),
        "status": d["Status"].astype(str).str.strip(),
        "mpp": pd.to_numeric(d["Reforecast"], errors="coerce").fillna(0),
        "budget": pd.to_numeric(d.get("Budget"), errors="coerce").fillna(0),
    })
    return out[out["divisi"].notna() & ~out["divisi"].isin(["nan", ""])]


def prepare_headcount(emp: pd.DataFrame, kode_divisi: dict | None = None) -> pd.DataFrame:
    """Karyawan AKTIF jadi (site, divisi, level_code, status) — 1 baris 1 orang.

    Sejak 8 Sep 2026 sumbernya tab **Existing Employee**, yang sudah punya kolom
    Division, Loc, dan Level yang dibereskan tim — divisi tidak perlu ditebak
    lagi dari huruf pertama Position Code. `kode_divisi` hanya dipakai kalau
    kolom Division tidak ada, supaya sumber lama tetap bisa dibaca.

    Dua aturan dari sheet "Copy of Summary by Division":
      - Staff = Level < 11, Non Staff = Level 11 (Level kosong dibuang).
      - Karyawan **FTAP** dipindah keluar dari Human Capital Management jadi
        divisi sendiri. Position Name mereka selalu diawali "FTAP"; selama
        mereka ikut terhitung di HCM, HCM terlihat jauh lebih besar dari
        kenyataannya.
    """
    d = emp.copy()
    d.columns = [str(c).strip() for c in d.columns]

    # Baris dengan End Date terisi berarti sudah berhenti. Tab Existing Employee
    # sudah tersaring, tapi pengecekan ini tetap ada supaya sumber lama aman.
    akhir = d.get("End Date")
    if akhir is not None:
        kosong = akhir.isna() | akhir.astype(str).str.strip().isin(["", "nan", "NaT"])
        d = d[kosong]

    if "Division" in d.columns:
        divisi = d["Division"].astype(str).str.strip()
    else:
        divisi = (d["Position Code"].astype(str).str.strip().str[0]
                  .map(kode_divisi or {}))

    if "Loc" in d.columns:
        site = d["Loc"].astype(str).str.strip().str.upper()
    else:
        site = d["Location Name"].map(C.LOCATION_TO_SITE)

    lvl = pd.to_numeric(d.get("Level"), errors="coerce")
    posisi = d.get("Position Name")
    ftap = (posisi.astype(str).str.strip().str.upper()
            .str.startswith(C.FTAP_POSITION_PREFIX)
            if posisi is not None else pd.Series(False, index=d.index))

    out = pd.DataFrame({
        "site": site,
        "divisi": divisi.where(~ftap, C.FTAP_DIVISION),
        "level_code": lvl,
        "status": lvl.map(lambda v: "Non Staff" if pd.notna(v) and v >= 11
                          else "Staff" if pd.notna(v) else None),
        "ftap": ftap,
    })
    out = out[out["site"].notna() & out["divisi"].notna()]
    return out[~out["divisi"].isin(["", "nan", "None", "#N/A"])]


def prepare_adp(adp: pd.DataFrame) -> pd.DataFrame:
    """Tabel ADP siap hitung: (site, divisi, status).

    data_loader.load_adp() sudah merapikannya; fungsi ini hanya membakukan
    huruf besar site supaya cocok dengan headcount dan MPP.
    """
    if adp is None or adp.empty:
        return pd.DataFrame(columns=["site", "divisi", "status"])
    d = adp.copy()
    d["site"] = d["site"].astype(str).str.strip().str.upper()
    d["divisi"] = d["divisi"].astype(str).str.strip()
    return d


def _pipeline_per_grup(df: pd.DataFrame, kunci: list[str]) -> pd.DataFrame:
    """Ringkasan proses rekrutmen per grup — dasar kolom monitoring."""
    if df.empty:
        return pd.DataFrame(columns=kunci + ["kandidat", "ongoing", "hired",
                                             "pool", "gagal"])
    baris = []
    for nilai, g in df.groupby(kunci, dropna=False):
        nilai = nilai if isinstance(nilai, tuple) else (nilai,)
        baris.append({**dict(zip(kunci, nilai)), **_ringkas(g)})
    return pd.DataFrame(baris)


# ---------------------------------------------------------------------------
# Sebaran per proses — On Progress / Passed / Failed untuk empat tahap kunci
# ---------------------------------------------------------------------------
# Navi minta Summary by Division bisa digeser ke kanan sampai kelihatan
# "Interview User berapa, Psikotest berapa, Offering berapa, MCU berapa", tiap
# tahap dipecah tiga. Empat tahap ini yang dipilih karena di situlah kandidat
# paling sering tertahan — Screening CV terlalu di depan (hampir semua orang
# lewat), Onboarding terlalu di belakang (sudah jadi angka hired).
PROCESS_STAGES = ["Interview User", "Psychotest", "Offering", "MCU"]
PROCESS_SLUG = {"Interview User": "iu", "Psychotest": "psy",
                "Offering": "off", "MCU": "mcu"}
PROCESS_KINDS = ["progress", "passed", "failed"]

# Kolom Result tiap tahap memakai kosakata yang berbeda-beda: Interview User
# menulis PASSED/FAILED, Offering menulis ACCEPTED/DECLINE/WITHDRAWN. Dipetakan
# ke tiga keadaan yang sama supaya kolomnya bisa dibaca berdampingan.
_HASIL_LULUS = {"PASSED", "PASS", "ACCEPTED", "ACCEPT", "LULUS", "TALENT POOL"}
_HASIL_GAGAL = {"FAILED", "FAIL", "DECLINE", "DECLINED", "REJECTED", "REJECT",
                "WITHDRAWN", "WITHDRAW", "TIDAK LULUS", "CANCEL", "CANCELLED"}
_HASIL_JALAN = {"ON PROGRESS", "ONPROGRESS", "PROGRESS", "HOLD", "PENDING",
                "SCHEDULED", "RESCHEDULE"}


def stage_outcome(sf: pd.DataFrame, df: pd.DataFrame) -> pd.Series:
    """Keadaan tiap (kandidat, tahap): 'progress' / 'passed' / 'failed' / NA.

    Dua sumber, dengan urutan yang jelas:
      1. Kolom Result kalau tahapnya punya — itu keputusan yang ditulis manusia.
      2. Kalau tidak ada (MCU tidak punya kolom Result sama sekali, dan tahap
         lain pun sering dikosongkan), keadaannya disimpulkan dari TANGGAL:
         sudah mulai belum selesai = berjalan; sudah selesai dan kandidat
         lanjut ke tahap berikutnya = lulus; sudah selesai, tidak lanjut, dan
         kandidatnya FAILED = gagal di sini.

    Tahap yang belum pernah disentuh sama sekali menghasilkan NA — bukan nol —
    supaya "belum sampai ke sini" tidak tercampur dengan "sampai sini lalu
    gagal".
    """
    d = sf
    hasil = pd.Series(pd.NA, index=d.index, dtype=object)

    res = d["result"].astype(str).str.strip().str.upper() if "result" in d else None
    if res is not None:
        hasil = hasil.mask(res.isin(_HASIL_LULUS), "passed")
        hasil = hasil.mask(res.isin(_HASIL_GAGAL), "failed")
        hasil = hasil.mask(res.isin(_HASIL_JALAN), "progress")

    disentuh = d["start"].notna() | d["end"].notna()
    berjalan = d["start"].notna() & d["end"].isna()
    hasil = hasil.mask(hasil.isna() & berjalan, "progress")

    # Tahap terjauh yang punya tanggal, per kandidat: dipakai menilai apakah
    # kandidat benar-benar melewati tahap ini atau berhenti di sini.
    terjauh = d[disentuh].groupby("cand_key")["stage_no"].max()
    lanjut = d["cand_key"].map(terjauh) > d["stage_no"]

    stat = d["cand_key"].map(df.drop_duplicates("cand_key")
                             .set_index("cand_key")["status1"])
    selesai = d["end"].notna() & hasil.isna()
    hasil = hasil.mask(selesai & lanjut, "passed")
    hasil = hasil.mask(selesai & ~lanjut & stat.eq("FAILED"), "failed")
    hasil = hasil.mask(selesai & ~lanjut & ~stat.eq("FAILED"), "passed")
    return hasil


def process_breakdown(sf: pd.DataFrame, df: pd.DataFrame,
                      grup: pd.Series) -> pd.DataFrame:
    """Hitung On Progress / Passed / Failed per grup untuk PROCESS_STAGES.

    `grup`: Series ber-index cand_key, isinya label grup (divisi, level, dsb).
    Hasilnya satu baris per label, kolom rata: iu_progress, iu_passed, ...
    """
    kolom = [f"{sl}_{k}" for sl in PROCESS_SLUG.values() for k in PROCESS_KINDS]
    kosong = pd.DataFrame(columns=["_grup"] + kolom)
    if grup is None or not len(grup) or sf.empty:
        return kosong

    d = sf[sf["stage"].isin(PROCESS_STAGES)].copy()
    if d.empty:
        return kosong
    d["_o"] = stage_outcome(d, df)
    d["_grup"] = d["cand_key"].map(grup)
    d = d[d["_grup"].notna() & d["_o"].notna()]
    if d.empty:
        return kosong

    tabel = (d.groupby(["_grup", "stage", "_o"])["cand_key"].nunique()
              .unstack(fill_value=0))
    out = pd.DataFrame(index=sorted(d["_grup"].unique()))
    for tahap, sl in PROCESS_SLUG.items():
        for k in PROCESS_KINDS:
            try:
                kol = tabel.xs(tahap, level="stage")[k]
            except KeyError:
                kol = pd.Series(0, index=out.index)
            out[f"{sl}_{k}"] = kol.reindex(out.index).fillna(0).astype(int)
    return out.reset_index().rename(columns={"index": "_grup"})


def _mpp_dengan_ftap(mpp: pd.Series, aktual: pd.Series) -> pd.Series:
    """MPP divisi FTAP disamakan dengan Actual-nya.

    Future Talent Acceleration Program tidak punya rencana headcount tersendiri
    di MPP2 — orangnya direkrut sebagai program, bukan untuk mengisi posisi yang
    sudah dianggarkan. Kalau MPP-nya dibiarkan nol, Gap FTAP tampil sebagai
    kelebihan orang yang besar dan menutupi kekurangan divisi lain. Disamakan
    dengan Actual, Gap-nya nol dan divisi ini terbaca apa adanya: sekian orang,
    memang segitu rencananya (arahan Navi, 8 Sep 2026).
    """
    out = mpp.copy()
    if C.FTAP_DIVISION in aktual.index:
        out.loc[C.FTAP_DIVISION] = aktual.get(C.FTAP_DIVISION, 0)
    return out


# Sebutan level di sheet ADP tidak sama persis dengan nama level portal.
ADP_LEVEL_ALIAS = {
    "junior staff": "Jr. Staff / Foreman", "jr staff": "Jr. Staff / Foreman",
    "jr. staff": "Jr. Staff / Foreman", "foreman": "Jr. Staff / Foreman",
    "supervisor": "Supervisor", "superintendent": "Superintendent",
    "manager": "Manager", "general manager": "General Manager",
    "non-staff": "Non Staff", "non staff": "Non Staff", "mekanik": "Non Staff",
    "operator": "Non Staff",
}


def adp_level_name(v) -> str | None:
    """Sebutan level di sheet ADP -> nama level yang dipakai portal."""
    t = str(v or "").strip().lower()
    return ADP_LEVEL_ALIAS.get(t)


def _hitung_adp(adp: pd.DataFrame, kunci: str, site: str | None = None,
                divisi: str | None = None) -> pd.Series:
    """Jumlah orang ADP per grup. Kosong kalau tabel ADP tidak tersedia."""
    if adp is None or adp.empty:
        return pd.Series(dtype=int)
    a = adp
    if site:
        a = a[a["site"] == site]
    if divisi is not None:
        a = a[a["divisi"] == divisi]
    if a.empty:
        return pd.Series(dtype=int)
    return a.groupby(kunci).size()


def division_summary(ref: pd.DataFrame, hc: pd.DataFrame, cand: pd.DataFrame,
                     site: str | None = None, level_codes=None,
                     adp: pd.DataFrame | None = None) -> pd.DataFrame:
    """Satu baris per divisi: MPP, Actual, Gap, ADP, Need to hire, plus pipeline.

    `site` None berarti All. `level_codes` menyaring ke level tertentu, dipakai
    saat drill-down sudah masuk ke satu level.

    **Need to hire** = MPP − Actual − ADP, dibatasi minimal nol. Sheet aslinya
    menulis angka ini bertanda terbalik (ADP + Gap, negatif berarti kurang);
    di sini tandanya dibalik supaya kolom bernama "Need to hire" berisi angka
    yang benar-benar berarti "rekrut sekian orang lagi". ADP ikut mengurangi
    karena orang itu sudah menempati posisinya sebagai acting.
    """
    r, h = ref.copy(), hc.copy()
    if site:
        r, h = r[r["site"] == site], h[h["site"] == site]
    if level_codes is not None:
        kode = {str(x) for x in level_codes}
        r = r[r["level_code"].isin(kode)]
        h = h[h["level_code"].map(lambda v: str(int(v)) if pd.notna(v) else "").isin(kode)]

    mpp = r.groupby("divisi")["mpp"].sum()
    aktual = h.groupby("divisi").size()
    mpp = _mpp_dengan_ftap(mpp, aktual)
    pipe = _pipeline_per_grup(cand, ["divisi"]).set_index("divisi") if len(cand) else None

    out = pd.DataFrame({"mpp": mpp}).join(aktual.rename("actual"), how="outer")
    out[["mpp", "actual"]] = out[["mpp", "actual"]].fillna(0).astype(int)
    out["gap"] = out["actual"] - out["mpp"]
    out["adp"] = (_hitung_adp(adp, "divisi", site)
                  .reindex(out.index).fillna(0).astype(int))
    out["need"] = (out["mpp"] - out["actual"] - out["adp"]).clip(lower=0)
    for k in ("kandidat", "ongoing", "hired", "pool", "gagal"):
        out[k] = (pipe[k] if pipe is not None and k in pipe else 0)
        out[k] = out[k].reindex(out.index).fillna(0).astype(int)
    out = out[(out[["mpp", "actual", "kandidat"]].sum(axis=1) > 0)]
    return out.sort_values(["gap", "mpp"]).reset_index().rename(
        columns={"index": "divisi"})


def level_summary(ref: pd.DataFrame, hc: pd.DataFrame, cand: pd.DataFrame,
                  divisi: str, site: str | None = None,
                  adp: pd.DataFrame | None = None) -> pd.DataFrame:
    """Sebaran satu divisi per LEVEL, urut dari level paling bawah ke atas."""
    r = ref[ref["divisi"] == divisi]
    h = hc[hc["divisi"] == divisi]
    c = cand[cand["divisi"] == divisi] if len(cand) else cand
    if site:
        r, h = r[r["site"] == site], h[h["site"] == site]
        c = c[c["site"] == site] if len(c) else c

    # Dikelompokkan berdasarkan NAMA level, bukan kodenya: level 7 dan 6 sama-sama
    # "Manager", dan menampilkannya sebagai dua baris Manager yang berbeda hanya
    # membingungkan pembaca yang tidak tahu kode di baliknya.
    r = r.copy()
    r["_k"] = r["level_code"].map(C.level_name)
    mpp = r.groupby("_k")["mpp"].sum()

    h = h.copy()
    h["_k"] = h["level_code"].map(C.level_name)
    aktual = h.groupby("_k").size()
    # Divisi FTAP: MPP tiap levelnya mengikuti Actual, sama seperti di tingkat
    # divisi — kalau tidak, satu-satunya level FTAP akan tampil kelebihan orang.
    if divisi == C.FTAP_DIVISION:
        mpp = aktual.astype(float).copy()

    pipe = None
    if len(c):
        c = c.copy()
        c["_k"] = c["level_code"].map(C.level_name)
        pipe = _pipeline_per_grup(c, ["_k"]).set_index("_k")

    out = pd.DataFrame({"mpp": mpp}).join(aktual.rename("actual"), how="outer")
    out[["mpp", "actual"]] = out[["mpp", "actual"]].fillna(0).astype(int)
    out["gap"] = out["actual"] - out["mpp"]

    # ADP ditempatkan di level yang benar-benar sedang dia duduki (kolom "Level
    # Acting" di sheet ADP), bukan level asalnya — yang berkurang kebutuhannya
    # adalah posisi yang sedang dia isi.
    out["adp"] = 0
    if adp is not None and not adp.empty and "level" in adp.columns:
        a = adp[adp["divisi"] == divisi]
        if site:
            a = a[a["site"] == site]
        if len(a):
            per = a.assign(_k=a["level"].map(adp_level_name)).dropna(subset=["_k"])
            hit = per.groupby("_k").size()
            for nama in out.index:
                out.loc[nama, "adp"] = int(hit.get(nama, 0))
    out["adp"] = out["adp"].fillna(0).astype(int)
    out["need"] = (out["mpp"] - out["actual"] - out["adp"]).clip(lower=0)

    for k in ("kandidat", "ongoing", "hired", "pool", "gagal"):
        out[k] = (pipe[k] if pipe is not None and k in pipe else 0)
        out[k] = out[k].reindex(out.index).fillna(0).astype(int)

    out = out[(out[["mpp", "actual", "kandidat"]].sum(axis=1) > 0)]
    # Indeksnya gabungan dua sumber, jadi namanya belum tentu "level_code";
    # disebut eksplisit supaya tidak bergantung pada nama bawaan pandas.
    out.index.name = "level"
    out = out.reset_index()

    # Urutan tampil mengikuti LEVEL_ORDER, dari level paling bawah ke paling atas.
    urut = {}
    for i, k in enumerate(C.LEVEL_ORDER):
        urut.setdefault(C.level_name(k), i)
    out["_u"] = out["level"].map(lambda v: urut.get(v, 99))
    # Kode level pertama yang memakai nama itu — dipakai menyaring saat detail
    # level dibuka.
    kode_pertama = {}
    for k in C.LEVEL_ORDER:
        kode_pertama.setdefault(C.level_name(k), k)
    out["level_code"] = out["level"].map(kode_pertama)
    return out.sort_values("_u").drop(columns="_u").reset_index(drop=True)


def candidate_level_code(df: pd.DataFrame) -> pd.Series:
    """Level kandidat (teks) -> kode angka, supaya bisa disandingkan dengan MPP."""
    balik = {}
    for kode, nama in C.LEVEL_CODE_NAMES.items():
        balik.setdefault(nama.strip().lower(), kode)
    # Sebutan di database kandidat tidak selalu sama persis dengan peta di atas.
    balik.update({
        "junior staff": 10, "jr. staff": 10, "jr staff": 10, "foreman": 10,
        "supervisor": 9, "superintendent": 8, "manager": 7,
        "general manager": 5, "non staff": 11, "boards": 1, "commisioner": 0,
    })
    return df["level"].astype(str).str.strip().str.lower().map(balik)
