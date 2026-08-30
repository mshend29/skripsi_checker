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
- Koreksi per versi dokumen dengan viewer teks DOCX/PDF
- Navigasi BAB/subbab hasil deteksi dokumen
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
