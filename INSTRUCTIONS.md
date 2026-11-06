# Instructions & Execution Guide: Company & Job Discovery

This document provides complete instructions for setting up, running, testing, and verifying the Company & Job Discovery application.

All examples below use the target website:
**[Spezialisierte Personalberatung Maschinenbau | InnoTech Experts](https://innotech-experts.de/)** (`https://innotech-experts.de/`).

---

## 1. Prerequisites & Environment Setup

### 1.1 Verify Python Version
Ensure Python 3.12+ (tested with Python 3.14) is available:
```powershell
python --version
```

### 1.2 Open the Project Directory
Navigate to the project root directory in PowerShell or Terminal:
```powershell
cd "c:\Users\a.awad\Desktop\Job Discovery"
```

### 1.3 Install Dependencies
Install all pinned dependencies from `requirements.txt`:
```powershell
pip install -r requirements.txt
```

---

## 2. Interactive Menu & Command-Line Usage

### 2.1 Launching the Interactive Console Menu
Run the application without arguments (or with `--menu`) to open the interactive menu:
```powershell
python main.py
```

Menu Interface:
```text
=======================================================
              COMPANY & JOB DISCOVERY
=======================================================
  [1] New Scan (Enter Website URL)
  [2] Search Database (By URL, Domain, or Name)
  [3] Browse Database (List All Companies & Jobs)
  [4] Exit
=======================================================
Select an option [1-4]: 
```

- **Option [1] New Scan:** Prompts you to enter a company website URL (e.g. `https://innotech-experts.de/`) and runs the full discovery scan.
- **Option [2] Search Database:** Prompts for a URL or domain, finds the stored company record, and displays complete details and job postings.
- **Option [3] Browse Database:** Displays a clean summary table of all stored companies and their job counts, with interactive sub-options to:
  - `[1] View Job Postings for a Company`: Paginated view of all job advertisements (title, location, type, dates, and direct URL) for any selected company ID.
  - `[2] View Full Company Profile`: Complete Impressum, contact details, address, legal representatives, and jobs.
  - `[3] View All Jobs in Database`: View all job postings across all scanned companies.
  - `[4] Delete Company & Data`: Permanently delete a company and cascade-delete its jobs and representatives.
- **Option [4] Exit:** Closes the application.

### 2.2 Direct Command-Line Execution
You can still run scans directly by passing the target URL as an argument:
```powershell
python main.py https://innotech-experts.de/
```

### 2.3 Display Help
To see all supported CLI options and flags:
```powershell
python main.py --help
```

---

## 3. Running a Scan Against `https://innotech-experts.de/`

### 3.1 Initial Scan
Run the application by passing the target URL:
```powershell
python main.py https://innotech-experts.de/
```

Expected Workflow & Output:
```text
========================================
       COMPANY DISCOVERY
========================================

Website: https://innotech-experts.de/

[1/4] Fetching website...
SUCCESS

[2/4] Finding Impressum...
FOUND: https://innotech-experts.de/en/imprint

[3/4] Extracting company information...

Company: InnoTech Experts
Address: Universitätsstraße 30, 47051 Duisburg, Germany
Email: a.oengel@innotech-experts.de
Phone: +49 (0)203 ...
VAT ID: DE320788090

[4/4] Finding job advertisements...
Career page: FOUND (https://innotech-experts.de/stellenangebote)
Jobs discovered: 138
  [1] Technischer Außendienst Gebäudetechnik (m/w/d) | Full-time
  [2] Außendienstmitarbeiter Gebäudetechnik (m/w/d) | München | Full-time
  [3] Produktmanager Mess- und Regeltechnik (m/w/d) | Full-time
  [4] Leitung Vertrieb Food & Beverage (m/w/d) | Full-time
  [5] Area Sales Manager Industry (m/w/d) | Full-time
  ... and 133 more.

========================================
DATABASE
========================================
Company saved successfully.
138 new job postings saved, 0 existing job postings updated.

Scan completed.
========================================
```

---

### 3.2 Deduplication Verification (Second Scan)
Run the exact same command a second time:
```powershell
python main.py https://innotech-experts.de/
```

Expected Output:
```text
========================================
DATABASE
========================================
Company updated successfully.
0 new job postings saved, 138 existing job postings updated.

Scan completed.
========================================
```
- No duplicate company record is created.
- No duplicate job postings are created.
- The company's `updated_at` timestamp is updated while preserving `created_at`.
- Each job posting's `last_seen_at` timestamp is updated while preserving `first_seen_at`.

---

## 4. Custom Database & Page Limits

### 4.1 Custom Database File
Save extracted data to a dedicated database file:
```powershell
python main.py https://innotech-experts.de/ --db innotech_results.db
```

### 4.2 Adjust Visited Page Limit
Adjust the maximum number of visited pages (default is 20):
```powershell
python main.py https://innotech-experts.de/ --max-pages 30
```

---

## 5. Security & SSRF Protection Checks

The application validates every input URL before initiating network connections. You can test the security guardrails:

### 5.1 Localhost Rejection
```powershell
python main.py http://localhost:8080
```
Output:
```text
ERROR: Invalid or unsafe URL: Localhost destination 'localhost' is rejected for security.
```

### 5.2 Private IP Rejection
```powershell
python main.py http://192.168.1.1
```
Output:
```text
ERROR: Invalid or unsafe URL: Private or reserved IP address '192.168.1.1' is rejected.
```

### 5.3 Unsupported Scheme Rejection
```powershell
python main.py ftp://innotech-experts.de
```
Output:
```text
ERROR: Invalid or unsafe URL: Unsupported scheme 'ftp'. Only HTTP and HTTPS are permitted.
```

---

## 6. Running the Automated Test Suite

Execute the 15 unit tests covering Impressum discovery, metadata extraction, administrative noise filtering, navigation exclusion, job-card parsing, deduplication, and URL security:

```powershell
python -m unittest test_discovery.py -v
```

Expected Result:
```text
test_01_impressum_link_discovery (test_discovery.TestCompanyDiscovery.test_01_impressum_link_discovery) ... ok
test_02_company_name_extraction (test_discovery.TestCompanyDiscovery.test_02_company_name_extraction) ... ok
test_03_email_extraction (test_discovery.TestCompanyDiscovery.test_03_email_extraction) ... ok
test_04_phone_extraction (test_discovery.TestCompanyDiscovery.test_04_phone_extraction) ... ok
test_05_career_page_discovery (test_discovery.TestCompanyDiscovery.test_05_career_page_discovery) ... ok
test_06_basic_job_title_extraction (test_discovery.TestCompanyDiscovery.test_06_basic_job_title_extraction) ... ok
test_07_duplicate_company_prevention (test_discovery.TestCompanyDiscovery.test_07_duplicate_company_prevention) ... ok
test_08_duplicate_job_prevention (test_discovery.TestCompanyDiscovery.test_08_duplicate_job_prevention) ... ok
test_09_invalid_url_rejection (test_discovery.TestCompanyDiscovery.test_09_invalid_url_rejection) ... ok
test_10_multiple_valid_representatives (test_discovery.TestCompanyDiscovery.test_10_multiple_valid_representatives) ... ok
test_11_representative_section_with_sitz_karlsruhe (test_discovery.TestCompanyDiscovery.test_11_representative_section_with_sitz_karlsruhe) ... ok
test_12_representative_section_with_register_and_contact (test_discovery.TestCompanyDiscovery.test_12_representative_section_with_register_and_contact) ... ok
test_13_career_page_category_and_navigation_filtering (test_discovery.TestCompanyDiscovery.test_13_career_page_category_and_navigation_filtering) ... ok
test_14_job_card_with_title_and_location (test_discovery.TestCompanyDiscovery.test_14_job_card_with_title_and_location) ... ok
test_15_duplicate_job_links_deduplication (test_discovery.TestCompanyDiscovery.test_15_duplicate_job_links_deduplication) ... ok

----------------------------------------------------------------------
Ran 15 tests in 0.198s

OK
```

---

## 7. Inspecting the SQLite Database

All extracted data is stored in `company_discovery.db`.

### 7.1 View Stored Company Details
```powershell
python -c "import sqlite3; conn = sqlite3.connect('company_discovery.db'); c = conn.cursor(); print(c.execute('SELECT id, domain, name, city, email, vat_id, created_at, updated_at FROM companies WHERE domain = \"innotech-experts.de\"').fetchall())"
```

### 7.2 View Stored Job Postings Sample
```powershell
python -c "import sqlite3; conn = sqlite3.connect('company_discovery.db'); c = conn.cursor(); print('Total Jobs for innotech-experts.de:', c.execute('SELECT count(*) FROM job_postings WHERE company_id IN (SELECT id FROM companies WHERE domain = \"innotech-experts.de\")').fetchone()[0]); print('\nSample Jobs:'); [print(row) for row in c.execute('SELECT title, location, employment_type, first_seen_at, last_seen_at FROM job_postings WHERE company_id IN (SELECT id FROM companies WHERE domain = \"innotech-experts.de\") LIMIT 5').fetchall()]"
```

### 7.3 Graphical SQLite Viewers
You can also open `company_discovery.db` with GUI tools such as **DB Browser for SQLite** or **VS Code SQLite Viewer Extension**.

---

## 8. Running with Docker & Docker Compose

The application includes a production-grade multi-stage `Dockerfile` and `docker-compose.yml` for isolated containerized execution.

### 8.1 Build the Docker Image
Build the container image using Docker Compose:
```powershell
docker compose build
```

### 8.2 Launch the Interactive Menu in Docker
Run the interactive console menu inside Docker with full terminal interactivity:
```powershell
docker compose run --rm app
```

### 8.3 Direct Scan with Docker
Execute a direct discovery scan on any company website:
```powershell
docker compose run --rm app https://innotech-experts.de/
```

### 8.4 Run Automated Tests in Docker
Execute the full test suite in an isolated container environment:
```powershell
docker compose run --rm tests
```

### 8.5 Data Persistence
All containerized scans persist their database to `./data/company_discovery.db` on your host machine via Docker volume mounting.


