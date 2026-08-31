# Skripsi Checker

Aplikasi desktop offline untuk membantu dosen mengelola mahasiswa, proposal, revisi, koreksi, dan finalisasi skripsi.

## Stack

- Python 3.12+
- PySide6
- SQLite
- SQLAlchemy
- python-docx
- PyMuPDF

Semua data disimpan lokal. Aplikasi tidak membutuhkan Supabase atau server web.

## Menjalankan aplikasi

### Windows

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Database SQLite akan dibuat otomatis di `data/skripsi_checker.db`.

### Isi 6 data dummy mahasiswa

Setelah dependency terpasang, jalankan:

```powershell
python seed_students.py
```

Script akan menambahkan 6 mahasiswa dummy. Jika NIM dummy sudah ada, record tersebut akan dilewati sehingga aman dijalankan ulang.

## Fitur versi awal

- Dashboard statistik lokal
- Data mahasiswa: tambah, cari, edit, hapus, dan validasi
- Data skripsi: cari/filter, tambah, edit, detail, hapus aman, dan status progres
- Import dokumen Proposal/Revisi/Final dalam format DOCX/PDF
- Riwayat versi dokumen dan buka file lokal langsung dari aplikasi
- Penyimpanan dokumen terpisah berdasarkan jenis dan versi
- Deteksi awal judul dari isi dokumen
- Workspace koreksi 3 kolom: struktur, paragraf dokumen, dan catatan review
- Komentar melekat ke paragraf/versi dokumen tertentu
- Komentar memiliki kategori, tingkat urgensi, status, dan kutipan teks
- Export DOCX dengan komentar Word native untuk dikembalikan ke mahasiswa
- Komentar dosen: tambah, edit, selesai/buka kembali, hapus, dan filter status
- Halaman Finalisasi sebagai tahap pengembangan berikutnya

## Struktur

```text
.
├── main.py
├── requirements.txt
├── app/
│   ├── database.py
│   ├── models.py
│   ├── services/
│   │   └── document_service.py
│   └── ui/
│       ├── main_window.py
│       └── pages/
│           ├── dashboard.py
│           ├── students.py
│           └── theses.py
├── data/
└── storage/
    ├── proposals/
    ├── revisions/
    └── finals/
```

## Prinsip penyimpanan

File proposal/revisi/final tidak disimpan di database. Database hanya menyimpan metadata dan path file. File fisik disimpan di folder `storage/`.

Riwayat Git lama tetap tersedia sehingga versi web sebelumnya masih dapat dilihat dari commit terdahulu.


## Export koreksi ke Word

Untuk dokumen sumber DOCX, menu Koreksi menyediakan tombol `Export Word Berkomentar`.
Aplikasi membuat salinan DOCX dan menanamkan komentar aktif sebagai komentar Word native
pada paragraf yang dikoreksi. Komentar berstatus Selesai tidak ikut diekspor.

Fitur ini membutuhkan `python-docx >= 1.2`. Setelah melakukan `git pull`, jalankan:

```powershell
pip install -r requirements.txt
```

Untuk dokumen PDF, komentar tetap tersimpan di database aplikasi, tetapi tidak diekspor
sebagai komentar Word.


## Struktur dan tampilan review

Panel Struktur menggunakan tree view ringkas. BAB yang memiliki subbab tampil dalam keadaan
tertutup dan dapat dibuka dengan indikator `+`. Halaman awal/judul hanya ditampilkan sebagai
satu item `Halaman Awal / Halaman Judul`. Jika dokumen memiliki Daftar Isi, struktur BAB/subbab
diambil dari Daftar Isi tersebut, sementara halaman Daftar Isi sendiri hanya tampil sebagai satu
item `Daftar Isi`.

Panel dokumen menggunakan tampilan menyerupai lembar Microsoft Word: workspace abu-abu,
lembar putih, teks hitam Times New Roman, dan paragraf tetap menjadi unit review. Border paragraf
serta tombol `+ Tambahkan komentar` hanya tampil ketika paragraf di-hover atau sedang dipilih.


## Preview dokumen seperti Word

Untuk DOCX, halaman Koreksi menggunakan renderer HTML interaktif langsung dari struktur DOCX
tanpa konversi ke PDF. Hasilnya ditampilkan di `QWebEngineView` dengan halaman putih bergaya
Word, jarak antarhalaman, paragraf yang dapat di-hover, dan teks yang dapat diblok menggunakan
selection native browser.

Renderer mempertahankan format penting seperti alignment, indentasi, spacing, bold/italic,
ukuran dan nama font, tabel, gambar inline, page break eksplisit, serta header/footer dasar.
Pagination A4 dilakukan secara lokal di HTML. File cache HTML disimpan di
`storage/html_previews/` dan tidak masuk Git.

Mode komentar memiliki dua perilaku: jika tidak ada teks yang diblok maka seluruh paragraf
menjadi kutipan; jika ada teks yang diblok di paragraf tersebut maka hanya selection itu yang
menjadi kutipan. Zoom menggunakan zoom native WebEngine sehingga tidak perlu merender ulang
gambar halaman.


## Interaksi koreksi dokumen

Hover bekerja langsung pada elemen paragraf HTML, bukan overlay koordinat PDF. Selection teks
menggunakan selection native browser sehingga dosen dapat memblok kata atau kalimat di paragraf.
Jika tidak ada selection, seluruh paragraf menjadi kutipan komentar; jika ada selection, hanya
teks yang dipilih yang menjadi kutipan.

Dialog Tambah/Edit Komentar menggunakan input putih dengan teks hitam dan font yang lebih besar.
Layout awal modul Koreksi menggunakan rasio Struktur/Dokumen/Komentar 20/70/10 dan tetap dapat
diubah dengan menarik splitter. Panel Dokumen memiliki zoom 50%–200% dengan tombol minus, slider,
dan plus.
