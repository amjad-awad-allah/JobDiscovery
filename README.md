# Company & Job Discovery – Proof of Concept (PoC)

A lightweight, security-conscious Python console application for automated company and career discovery. Given a company website URL, the application crawls the site using **Scrapling**, detects the **Impressum** and **Career** pages, extracts structured metadata, and persists the results into a local **SQLite** database via **SQLAlchemy 2.x**.

---

## 1. Key Features

- **Strict URL & SSRF Validation:** Accepts only valid `http://` and `https://` URLs. Actively rejects `localhost`, private IP ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.0/8`), link-local, multicast, and loopback destinations.
- **Scrapling-Powered Web Crawling:** Fetches web pages safely without running client-side JavaScript, respects request timeouts (12s), confines crawling strictly to the target company domain, and enforces a safety visit limit (max ~20 pages).
- **Rule-Based Impressum Discovery:** Identifies and ranks Impressum links matching terms such as `Impressum`, `Anbieterkennzeichnung`, `Rechtliche Hinweise`, `Legal Notice`, and `Imprint`.
- **Company Metadata Extraction:** Extracts company name, legal form (GmbH, AG, UG, etc.), address (street, house number, PLZ, city, country), email, phone, fax, VAT ID (`DE...`), commercial register number (`HRB/HRA`), register court, and company representatives/managing directors.
- **Career Page & Job Extraction:** Discovers internal career pages (`/karriere`, `/jobs`, `Stellenangebote`), identifies job listing links and titles (e.g. `(m/w/d)`, `Developer`, `Engineer`), and detects external applicant tracking systems (e.g. Personio, Greenhouse, Lever).
- **SQLite Persistence & Deduplication:** Stores records using SQLAlchemy 2.0 ORM. Repeated scans update existing company records (based on domain) and job postings (based on company ID + normalized URL), preserving original `first_seen_at` timestamps while updating `last_seen_at`.
- **Clean Console Output:** Presents a clear 4-step progress report and database transaction summary.

---

## 2. Technology Stack & Pinned Dependencies

- **Python:** 3.12+ (tested on Python 3.14.4)
- **Scrapling:** `0.5.1` (official library for fetching and HTML parsing)
- **SQLAlchemy:** `2.1.8` (ORM & database operations)
- **SQLite:** Local file `company_discovery.db`

All dependencies are pinned in `requirements.txt`:
```text
scrapling==0.5.1
SQLAlchemy==2.1.8
curl_cffi==0.17.0
lxml==6.1.3
cssselect==1.6.0
orjson==3.13.0
tld==0.13.2
w3lib==2.5.0
browserforge==1.2.4
patchright==1.64.4
playwright==1.64.1
Protego==0.7.0
msgspec==0.22.0
anyio==4.16.0
apify-fingerprint-datapoints==0.15.0
cffi==2.1.1
pycparser==3.12
pyee==14.0.0
greenlet==3.5.6
typing_extensions==4.16.0
certifi==2026.10.23
click==8.5.0
```

---

## 3. Project Structure

```text
Job Discovery/
├── main.py              # CLI entrypoint, argument parsing, workflow orchestration
├── crawler.py           # Scrapling fetching, URL normalization & security validation
├── extractor.py         # Impressum, metadata, career portal & job extraction
├── models.py            # SQLAlchemy 2.x declarative models (companies, persons, jobs)
├── database.py          # SQLite engine, sessions, deduplication & persistence
├── test_discovery.py    # Synthetic offline test suite covering all 9 test cases
├── requirements.txt     # Pinned dependencies
├── README.md            # Comprehensive documentation
├── .gitignore           # Ignores database files, caches, and venv
└── company_discovery.db # SQLite database file (created upon first run)
```

---

## 4. Installation & Setup

1. **Clone or navigate to the repository:**
   ```bash
   cd "c:\Users\a.awad\Desktop\Job Discovery"
   ```

2. **(Optional) Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install pinned dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

---

## 5. Usage Examples

### 5.1 Help Command
```bash
python main.py --help
```
Output:
```text
usage: company-discovery [-h] [--db DB] [--max-pages MAX_PAGES] [url]

Company & Job Discovery CLI: Automatically extract company and career details
from websites.

