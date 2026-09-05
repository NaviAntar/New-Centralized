# HR Recruitment Portal — PT Darma Henwa

Aplikasi Streamlit pengganti dashboard Centralized. Mengikuti sistem desain
FTE Calculator: band oranye, kartu putih di atas abu terang, aksen navy,
Archivo + Public Sans.

---

## Deploy ke Streamlit Cloud

1. Push seluruh isi folder ini ke GitHub (repo boleh privat).
2. Di [share.streamlit.io](https://share.streamlit.io): **New app** → pilih repo →
   **Main file path** diisi `app.py`.
3. Buka **Advanced settings → Secrets**, tempel:

   ```toml
   [auth]
   recruitment = "RecruitmentPTDH"
   user = "UserPTDH"
   ```

4. Deploy.

`.streamlit/secrets.toml` sudah masuk `.gitignore` supaya password tidak ikut
ter-commit. Kalau file itu tidak ada, aplikasi jatuh ke nilai default di
`config.py` — cukup untuk uji coba, tapi ganti sebelum dipakai produksi.

**Syarat data:** ketiga spreadsheet harus di-share minimal
*Anyone with the link — Viewer*, kalau tidak Google mengembalikan halaman login
dan aplikasi menampilkan pesan error yang menyebutkan hal ini.

## Jalankan lokal

```bash
pip install -r requirements.txt
streamlit run app.py
```

Untuk bekerja tanpa menyentuh Google Sheets (mis. saat mengembangkan tampilan):

```bash
CENTRALIZED_CSV=/path/ke/fix_centralized.csv streamlit run app.py
```

---

## Peran & akses

| Halaman | Recruitment | User |
|---|:--:|:--:|
| Overview | ✓ | ✓ |
| Weekly Report | ✓ | ✓ |
| Tracking Kandidat | ✓ | ✓ |
| Tracking Posisi | ✓ | ✓ |
| Recruitment Room | ✓ | — |
| Export, hapus cache | ✓ | — |

Peran User yang mencoba membuka Recruitment Room lewat session state dialihkan
ke Overview. Nama kandidat tampil penuh di kedua peran.

## Struktur file

| File | Isi |
|---|---|
| `app.py` | Entrypoint: router, nav, dan empat halaman yang sudah jadi |
| `theme.py` | Sistem desain — token warna, satu blok CSS, komponen yang mengembalikan HTML |
| `charts.py` | Chart Plotly. Warna diambil dari token `theme.py`, tidak ada hex di sini |
| `config.py` | SLA per level, kalender libur, ID spreadsheet, password, roster recruiter |
| `metrics.py` | Semua perhitungan. Murni pandas, bisa dites tanpa Streamlit |
| `data_loader.py` | Pengambilan dari Google Sheets + rantai fallback |
| `auth.py` | Gerbang login dua tingkat |

Aturan yang menjaga aplikasi ini tetap konsisten:

- **Tidak ada halaman yang menghitung sendiri.** Semua angka lewat `metrics.py`.
  Versi lama menampilkan dua lead time berbeda untuk orang yang sama karena
  perhitungan tersebar di dua halaman.
- **Tidak ada hex di luar `theme.py`.** Ganti satu token, seluruh chart dan
  badge ikut berubah.
- **Semua teks dari data di-escape** sebelum masuk HTML (`theme.esc`). Portal ini
  menampilkan nama orang dan alasan keterlambatan yang diketik manusia.

---

## Cara lead time dihitung

**Hari kerja, inklusif.** Mulai dan selesai di hari kerja yang sama = 1 hari.
Sabtu, Minggu, dan libur nasional tidak dihitung.

Ini bukan definisi baru. Rumusnya dicocokkan terhadap kolom LT yang sudah ada di
spreadsheet dan **cocok 100% di 6.478 baris, sebelas tahap** — jadi angka portal
bisa langsung disandingkan dengan angka yang biasa dilihat tim.

Kalender libur dibaca dari `Monitoring 2026 › Backend` kolom A. Kalau sheet itu
tidak bisa diambil, dipakai salinan cadangan di `config.HOLIDAYS_FALLBACK`.

Portal menyediakan dua ukuran yang sengaja dipisah:

- `lt_stage_sum` — jumlah durasi tahap. Dipakai menilai kinerja PIC, karena orang
  hanya bertanggung jawab atas tahap yang ia pegang.
- `lt_elapsed` — selisih tanggal ujung ke ujung. Ini yang dirasakan user dan
  manajemen. Selisih keduanya (`lt_idle`) adalah waktu proses menganggur.

## SLA per level

Sumber: `Monitoring 2026 › Backend`. Ini menggantikan kolom `budget_lt1` di
database, yang berisi angka 16 hari lebih longgar dan membuat 99,4% kandidat
tampil "Onbudget".

| Level | Total | Catatan |
|---|--:|---|
| General Manager | 70 | |
| Manager | 70 | |
| Superintendent | 63 | |
| Supervisor | 61 | |
| Junior Staff | 60 | |
| Non Staff | 61 | Junior Staff + Technical Test 1 hari |

Technical Test hanya berlaku Non Staff — dikonfirmasi data: 235 dari 239 kandidat
Non Staff punya tanggalnya, nol di seluruh level lain. Untuk level lain, tahap ini
ditandai "tidak berlaku", bukan "pending", sehingga progress bar bisa mencapai 100%.

## Pemetaan kolom tanggal

Tiap pasangan diuji terhadap kolom LT yang sudah ada; hanya yang cocok 100%
dipakai. Dua di antaranya berbeda dari label lamanya:

- **MCU** berakhir di `mcu_issue_date`, bukan `mcu_date`.
- **One Month Notice** = `date_fit` → `date_onboarding`, budget 30 hari. Versi
  lama melabelinya "Onboarding"; Onboarding sendiri hanya milestone 1 hari.

---

## Yang masih perlu dilengkapi

### 1. Form Apps Script harus mengizinkan penyematan

Iframe di Recruitment Room akan kosong sampai `doGet()` di `Code.gs`
mengembalikan output dengan mode X-Frame `ALLOWALL`.

**Sebelum** — bentuk yang biasa dipakai:

```js
function doGet(e) {
  return HtmlService.createTemplateFromFile('Form').evaluate()
    .setTitle('Form Monitoring Recruitment');
}
```

**Sesudah** — tambahkan satu baris `.setXFrameOptionsMode(...)`:

```js
function doGet(e) {
  return HtmlService.createTemplateFromFile('Form').evaluate()
    .setTitle('Form Monitoring Recruitment')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
```

Kalau `doGet` memakai `createHtmlOutputFromFile` (bukan template), polanya sama:

```js
function doGet(e) {
  return HtmlService.createHtmlOutputFromFile('Form')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
```

Setelah diubah: **Deploy → Manage deployments → ikon pensil → Version: New
version → Deploy.** Menyimpan file saja tidak cukup; URL web app baru memakai
kode terbaru setelah versi baru di-deploy.

`addMetaTag('viewport', ...)` bukan keharusan, tapi membuat form ikut menyesuaikan
lebar iframe alih-alih tampil kecil di pojok.

Kalau form perlu tahu sedang dibuka untuk site mana, `e.parameter` bisa dibaca:

```js
function doGet(e) {
  var site = (e && e.parameter && e.parameter.site) || 'HO';
  var t = HtmlService.createTemplateFromFile('Form');
  t.site = site;   // dipakai di Form.html lewat <?= site ?>
  return t.evaluate()
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}
```

### 2. Form dan spreadsheet per site

`config.FORM_URLS` dan `config.SHEET_URLS` menyimpan satu URL per site. HO
memakai form baru (Staff); BCP, KCP, dan ACP sementara memakai form Centralized
yang sudah berjalan selama ini. Mengganti form sebuah site cukup satu baris:

```python
FORM_URLS = {
    "HO":  "https://script.google.com/macros/s/AKfycby.../exec",
    "BCP": "https://script.google.com/macros/s/PASTE_URL_BARU/exec",
}
```

SSCP belum punya keduanya, jadi halamannya menyatakan itu apa adanya.

### 3. Inisial recruiter yang belum dipetakan

Tiga orang di roster belum punya inisial di `config.RECRUITER_NAMES`:
Muhammad Faiq Kenzie Widodo, Tallita Ayu Salsabila, Fachry. Sesuai arahan Navi
ini dibiarkan — mereka tampil dengan nilai nol, bukan mengambil data orang lain.

Kalau nanti inisialnya ketemu, ada dua cara memasukkannya:

Tambahkan ke `RECRUITER_NAMES` di `config.py` kalau inisialnya sudah diketahui.

Inisial yang masih menganggur, diurutkan dari yang tersibuk: `AIC` (550
aktivitas) · `FLI` (175) · `BEL` (112) · `SOM` (62) · `JAZ` (42) · `MEI` (5) ·
`ADR` (1). Sudah diketahui bukan milik roster: `RAF` = Rafi'ud A ·
`MRB` = M. Ribi H · `NAV` = Navi A · `IRV` = Irviyani.

### 4. Lead time Non Staff belum bisa diukur

163 dari 164 hire Non Staff punya tanggal screening, interview, dan onboarding
yang persis sama — input borongan di KCP tanggal 5 dan 7 Januari 2026. SLA
Non Staff yang sudah dipasang baru bermakna setelah site mengisi tanggal per
tahap. Sampai itu terjadi, semua metrik lead time mengecualikan Non Staff dan
hal itu dinyatakan terbuka di layar.

---

## Status halaman

| Halaman | Status |
|---|---|
| Overview | Ringkasan (5 kartu) + embed Looker — dua bagian saja |
| Weekly Report | Performance recruiter, New Hire, ringkasan site, On Progress, karyawan resign — semuanya mengikuti satu baris filter |
| Tracking Kandidat | Satu kotak pencarian, tabel tahap, progress bar, kartu SLA |
| Tracking Posisi | Satu kotak pencarian, langsung ke detail posisi dan kandidatnya |
| Recruitment Room | Pilih site → link form & spreadsheet → form tersemat |

Halaman yang belum dibangun tetap bisa dibuka dan menampilkan daftar isi yang
akan masuk ke sana, supaya tidak ada tombol yang mati tanpa penjelasan.

### Catatan tiap halaman

**Overview.** Dashboard Looker tetap disematkan di bagian bawah. Filter site di
halaman ini hanya berlaku untuk kartu dan chart portal — Looker punya filternya
sendiri dan menghitung terpisah.

**Weekly Report.** Satu baris filter di atas — Tahun, Bulan, Site — mengatur
SELURUH bagian di bawahnya: Performance, New Hire, Ringkasan per site,
On Progress, dan Karyawan resign.

Tabel Performance dihitung dua langkah:

1. Kumpulkan kandidat yang ditangani orang itu.
2. Untuk **setiap tahap proses** — PRF Approval sampai Onboarding — hitung
   rata-rata lead time dan rata-rata budget di antara kandidat tadi.
3. Jumlahkan rata-rata itu lintas tahap. Tidak dibagi lagi.

Yang penting di langkah 2: seluruh tahap ikut, bukan hanya tahap yang punya
kolom PIC di database. Versi sebelumnya hanya menghitung tujuh tahap ber-PIC,
sehingga One Month Notice yang budget-nya saja 30 hari ikut terbuang dan total
budget keluar cuma ~20 hari — mustahil untuk proses bertarget 60+ hari. Sekarang
SLA Budget sejalan dengan matriks di `Monitoring 2026 › Backend`.

Filter bulan bisa memilih lebih dari satu. Memilih dua bulan membuat New Hire
dan Ringkasan per site menampilkan satu kolom untuk tiap bulan plus kolom Total.
Periodenya merujuk ke tanggal **screening CV** untuk Performance, tanggal
**onboarding** untuk New Hire dan Ringkasan per site, tanggal tahap
masing-masing untuk On Progress, dan tanggal **resign** untuk Karyawan resign.

**On Progress dan Karyawan resign** mereplikasi rumus QUERY yang sudah dipakai
tim di sheet ONP dan Karyawan Resign, bukan tafsiran sendiri:

| Panel | Aturan |
|---|---|
| Offering | status OPEN, tahap Offering, START REQ OFFERING di bulan berjalan |
| MCU | status OPEN, tahap MCU/Review MCU/FU MCU, OL SENT di bulan berjalan |
| Onboarding | hasil MCU FIT TO WORK dan tanggal onboarding masih di depan |
| Resign | dari sheet `Update MPP`: level < 11, posisi bukan Internship, berhenti di bulan berjalan, dan berhenti sebelum kontrak habis atau tidak punya tanggal akhir kontrak |

Panel resign diverifikasi terhadap sheet: **18 dari 18 nama cocok persis** untuk
Agustus 2026.

Kolom **Kandidat** dan **Onboarding** dihitung dari **PIC Screening CV saja**,
sesuai permintaan Navi: satu kandidat hanya dikreditkan ke satu orang, jadi kedua
kolom itu boleh dijumlahkan ke bawah tanpa dobel. SLA-nya tetap dihitung dari
seluruh tahap yang orang itu tangani — dua ukuran yang beda dasar, dan memang
sengaja.

Sheet **Summary** belum punya kolom Need. Angka kebutuhan berasal dari weekly
report dan portal belum menyambungnya; menampilkan kolom kosong bernama Need
akan lebih menyesatkan daripada tidak menampilkannya.

**Tracking Kandidat & Tracking Posisi.** Keduanya memakai satu kotak saja, dan
daftarnya menyusut **sambil diketik** — tidak perlu menekan tombol apa pun.

Yang dicocokkan hanya **nama** (di Tracking Kandidat) atau **nama posisi** (di
Tracking Posisi). Keterangan lain — posisi, departemen, level, site — muncul di
bawah setelah dipilih, bukan ikut jadi bahan pencarian. Kalau labelnya memuat
semua keterangan itu, mengetik "tika" ikut memunculkan orang yang cuma kebetulan
departemennya mengandung "tika".

Nama yang kembar diberi pembeda seperlunya: nama posisi dulu, dan site hanya
kalau posisinya pun sama.

Tracking Posisi langsung menampilkan detail posisi yang dipilih; tabel hasil
pencarian sudah dihapus. Kolom kandidatnya: nama, posisi, departemen, level,
loc, last progress, total LT, dan status.

**Panjang tabel.** New Hire, Ringkasan per site, On Progress, Karyawan resign,
dan daftar kandidat per posisi dibatasi **10 baris terlihat**; sisanya digulir
di dalam kotak tabel dengan header yang tetap menempel. Tanpa batas ini satu
panel On Progress berisi 200 baris mendorong seluruh bagian lain jauh ke bawah.

**Site kosong.** Kandidat yang kolom `loc`-nya tidak terisi dimasukkan ke
**BPN**, bukan ditampilkan sebagai baris "(tanpa site)".


**Departemen yang terisi nama posisi.** Sebagian baris database mengisi kolom
`departement` dengan nama posisi ("Foreman - DMS Operation"), sehingga New Hire
dulu memunculkan nama posisi seolah-olah departemen. Portal memperbaikinya lewat
master `Monitoring 2026 › MPP 2026` (660 Position ID, 685 nama posisi, 56
departemen sah), dengan urutan: nilai yang memang departemen dipakai apa adanya →
cari lewat Position ID → cari lewat nama posisi → contek baris lain dengan posisi
sama → sisanya dikumpulkan ke satu baris "Belum diisi di sumber".

Dua jebakan yang sudah ditutup:

* Endpoint **gviz by nama tab** memotong sheet MPP 2026 di **baris ke-4**. Portal
  memakai `export?format=csv&gid=354501614` lebih dulu dan gviz hanya cadangan.
  Kalau master terbaca kurang dari 20 departemen, master itu **tidak dipakai sama
  sekali** — lebih baik jatuh ke acuan cadangan daripada menganggap semua
  departemen asli tidak sah dan meruntuhkan laporan jadi satu baris.
* Di sheet MPP 2026 judul kolom **"Position" dan "PositionID" tertukar dengan
  isinya** (yang berjudul Position berisi kode, yang berjudul PositionID berisi
  nama). Portal menukarnya balik saat membaca; kalau nanti sheetnya diperbaiki,
  ubah `MPP_HEADER_SWAPPED = False` di `config.py`.

Sisanya, **711 baris** memang belum bisa dipetakan, dan itu perkara data bukan
kode: 566 baris kolom departemennya kosong di sumber, sisanya memakai posisi yang
belum ada di MPP 2026 (rata-rata posisi baru berkode 11 digit seperti
`E26E0200002`, `P26P0470002` — SSCP). Di New Hire hanya 50 dari 414 yang jatuh ke
"Belum diisi di sumber".

**Tanggal di sheet Update MPP** ditulis hari-dulu (`03/01/2026` = 3 Januari).
Dibaca dengan format eksplisit `%d/%m/%Y`, bukan tebakan pandas — kalau tidak,
tanggal 1–12 berisiko terbalik jadi bulan dan daftar resign salah periode.


## fix_centralized vs Backend Monitoring — kolom lookup yang belum ditarik

Per 30 Agu 2026, **566 baris** di `fix_centralized` punya Position ID tapi kolom
POSITION NAME, LEVEL, DEPARTMENT dan LOC-nya **kosong** — kolom lookup yang belum
ditarik ke bawah untuk baris baru (hampir semuanya SSCP). Akibatnya di portal
kandidat SSCP tercatat tanpa site, lalu ikut terhitung sebagai BPN, dan tanpa
departemen.

Baris yang sama di `Report › Backend Monitoring` (gid 0) **sudah terisi lengkap**
— itulah sheet yang dilihat tim di dashboard monitoring. Portal memakai sheet itu
sebagai penambal identitas: `data_loader.load_backend_monitoring()` +
`metrics.set_row_master()`, dicocokkan dengan kunci **nama + Position ID** supaya
orang yang melamar dua posisi tidak tertukar.

Penambalan ini **hanya mengisi lubang**, tidak menimpa nilai yang sudah ada.
`fix_centralized` tetap sumber utama karena punya kolom Technical Test dan
seluruh peta tahap portal.

Hasilnya (Agustus 2026): Ringkasan per site berubah dari *BPN 29* menjadi
**SSCP 30 · BCP 10 · JKT 2 · BPN 1 · KCP 1**, dan New Hire yang jatuh ke
"Belum diisi di sumber" turun dari **30 menjadi 1**. Sepanjang 2026, dari 414
hire hanya **3** yang belum berdepartemen dan **2** yang benar-benar tanpa site.

Sisa 37 baris tanpa site memang tidak punya Position ID di kedua sheet — ini
perkara input, bukan lookup.

## Satu departemen, beberapa ejaan

Tiga sheet menulis HSE dengan tiga ejaan berbeda: `fix_centralized` dan MPP 2026
menulis "Environent", Backend Monitoring "Environment", sheet Report
"Environtment". Tanpa penyatuan, New Hire menampilkan dua baris untuk departemen
yang sama. `config.DEPT_ALIASES` menyatukannya — daftarnya sengaja pendek dan
eksplisit supaya terlihat persis apa yang digabung.


## Halaman PRF Tracking

Sumbernya spreadsheet **PRF Management › tab "PRF Tracking"** (`config.PRF_*`),
terpisah dari database kandidat: PRF terjadi SEBELUM ada kandidat, jadi tidak
bisa diturunkan dari fix_centralized.

**Kartu.** Jumlah PRF · Approved · Not Approved · Status Close. Approved dan Not
Approved dibaca dari kolom **Tracking PRF**; Status Close dari kolom **Status**,
dan persentasenya terhadap **total PRF** (bukan terhadap yang approved saja),
sesuai permintaan Navi.

Semua angka menghitung **baris PRF**, bukan qty orang. Satu PRF bisa meminta 14
orang sekaligus; menjumlahkan qty menjawab pertanyaan yang berbeda dari "berapa
PRF yang sudah approved". Qty tetap tampil per baris di tabel, dan total qty
disebut sebagai keterangan kecil di kartu Jumlah PRF.

**Filter.** Site · Level · Jenis Level · Tracking PRF · Status PRF. Site, Level,
dan Jenis Level diambil dari data. Tracking PRF dan Status PRF memakai daftar
tetap di `config.PRF_TRACKING_VALUES` dan `config.PRF_STATUS_VALUES` — CLOSE dan
CANCEL belum pernah ada satu baris pun, dan filter yang menyusut sendiri terbaca
seperti fitur yang hilang, bukan seperti keadaan yang memang belum terjadi.

**Jenis Level.** Staff = Junior Staff, Supervisor, Superintendent, Manager,
General Manager, Boards, Commisioner (`config.PRF_STAFF_LEVELS`). Sisanya —
apa pun isinya — masuk Non Staff, jadi level baru tidak diam-diam hilang dari
filter. Baris yang levelnya kosong ditandai "—", bukan Non Staff: itu klaim yang
tidak ada dasarnya. Per 2 Sep 2026 seluruh 144 baris berlevel Staff.

**Kolom identitas.** Tabel memakai satu kolom **Request Number** saja: kalau
`request_number` kosong, dipakai `ID PRF`. Dua kolom untuk satu identitas, yang
masing-masing separuhnya kosong, hanya menyulitkan pembacaan — per 2 Sep 2026 ada
3 baris yang baru punya ID PRF (`H15P1`, `H12P1`, `H12P2`).


## Unduh tabel: Excel dan Gambar

Tiap tabel punya dua tombol kecil di ujung kanan atasnya. Yang diunduh adalah
**tabel yang sedang tampil**, sudah kena filter halaman — bukan data mentah.
Kalau yang keluar selalu data mentah, orang mengirimkan berkas yang isinya
berbeda dari yang baru saja mereka lihat di layar, dan itu jenis kesalahan yang
baru ketahuan setelah berkasnya beredar.

Karena itu semua tabel lewat satu pintu, `app.tabel()`, bukan langsung ke
`theme.data_table()`: satu sumber baris, dua cara menampilkannya.

**Excel (.xlsx).** Header bergaya portal, freeze pane, autofilter, dan satu baris
catatan berisi judul + filter aktif + tanggal unduh. Angka yang di layar diformat
gaya Indonesia (`1.150`, `40,4`, `166,2%`) dikembalikan jadi **angka betulan** di
Excel — kalau dibiarkan teks, kolomnya tidak bisa dijumlahkan atau diurutkan,
padahal itu alasan orang mengunduh ke Excel. Teks yang kebetulan berbentuk angka
tidak ikut dikonversi: pola pencocokannya harus cocok seluruh teks, dan nilai
berawalan nol (`013`) tetap teks karena itu kode, bukan angka.

**Gambar (.png).** Tabelnya digambar ulang dengan matplotlib memakai warna yang
sama dengan di layar — Streamlit tidak bisa memotret dirinya sendiri. Hasilnya
justru lebih rapi: tidak ada scrollbar, tidak terpotong, dan **seluruh baris
ikut** walau di layar harus digulir. Dipakai untuk ditempel ke deck atau dikirim
di WhatsApp.

Tabel di atas **60 baris** tidak digambar otomatis — menggambar 257 baris perlu
~2 detik dan menghasilkan berkas 3 MB, biaya yang tidak pantas dibayar setiap
kali filter digeser. Tombolnya jadi "siapkan dulu": klik sekali untuk menyiapkan,
lalu tombolnya berubah jadi unduhan. Hasilnya di-cache, jadi filter yang sama
tidak digambar dua kali.

**Siapa yang bisa mengunduh.** Hanya peran Recruitment — peran User memang tidak
diberi export sejak awal. Kalau mau dibuka untuk semua, ubah `export` di
`config.ACTION_ACCESS`.

Tabel Tahap seleksi memakai penampil sendiri (`theme.stage_table`) karena tiap
barisnya berisi lencana status, tapi tetap bisa diunduh lewat `app.unduh_saja()`.
Di berkasnya lencana jadi teks — di Excel dan di gambar, warna saja tidak cukup
untuk menyampaikan "Late".

## Talent pool

Kandidat yang lolos seleksi tapi belum ditempatkan — posisinya sudah terisi orang
lain, atau kebutuhannya belum ada. Ditandai lewat kolom **Result** di tahap mana
pun oleh form Apps Script, bukan lewat satu kolom khusus: keputusan itu diambil
di tahap yang berbeda-beda per orang.

**Dampaknya ke arti CLOSE.** Sebuah proses sekarang bisa berakhir dengan dua cara
yang sama-sama "selesai" tapi sangat berbeda maknanya:

| | Artinya |
|---|---|
| Close — Onboarding | orangnya masuk kerja |
| Talent pool | orangnya disimpan untuk kebutuhan berikutnya |

Menjumlahkan keduanya jadi satu angka "hire" membuat pencapaian rekrutmen
terlihat lebih besar dari kenyataan, jadi di Overview keduanya berdiri sendiri.
Kartu Talent pool menghitung **semua** orang di pool apa pun `status1`-nya —
sebagian baris masih tertulis OPEN di sheet padahal keputusannya sudah diambil di
kolom Result.

**Tabelnya hidup di Recruitment Room**, bukan di Overview: di Overview orang cuma
melihat angkanya, di Recruitment Room orang menindaklanjutinya — dan nomor HP-nya
justru berguna saat filter site/PIC sudah dipersempit. Daftarnya ikut seluruh
filter halaman itu.

Isinya nama, nomor HP, posisi yang dilamar, dan departemen sesuai permintaan, ditambah tiga kolom yang membuatnya bisa langsung dipakai menelepon
orang: **Site** (siapa yang menghubungi), **Level** (posisi apa yang pantas
ditawarkan), dan **Tahap** tempat dia masuk pool (semakin jauh tahapnya, semakin
sedikit seleksi yang perlu diulang).

Nomor HP diambil dari kolom `No Telpon` di `Report › Backend Monitoring` —
`fix_centralized` tidak punya kolomnya sama sekali.

## Tracking Posisi — dua mode

| Mode | Menjawab |
|---|---|
| **Per Posisi** (default) | "posisi X isinya siapa?" |
| Per Departemen | "departemen saya sudah sampai mana?" |

Mode Site dihapus: pertanyaannya sudah terjawab oleh filter Site yang berlaku di
kedua mode, dan mode ketiga hanya menambah pilihan tanpa menambah jawaban.

Pemilih modenya `st.segmented_control`, bukan radio bertitik — dua pilihan yang
saling meniadakan lebih terbaca sebagai dua tombol berdampingan.

**Filter bersama kedua mode:** bulan (multi-pilih, patokannya tanggal
**Screening CV**) dan site. Screening CV dipakai sebagai patokan periode di
seluruh portal karena itu tanggal kandidat masuk proses, jadi satu kandidat
selalu utuh dalam satu bulan. Kalau patokannya tanggal tahap terakhir, orang yang
sama pindah-pindah bulan setiap prosesnya maju, dan angka bulan lalu berubah
sendiri.

**Mode Per Departemen bertingkat, bukan tabel.** Pilih departemen di dropdown →
ringkasannya muncul (kartu + batang sebaran + chip "yang masih berjalan berhenti
di mana") → di bawahnya posisi yang dibuka, satu per satu bisa dibuka untuk
melihat sebaran dan siapa yang sedang diproses. Melihat semua posisi sekaligus
sebagai tabel bukan tracking, cuma daftar.

Yang tampil lebih dulu hanya posisi yang **masih ada orangnya jalan** — itu arti
"posisi yang dibuka". Plant & Maintenance punya 79 posisi tercatat dan hanya 35
yang masih berjalan; ada tombol untuk memunculkan sisanya.

**Komponen visual baru** menggantikan deretan kolom angka:

* `theme.split_bar()` — batang bertumpuk + legenda angkanya. Proporsi jauh lebih
  cepat dibaca sebagai panjang daripada sebagai lima kolom angka. Sisa yang tidak
  masuk empat kategori (hampir semuanya HOLD) ikut digambar sebagai "lainnya" —
  celah abu yang tidak dijelaskan selalu dibaca sebagai bug.
* `theme.chip_row()` — sebaran last progress sebagai chip. Sebagai tabel, sepuluh
  baris dipakai untuk memberi tahu bahwa kebanyakan bernilai nol; sebagai chip,
  yang nol tidak ditulis sama sekali.
* `theme.stat_inline()` — angka ringkas sebaris untuk ruang sempit di dalam
  expander.

## Recruitment Room — monitoring, bukan embed

Embed form Apps Script sudah dihapus. Alasannya bukan teknis: form itu memang
untuk **mengisi**, dan mengisi lebih enak di tab sendiri yang lebar. Yang tidak
bisa dilakukan form adalah **melihat** — dan itu yang selama ini memaksa tim
kembali ke spreadsheet mentah. Halaman ini mengambil alih bagian melihatnya.

**Atas: tabel monitoring.** Enam filter (Site · PIC · Departemen · Status · Level
· Jenis level), semuanya default "semua". Kolom inti yang selalu tampil: kandidat,
posisi, site, departemen, level, PIC, tahap terakhir, status, SLA.

Sheet aslinya punya **delapan kolom per tahap** — start, done, LT, budget, LT
contribution, variance, reason, result — dan itu yang membuatnya berhenti
terbaca. Di portal, tahap ditambahkan sendiri lewat "Tambah kolom tahap", dan
tiap tahap hanya membawa **LT** dan **SLA**. Variance dan LT contribution tidak
dibawa karena keduanya turunan dari LT dan budget yang sudah tampil.

**PIC** diambil dari PIC Screening CV, dasar yang sama dengan tabel Performance,
jadi angka di dua halaman itu bisa dibandingkan langsung.

**Bawah: daftar link** form dan spreadsheet per site, masing-masing bisa disalin
atau dibuka di tab baru.

## PIC: nama lengkap, bukan lagi inisial

Kolom `*_by` dulu berisi inisial tiga huruf; form Apps Script sekarang menulis
**nama lengkap**, dan ejaannya tidak seragam — di database ada "SHAUMY FADHILA"
dan "SHAUMY FADILAH", "ALFINA DIVA RAMADHANTY" dan "ALFINA DIVA". Karena peta
lama hanya berisi inisial, empat recruiter tercatat nol padahal datanya ada.

`config.resolve_recruiter()` menggantikan peta itu, dengan urutan:

1. cocokkan ke nama roster apa adanya (abaikan besar-kecil dan tanda baca);
2. cocokkan ke peta inisial;
3. cocokkan lewat **nama depan**, tapi hanya kalau nama depan itu cuma dimiliki
   satu orang di roster. "Shaumy" unik, jadi "SHAUMY FADILAH" aman dipulangkan.
   "Muhammad" dimiliki dua orang, jadi nama depan saja sengaja tidak cukup —
   lebih baik masuk "Recruiter lain" daripada dikreditkan ke orang yang salah.

Diverifikasi terhadap hitungan langsung dari sheet: kedelapan baris tabel
Performance cocok persis, selisih nol.
