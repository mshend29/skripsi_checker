from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import Student


DUMMY_STUDENTS = [
    {
        "nim": "22110001",
        "name": "Aulia Rahma Putri",
        "email": "aulia.rahma@example.test",
        "study_program": "Manajemen",
        "cohort": "2022",
    },
    {
        "nim": "22110002",
        "name": "Bagas Pratama",
        "email": "bagas.pratama@example.test",
        "study_program": "Manajemen",
        "cohort": "2022",
    },
    {
        "nim": "22110003",
        "name": "Citra Lestari",
        "email": "citra.lestari@example.test",
        "study_program": "Manajemen",
        "cohort": "2022",
    },
    {
        "nim": "23110001",
        "name": "Dimas Arya Saputra",
        "email": "dimas.arya@example.test",
        "study_program": "Manajemen",
        "cohort": "2023",
    },
    {
        "nim": "23110002",
        "name": "Fajar Ramadhan",
        "email": "fajar.ramadhan@example.test",
        "study_program": "Manajemen",
        "cohort": "2023",
    },
    {
        "nim": "23110003",
        "name": "Nadia Safitri",
        "email": "nadia.safitri@example.test",
        "study_program": "Manajemen",
        "cohort": "2023",
    },
]


def seed_students() -> tuple[int, int]:
    init_db()

    inserted = 0
    skipped = 0

    with SessionLocal() as session:
        for payload in DUMMY_STUDENTS:
            exists = session.scalar(
                select(Student.id).where(Student.nim == payload["nim"])
            )
            if exists:
                skipped += 1
                continue

            session.add(Student(**payload))
            inserted += 1

        session.commit()

    return inserted, skipped


if __name__ == "__main__":
    inserted, skipped = seed_students()
    print(f"Dummy mahasiswa selesai: {inserted} ditambahkan, {skipped} dilewati.")
