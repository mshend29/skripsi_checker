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

## Fitur versi awal

- Dashboard statistik lokal
- Data mahasiswa: tambah, cari, edit, hapus, dan validasi
- Data skripsi
- Import proposal DOCX/PDF
- Penyimpanan dokumen proposal berdasarkan versi
- Deteksi awal judul dari isi dokumen
- Fondasi database untuk dokumen dan komentar/revisi
- Halaman Koreksi dan Finalisasi sebagai tahap pengembangan berikutnya

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
