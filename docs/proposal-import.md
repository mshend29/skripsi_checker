# Proposal Import Workflow

## Alur

```text
Tambah Skripsi
  -> Import Proposal
  -> Pilih mahasiswa
  -> Upload DOCX/PDF
  -> Parser browser membaca dokumen
  -> Preview dan verifikasi dosen
  -> Upload file ke private Supabase Storage
  -> RPC transactional
       -> theses
       -> thesis_sections
       -> documents
       -> document_versions (Version 1)
       -> document_paragraphs
  -> Detail Skripsi
```

## Storage

Bucket: `thesis-documents`

- Private
- Maksimal 20 MB
- DOCX dan PDF
- Path diawali `auth.uid()`
- SELECT / INSERT / UPDATE / DELETE dibatasi ke folder milik user melalui RLS

## Parsing

### DOCX
Menggunakan Mammoth.js untuk mempertahankan heading dan paragraf sebanyak mungkin.

### PDF
Menggunakan PDF.js. Karena PDF tidak memiliki struktur style Word yang konsisten, heading dideteksi melalui pola teks.

## Data yang dicoba dideteksi

- Judul penelitian
- Nama mahasiswa
- NIM
- Jenis penelitian
- Abstrak
- Kata kunci
- BAB / daftar pustaka / lampiran
- Paragraf dan section aktif

Semua hasil parser ditampilkan sebagai draft untuk diverifikasi dosen sebelum disimpan.

## Prinsip

AI/parser merekomendasikan; dosen memutuskan.

Import proposal tidak langsung membuat data tanpa tahap review.
