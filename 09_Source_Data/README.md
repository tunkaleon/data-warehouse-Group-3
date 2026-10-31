# Source data (simulated exports of the three library systems)

No real data was provided, so `generate_source_data.py` simulates the three systems for 2023-2025 (fixed random seed: the files are identical on every computer).

| File | System | Rows | Deliberate data problems |
|---|---|---|---|
| `book_transactions.csv` | Book Lending (MySQL export) | 2,278 | 3 date formats in 2023 data, 15% missing ReturnDate, department spellings (CS / Computer Science / CompSci ...), 3% missing department, ISBN with/without dash, category capitalisation, exact + logical duplicates, impossible dates, return before checkout, unknown ISBNs |
| `digital_usage.xlsx` | Digital Resources (3 sheets) | 4,113 | a different date format on each sheet (MM/DD/YYYY, YYYY-DD-MM, "Jan 15, 2025"), E-book / e-Book, faculty codes vary, 25% missing Duration_Minutes, numbers stored as text, invalid counts, QUARTER TOTAL rows with "1,203", copied rows |
| `room_bookings.csv` | Study Room Booking (CSV) | 2,999 | R101 / R-101 / Room101, Morning / 8AM-10AM / AM, two date formats, 8% walk-ins without StudentID, "2 hrs" durations, exact + near duplicates, invalid values |
| `reference/student_master.csv` | Registrar | 800 | clean (used to fill missing departments and student level) |
| `reference/book_catalog.csv` | Catalogue | 72 | clean (titles and categories) |

Built-in patterns for the analysis: digital use grows ~30%/year and book loans fall ~10%/year; exam peaks in April and November; an e-resource outage in October 2024; graduates keep books longer and read more journals; group rooms with projectors are the most popular.
