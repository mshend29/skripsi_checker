# SkripsiCheck

Aplikasi web untuk membantu dosen mengoreksi skripsi mahasiswa, mengelola catatan revisi, versioning dokumen, dan temuan AI.

## Stack awal

- HTML + Bootstrap 5
- JavaScript ES Modules
- Supabase Auth
- Supabase PostgreSQL + RLS
- Supabase project: `lwfljoazmfckxuwcsdvk`

## Fitur yang sudah disiapkan

- Register dosen
- Login / logout
- Profil dosen otomatis dari `public.users`
- Dashboard live count
- RLS per dosen
- Struktur database untuk mahasiswa, skripsi, dokumen, versi, paragraf, komentar, AI findings, dan bank komentar

## Menjalankan lokal

Jalankan HTTP server dari root repository:

```bash
python -m http.server 8080
```

Kemudian buka:

```text
http://localhost:8080
```

Jangan membuka `index.html` melalui `file://` karena aplikasi memakai JavaScript ES Modules.

## Keamanan

Frontend hanya menggunakan Supabase **publishable key**. Jangan pernah menaruh `service_role` / secret key di source code frontend.

## Roadmap

1. Authentication + profile dosen
2. Dashboard
3. Modul mahasiswa
4. Modul skripsi
5. Upload DOCX + document versioning
6. Review paragraph-level + komentar
7. AI findings
8. Revision comparison
