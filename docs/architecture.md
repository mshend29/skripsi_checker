# Arsitektur SkripsiCheck

## Alur utama

```text
Supabase Auth
      |
      v
public.users
      |
      v
students
      |
      v
theses
      |
      +-- thesis_sections
      |
      v
documents
      |
      v
document_versions
      |
      v
document_paragraphs
      |
      +-- comments
      +-- ai_findings

users
  |
  +-- comment_templates
```

## Prinsip keamanan

- Client menggunakan publishable key.
- Tidak ada service-role key di browser.
- Seluruh tabel utama memakai Row Level Security.
- Kepemilikan data mahasiswa dimulai dari `students.created_by = auth.uid()`.
- Tabel turunan mengikuti kepemilikan skripsi mahasiswa tersebut.

## Modul aplikasi

### 1. Authentication
Register, login, logout, dan profile dosen.

### 2. Dashboard
Statistik mahasiswa aktif, skripsi aktif, komentar terbuka, dan AI findings.

### 3. Mahasiswa
CRUD data mahasiswa dengan soft delete.

### 4. Skripsi
Judul, status, tahap, dan struktur BAB/sub-BAB.

### 5. Dokumen
Upload DOCX/PDF dan versioning.

### 6. Review
Paragraph-level comment, severity, status revisi, dan bank komentar.

### 7. AI
AI findings dipisahkan dari komentar dosen. Temuan AI baru menjadi komentar setelah diterima dosen.