positional arguments:
  url                   Target company website URL (e.g.
                        https://www.example.de)

options:
  -h, --help            show this help message and exit
  --db DB               Path to the SQLite database file (default:
                        company_discovery.db)
  --max-pages MAX_PAGES
                        Maximum number of pages to visit (default: 20)
```

### 5.2 Scan a Company Website
```bash
python main.py https://www.example.de
```

Example Console Output:
```text
========================================
       COMPANY DISCOVERY
========================================

Website: https://www.example.de

[1/4] Fetching website...
SUCCESS

[2/4] Finding Impressum...
FOUND: https://www.example.de/impressum

[3/4] Extracting company information...

Company: Example Solutions GmbH
Legal Form: GmbH
Address: Musterstraße 12, 10115 Berlin, Germany
Email: kontakt@example.de
Phone: +49 30 12345678
VAT ID: DE123456789
Commercial Register: HRB 12345 (Amtsgericht Berlin)
Representatives: Dr. Max Mustermann (Managing Director)

[4/4] Finding job advertisements...
Career page: FOUND (https://www.example.de/karriere)
Jobs discovered: 3
  [1] Senior Python Engineer | Berlin | Full-time
  [2] Cloud DevOps Specialist | Remote | Full-time
  [3] Werkstudent IT | Berlin | Working Student

========================================
DATABASE
========================================
Company saved successfully.
3 new job postings saved, 0 existing job postings updated.

Scan completed.
========================================
```

---

## 6. Database Schema (`company_discovery.db`)

### `companies` Table
| Column | Type | Constraints / Description |
|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `name` | VARCHAR(255) | Company trading or legal name |
| `legal_form` | VARCHAR(50) | GmbH, AG, UG, etc. |
| `domain` | VARCHAR(255) | UNIQUE, INDEXED (Normalized domain) |
| `website_url` | VARCHAR(1024) | Target site URL |
| `impressum_url` | VARCHAR(1024) | Discovered Impressum URL |
| `street` | VARCHAR(255) | Street name |
| `house_number` | VARCHAR(50) | House number |
| `postal_code` | VARCHAR(20) | Postal code (PLZ) |
| `city` | VARCHAR(100) | City name |
| `country` | VARCHAR(100) | Country |
| `email` | VARCHAR(255) | Primary contact / Impressum email |
| `phone` | VARCHAR(100) | Contact telephone |
| `fax` | VARCHAR(100) | Contact fax number |
| `vat_id` | VARCHAR(50) | VAT identification number |
| `register_number` | VARCHAR(50) | Commercial register number (HRB/HRA) |
| `register_court` | VARCHAR(255) | Competent registration court |
| `created_at` | DATETIME | Timestamp of first scan (UTC) |
| `updated_at` | DATETIME | Timestamp of latest scan (UTC) |

### `company_persons` Table
| Column | Type | Constraints / Description |
|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `company_id` | INTEGER | FOREIGN KEY -> `companies.id` ON DELETE CASCADE |
| `first_name` | VARCHAR(100) | Representative first name |
| `last_name` | VARCHAR(100) | Representative last name |
| `role` | VARCHAR(100) | E.g. "Managing Director" |

### `job_postings` Table
| Column | Type | Constraints / Description |
|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `company_id` | INTEGER | FOREIGN KEY -> `companies.id` ON DELETE CASCADE |
| `title` | VARCHAR(500) | Job title |
| `url` | VARCHAR(1024) | Normalized job advertisement URL |
| `location` | VARCHAR(255) | Location (e.g. Berlin, Remote) |
| `employment_type` | VARCHAR(100) | Full-time, Part-time, Internship, etc. |
| `description` | TEXT | Snippet / brief description |
| `first_seen_at` | DATETIME | Timestamp when job was first discovered (UTC) |
| `last_seen_at` | DATETIME | Timestamp when job was last confirmed active (UTC) |

**Unique Constraint:** `(company_id, url)` prevents duplicate job listings.

---

## 7. Automated Test Suite

A standalone test suite `test_discovery.py` uses synthetic in-memory HTML fixtures and an in-memory SQLite database, guaranteeing reliable execution without external network dependence.

Run tests:
```bash
python -m unittest test_discovery.py -v
```

### Test Coverage (All 9 Required Cases Passed):
1. **`test_01_impressum_link_discovery`**: Tests keyword identification and link ranking for Impressum URLs.
2. **`test_02_company_name_extraction`**: Tests extraction of legal form and company name from Impressum text.
3. **`test_03_email_extraction`**: Tests regex-based email extraction while filtering noise.
4. **`test_04_phone_extraction`**: Tests telephone extraction and normalization.
5. **`test_05_career_page_discovery`**: Tests career portal link identification.
6. **`test_06_basic_job_title_extraction`**: Tests job card title detection and exclusion of nav links.
7. **`test_07_duplicate_company_prevention`**: Verifies that re-scanning a domain updates the record instead of creating duplicates.
8. **`test_08_duplicate_job_prevention`**: Verifies that re-scanning updates `last_seen_at` while preserving `first_seen_at`.
9. **`test_09_invalid_url_rejection`**: Verifies rejection of localhost, private IPs (127.0.0.1, 192.168.0.1), and unsupported schemes (ftp, javascript).

---

## 8. Security Considerations & Protections

- **SSRF Protection:** URL hostnames are inspected. Raw IP literals and resolved DNS addresses are validated against private, loopback, multicast, and link-local ranges using Python's `ipaddress` module.
- **Protocol Restrictions:** Only `http` and `https` schemes are allowed.
- **Scope Restriction:** Crawling is strictly confined to the company's base domain (and direct subdomains). External links are cataloged but not traversed.
- **Resource Limits:** Requests timeout after 12 seconds. Visited pages are capped at 20 per scan.
- **Safe Static Fetching:** Downloaded JavaScript is never executed. Scrapling's static engine with `curl_cffi` is utilized.

---

## 9. Known Limitations (PoC Scope)

- **JavaScript-Only Single Page Applications (SPAs):** Websites rendering job lists exclusively via client-side React/Vue/Angular without server-side HTML won't reveal job titles in static HTML mode (Playwright/headless browsing was excluded per PoC specification).
- **External ATS Extraction:** External job portals (Personio, Lever, Greenhouse) are detected and flagged, but individual portal scrapers are out of scope for this initial PoC.
- **Unstructured / Obfuscated Impressum:** Images containing contact info (anti-scraping measure) cannot be parsed without OCR (excluded in PoC).

---

## 10. Future Development Roadmap

1. **PostgreSQL Migration:** Switch storage to the existing Docker PostgreSQL instance for enterprise scalability.
2. **ATS Portal Connectors:** Add specialized handlers for Personio, Greenhouse, Lever, and Workable APIs.
3. **Automated Change Detection & Alerts:** Notify users via email/webhook when new job listings appear or existing ones close.
4. **Structured JSON Export:** Provide `--export json` and `--export csv` flags for batch downstream analytics.

