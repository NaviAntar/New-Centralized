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
from theme import STAGE_ORDER

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
            "Kolom 'candidate_id' tidak ada. Kemungkinan besar yang terambil "
            "bukan tab fix_centralized — periksa gid/nama tab di config.py."
        )

    df = df[df["candidate_id"].notna() & (df["candidate_id"].astype(str).str.strip() != "")]
    df = df.reset_index(drop=True)

    for col in _ID_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().replace({"nan": None, "": None})

    if "loc" in df.columns:
        df["loc"] = df["loc"].str.upper()
    if "status1" in df.columns:
        df["status1"] = df["status1"].str.upper()

    for stage, (s_col, e_col, *_rest) in STAGE_COLUMNS.items():
        for col in (s_col, e_col):
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
    return df


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
            block["pic_initial"] = df[pic_col].astype(str).str.strip().str.upper().replace({"NAN": None, "": None})
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
    furthest = touched.groupby("cand_key")["stage_no"].max()
    rows = []
    base = None
    prev = None
    for i, stage in enumerate(STAGE_ORDER, start=1):
        n = int((furthest >= i).sum())
        # Screening CV jadi basis konversi, bukan PRF: kolom PRF hanya terisi di
        # 422 dari 1.396 baris, jadi memakainya membuat konversi tahap kedua
        # terlihat di atas 300%.
        if stage == "Screening CV":
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
    """Inisial di database -> nama lengkap. None kalau tidak ada di roster."""
    if not initial:
        return None
    mapping = dict(C.RECRUITER_NAMES)
    if extra_map:
        mapping.update({k.strip().upper(): v for k, v in extra_map.items() if k and v})
    return mapping.get(str(initial).strip().upper())


def recruiter_performance(sf: pd.DataFrame, date_from=None, date_to=None,
                          extra_map: dict | None = None) -> pd.DataFrame:
    """Tabel performance per PIC.

    Definisi (sesuai arahan Navi):
      SLA Actual   rata-rata, per kandidat, dari JUMLAH durasi tahap yang PIC
                   itu tangani. Bukan lead time PRF-sampai-akhir — orang hanya
                   diukur atas tahap yang benar-benar ia pegang.
      SLA Budget   rata-rata dari jumlah budget tahap yang SAMA, memakai budget
                   level kandidat masing-masing. Jadi Actual dan Budget selalu
                   membandingkan komposisi tahap yang identik.
      Achievement  Budget / Actual x 100. Di atas 100% = lebih cepat dari target.
      Onboarding   jumlah kandidat berstatus CLOSE yang PIC itu tangani.

    Filter tanggal merujuk ke TANGGAL SCREENING CV kandidat, bukan tanggal tahap.
    Dengan begitu satu kandidat selalu utuh di dalam satu periode dan tidak
    terbelah antar bulan.

    PENTING: kolom Onboarding TIDAK bisa dijumlahkan ke bawah. Satu kandidat
    ditangani beberapa PIC dan tiap PIC mendapat kreditnya (keputusan Navi),
    jadi jumlah kolom ini lebih besar dari jumlah hire sebenarnya.
    """
    work = sf[sf["pic_initial"].notna() & sf["lt"].notna() & sf["budget"].notna()].copy()

    if date_from is not None:
        work = work[work["screening_date"] >= pd.Timestamp(date_from)]
    if date_to is not None:
        work = work[work["screening_date"] <= pd.Timestamp(date_to)]

    work["name"] = work["pic_initial"].map(lambda i: recruiter_name(i, extra_map))
    work["name"] = work["name"].fillna(C.OTHER_RECRUITER_LABEL)

    # Langkah 1: gabungkan per (PIC, kandidat) — inilah "SLA kandidat A" milik
    # orang itu, yaitu jumlah tahap yang ia pegang untuk kandidat tersebut.
    per_cand = work.groupby(["name", "cand_key"]).agg(
        lt=("lt", "sum"),
        budget=("budget", "sum"),
        stages=("stage", "nunique"),
        hired=("status1", lambda s: (s == "CLOSE").any()),
    ).reset_index()

    # Langkah 2: rata-ratakan lintas kandidat.
    g = per_cand.groupby("name").agg(
        sla_actual=("lt", "mean"),
        sla_budget=("budget", "mean"),
        candidates=("cand_key", "nunique"),
        stages=("stages", "sum"),
        onboarding=("hired", "sum"),
    )
    g["achievement"] = (g["sla_budget"] / g["sla_actual"] * 100).where(g["sla_actual"] > 0)

    # Roster selalu tampil lengkap, termasuk orang yang belum punya data —
    # baris nol lebih jujur daripada nama yang hilang begitu saja.
    g = g.reindex(g.index.union(C.RECRUITER_ROSTER, sort=False))
    g[["candidates", "stages", "onboarding"]] = g[["candidates", "stages", "onboarding"]].fillna(0).astype(int)

    order = {n: i for i, n in enumerate(C.RECRUITER_ROSTER)}
    g["_sort"] = [order.get(n, 90 if n == C.OTHER_RECRUITER_LABEL else 50) for n in g.index]
    g = g.sort_values(["_sort"]).drop(columns="_sort")

    return g.reset_index().rename(columns={"index": "name"}).round(
        {"sla_actual": 1, "sla_budget": 1, "achievement": 1})


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
