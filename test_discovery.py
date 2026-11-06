"""Unit test suite for Company Discovery PoC using synthetic HTML fixtures."""
import os
import unittest
from datetime import datetime, timezone

from crawler import (
    DiscoveredLink,
    normalize_domain,
    normalize_url,
    validate_url,
)
from database import (
    get_engine,
    get_session,
    init_db,
    save_or_update_company,
    save_or_update_jobs,
)
from extractor import (
    extract_company_data,
    extract_job_postings,
    find_career_url,
    find_impressum_url,
)
from models import Base, Company, CompanyPerson, JobPosting
from scrapling import Selector

# Synthetic HTML Fixtures
FIXTURE_HOMEPAGE_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
    <title>Acme Innovations GmbH - Home</title>
</head>
<body>
    <header>
        <nav>
            <a href="/">Startseite</a>
            <a href="/produkte">Produkte</a>
            <a href="/ueber-uns">Über uns</a>
            <a href="/karriere">Karriere & Jobs</a>
        </nav>
    </header>
    <main>
        <h1>Willkommen bei Acme Innovations</h1>
        <p>Wir bauen die Zukunft digitaler Lösungen.</p>
    </main>
    <footer>
        <a href="/impressum">Impressum</a>
        <a href="/datenschutz">Datenschutzerklärung</a>
        <a href="https://linkedin.com/company/acme" target="_blank">LinkedIn</a>
    </footer>
</body>
</html>
"""

FIXTURE_IMPRESSUM_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
    <title>Impressum - Acme Innovations GmbH</title>
</head>
<body>
    <h1>Impressum</h1>
    
    <h2>Angaben gemäß § 5 TMG</h2>
    <p>
        Acme Innovations GmbH<br>
        Musterstraße 42<br>
        10115 Berlin<br>
        Deutschland
    </p>

    <h2>Vertreten durch</h2>
    <p>
        Geschäftsführer: Dr. Erika Musterfrau, Max Mustermann
    </p>

    <h2>Kontakt</h2>
    <p>
        Telefon: +49 30 12345678<br>
        Telefax: +49 30 87654321<br>
        E-Mail: kontakt@acme-innovations.de
    </p>

    <h2>Registereintrag</h2>
    <p>
        Eintragung im Handelsregister.<br>
        Registergericht: Amtsgericht Berlin<br>
        Registernummer: HRB 98765
    </p>

    <h2>Umsatzsteuer-ID</h2>
    <p>
        Umsatzsteuer-Identifikationsnummer gemäß § 27 a Umsatzsteuergesetz:<br>
        DE123456789
    </p>
</body>
</html>
"""

FIXTURE_CAREER_HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
    <title>Karriere bei Acme Innovations</title>
</head>
<body>
    <h1>Werden Sie Teil unseres Teams</h1>
    <nav>
        <a href="/">Home</a>
        <a href="/impressum">Impressum</a>
    </nav>
    
    <div class="job-listings">
        <div class="job-card">
            <a href="/jobs/senior-python-developer" class="job-link">
                <h3>Senior Python Developer (m/w/d)</h3>
            </a>
            <span class="location">Berlin</span>
            <span class="type">Vollzeit</span>
        </div>

        <div class="job-card">
            <a href="/jobs/devops-cloud-engineer" class="job-link">
                <h3>DevOps Cloud Engineer (f/m/d)</h3>
            </a>
            <span class="location">Remote</span>
            <span class="type">Full-time</span>
        </div>

        <div class="job-card">
            <a href="/karriere/werkstudent-it-support" class="job-link">
                Werkstudent IT Support (all genders)
            </a>
            <span class="type">Werkstudent</span>
        </div>

        <!-- Non-job navigation links that must be rejected -->
        <a href="/karriere">Alle Stellenangebote</a>
        <a href="#apply">Jetzt bewerben</a>
    </div>
</body>
</html>
"""


class TestCompanyDiscovery(unittest.TestCase):
    """Test suite covering PoC core functionality and edge cases."""

    def setUp(self):
        """Prepare in-memory SQLite database for test isolation."""
        self.engine = get_engine(":memory:")
        Base.metadata.create_all(self.engine)
        self.session = get_session(self.engine)

    def tearDown(self):
        """Clean up database session."""
        self.session.close()

    # 1. Impressum link discovery
    def test_01_impressum_link_discovery(self):
        sel = Selector(FIXTURE_HOMEPAGE_HTML)
        discovered = []
        for a in sel.css("a"):
            href = a.attrib.get("href", "")
            norm = normalize_url(href, base_url="https://acme-innovations.de")
            if norm:
                discovered.append(DiscoveredLink(url=norm, text=a.get_all_text(), is_internal=True))

        impressum_url = find_impressum_url(discovered, base_url="https://acme-innovations.de")
        self.assertIsNotNone(impressum_url)
        self.assertEqual(impressum_url, "https://acme-innovations.de/impressum")

    # 2. Company name extraction
    def test_02_company_name_extraction(self):
        sel = Selector(FIXTURE_IMPRESSUM_HTML)
        data, _ = extract_company_data(
            selector=sel,
            source_url="https://acme-innovations.de/impressum",
            website_url="https://acme-innovations.de",
        )
        self.assertEqual(data["name"], "Acme Innovations GmbH")
        self.assertEqual(data["legal_form"], "GmbH")

    # 3. Email extraction
    def test_03_email_extraction(self):
        sel = Selector(FIXTURE_IMPRESSUM_HTML)
        data, _ = extract_company_data(
            selector=sel,
            source_url="https://acme-innovations.de/impressum",
            website_url="https://acme-innovations.de",
        )
        self.assertEqual(data["email"], "kontakt@acme-innovations.de")

    # 4. Phone extraction
    def test_04_phone_extraction(self):
        sel = Selector(FIXTURE_IMPRESSUM_HTML)
        data, _ = extract_company_data(
            selector=sel,
            source_url="https://acme-innovations.de/impressum",
            website_url="https://acme-innovations.de",
        )
        self.assertIsNotNone(data["phone"])
        self.assertIn("+49 30 12345678", data["phone"])

    # 5. Career page discovery
    def test_05_career_page_discovery(self):
        sel = Selector(FIXTURE_HOMEPAGE_HTML)
        discovered = []
        for a in sel.css("a"):
            href = a.attrib.get("href", "")
            norm = normalize_url(href, base_url="https://acme-innovations.de")
            if norm:
                discovered.append(DiscoveredLink(url=norm, text=a.get_all_text(), is_internal=True))

        career_url, is_ext = find_career_url(discovered, base_domain="acme-innovations.de")
        self.assertIsNotNone(career_url)
        self.assertFalse(is_ext)
        self.assertEqual(career_url, "https://acme-innovations.de/karriere")

    # 6. Basic job title extraction
    def test_06_basic_job_title_extraction(self):
        sel = Selector(FIXTURE_CAREER_HTML)
        jobs = extract_job_postings(
            selector=sel,
            career_url="https://acme-innovations.de/karriere",
            base_domain="acme-innovations.de",
        )
        self.assertGreaterEqual(len(jobs), 2)
        titles = [j["title"] for j in jobs]
        self.assertTrue(any("Senior Python Developer" in t for t in titles))
        self.assertTrue(any("DevOps Cloud Engineer" in t for t in titles))

        # Check that generic navigation was not extracted as a job
        for t in titles:
            self.assertNotEqual(t.lower(), "home")
            self.assertNotEqual(t.lower(), "impressum")

    # 7. Duplicate company prevention
    def test_07_duplicate_company_prevention(self):
        company_data = {
            "domain": "acme-innovations.de",
            "website_url": "https://acme-innovations.de",
            "name": "Acme Innovations GmbH",
            "legal_form": "GmbH",
            "city": "Berlin",
        }
        # First scan
        c1, created1 = save_or_update_company(self.session, company_data)
        self.assertTrue(created1)

        # Second scan with updated data
        updated_data = {
            "domain": "acme-innovations.de",
            "website_url": "https://acme-innovations.de",
            "name": "Acme Innovations GmbH",
            "legal_form": "GmbH",
            "city": "München",
        }
        c2, created2 = save_or_update_company(self.session, updated_data)
        self.assertFalse(created2)
        self.assertEqual(c1.id, c2.id)

        # Verify only one company exists in the database
        count = self.session.query(Company).filter_by(domain="acme-innovations.de").count()
        self.assertEqual(count, 1)
        self.assertEqual(c2.city, "München")

    # 8. Duplicate job prevention
    def test_08_duplicate_job_prevention(self):
        company_data = {
            "domain": "acme-innovations.de",
            "website_url": "https://acme-innovations.de",
            "name": "Acme Innovations GmbH",
        }
        company, _ = save_or_update_company(self.session, company_data)

        jobs_batch1 = [
            {"title": "Senior Python Developer", "url": "https://acme-innovations.de/jobs/python-dev", "location": "Berlin"},
            {"title": "DevOps Engineer", "url": "https://acme-innovations.de/jobs/devops", "location": "Remote"},
        ]
        created1, updated1 = save_or_update_jobs(self.session, company.id, jobs_batch1)
        self.assertEqual(created1, 2)
        self.assertEqual(updated1, 0)

        # Record first seen timestamp
        initial_job = self.session.query(JobPosting).filter_by(url="https://acme-innovations.de/jobs/python-dev").one()
        first_seen = initial_job.first_seen_at

        # Second scan with the same jobs (one updated)
        jobs_batch2 = [
            {"title": "Senior Python Developer (Lead)", "url": "https://acme-innovations.de/jobs/python-dev", "location": "Berlin (Hybrid)"},
            {"title": "DevOps Engineer", "url": "https://acme-innovations.de/jobs/devops", "location": "Remote"},
        ]
        created2, updated2 = save_or_update_jobs(self.session, company.id, jobs_batch2)
        self.assertEqual(created2, 0)
        self.assertEqual(updated2, 2)

        # Check total job count in DB remains 2
        total_jobs = self.session.query(JobPosting).filter_by(company_id=company.id).count()
        self.assertEqual(total_jobs, 2)

        # Check that original first_seen_at is preserved
        refreshed_job = self.session.query(JobPosting).filter_by(url="https://acme-innovations.de/jobs/python-dev").one()
        self.assertEqual(refreshed_job.first_seen_at, first_seen)
        self.assertEqual(refreshed_job.title, "Senior Python Developer (Lead)")

    # 9. Invalid URL rejection
    def test_09_invalid_url_rejection(self):
        valid, reason = validate_url("http://localhost:8000", check_dns=False)
        self.assertFalse(valid)
        self.assertIn("Localhost", reason)

        valid, reason = validate_url("http://127.0.0.1:3000", check_dns=False)
        self.assertFalse(valid)
        self.assertIn("Private", reason)

        valid, reason = validate_url("https://192.168.0.1/dashboard", check_dns=False)
        self.assertFalse(valid)
        self.assertIn("Private", reason)

        valid, reason = validate_url("ftp://ftp.example.com", check_dns=False)
        self.assertFalse(valid)
        self.assertIn("Unsupported scheme", reason)

        valid, reason = validate_url("javascript:alert(1)", check_dns=False)
        self.assertFalse(valid)
        self.assertIn("Unsupported scheme", reason)

        valid, _ = validate_url("https://www.example.de", check_dns=False)
        self.assertTrue(valid)

    # 10. Task 3.1: Multiple valid company representatives
    def test_10_multiple_valid_representatives(self):
        html = """
        <html><body>
        <h1>Impressum</h1>
        <p>Vertreten durch die Geschäftsführer:<br>
        Dr. Erika Musterfrau, Prof. Dr. Hans-Peter Schmidt, Dipl.-Ing. Max von Berg
        </p>
        </body></html>
        """
        sel = Selector(html)
        _, persons = extract_company_data(sel, "https://example.de/impressum", "https://example.de")
        self.assertEqual(len(persons), 3)

        p1 = persons[0]
        self.assertEqual(p1["first_name"], "Erika")
        self.assertEqual(p1["last_name"], "Musterfrau")

        p2 = persons[1]
        self.assertEqual(p2["first_name"], "Hans-Peter")
        self.assertEqual(p2["last_name"], "Schmidt")

        p3 = persons[2]
        self.assertEqual(p3["first_name"], "Max von")
        self.assertEqual(p3["last_name"], "Berg")

    # 11. Task 3.2: Representative section containing "Sitz: Karlsruhe"
    def test_11_representative_section_with_sitz_karlsruhe(self):
        html = """
        <html><body>
        <h1>Impressum</h1>
        <p>Geschäftsführer: Stephan Müller, Tobias Joch</p>
        <p>Sitz: Karlsruhe</p>
        <p>Amtsgericht Mannheim HRB 502126</p>
        </body></html>
        """
        sel = Selector(html)
        _, persons = extract_company_data(sel, "https://inovex.de/impressum", "https://inovex.de")
        self.assertEqual(len(persons), 2)
        names = [f"{p['first_name']} {p['last_name']}" for p in persons]
        self.assertIn("Stephan Müller", names)
        self.assertIn("Tobias Joch", names)

        # Confirm Sitz: Karlsruhe was not extracted as a representative
        for p in persons:
            self.assertNotIn("Sitz", p["first_name"])
            self.assertNotIn("Karlsruhe", p["last_name"])

    # 12. Task 3.3: Representative section containing register and contact information
    def test_12_representative_section_with_register_and_contact(self):
        html = """
        <html><body>
        <h1>Impressum</h1>
        <p>
            Geschäftsführung: Clara Schumann, Registergericht: Amtsgericht Berlin HRB 12345,
            Telefon: +49 30 112233, E-Mail: info@company.de, Fax: +49 30 654321
        </p>
        </body></html>
        """
        sel = Selector(html)
        _, persons = extract_company_data(sel, "https://company.de/impressum", "https://company.de")
        self.assertEqual(len(persons), 1)
        self.assertEqual(persons[0]["first_name"], "Clara")
        self.assertEqual(persons[0]["last_name"], "Schumann")

    # 13. Task 3.4: Career page containing both real jobs and category/navigation links
    def test_13_career_page_category_and_navigation_filtering(self):
        html = """
        <html><body>
        <nav>
            <a href="/karriere/stellenangebote">Offene Jobs</a>
            <a href="/karriere/das-inovex-package-fuer-mitarbeiterinnen">inovex package</a>
            <a href="/karriere/teams-und-projekte">Teams & Projekte</a>
            <a href="/karriere/benefits">Unsere Benefits</a>
            <a href="/karriere/standorte">Standorte</a>
        </nav>
        <div class="job-list">
            <a href="/karriere/stellenangebote/senior-python-dev">
                <h3>Senior Python Backend Engineer (m/w/d)</h3>
            </a>
            <a href="/karriere/stellenangebote/cloud-architect">
                <h3>Cloud Architect (f/m/d)</h3>
            </a>
        </div>
        </body></html>
        """
        sel = Selector(html)
        jobs = extract_job_postings(sel, "https://inovex.de/karriere/stellenangebote", "inovex.de")
        self.assertEqual(len(jobs), 2)
        urls = [j["url"] for j in jobs]
        self.assertIn("https://inovex.de/karriere/stellenangebote/senior-python-dev", urls)
        self.assertIn("https://inovex.de/karriere/stellenangebote/cloud-architect", urls)

        # Confirm non-job navigation links are excluded
        self.assertNotIn("https://inovex.de/karriere/stellenangebote", urls)
        self.assertNotIn("https://inovex.de/karriere/das-inovex-package-fuer-mitarbeiterinnen", urls)
        self.assertNotIn("https://inovex.de/karriere/teams-und-projekte", urls)

    # 14. Task 3.5: Job card with valid title and location
    def test_14_job_card_with_title_and_location(self):
        html = """
        <html><body>
        <div class="job-card">
            <a href="/jobs/frontend-architect" class="job-link">
                <h3>Senior Frontend Architect (f/m/d)</h3>
            </a>
            <span class="location">München</span>
            <span class="type">Vollzeit</span>
        </div>
        </body></html>
        """
        sel = Selector(html)
        jobs = extract_job_postings(sel, "https://company.de/karriere", "company.de")
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["title"], "Senior Frontend Architect (f/m/d)")
        self.assertEqual(job["location"], "München")
        self.assertEqual(job["employment_type"], "Full-time")
        self.assertEqual(job["url"], "https://company.de/jobs/frontend-architect")

    # 15. Task 3.6: Duplicate job links on career page
    def test_15_duplicate_job_links_deduplication(self):
        html = """
        <html><body>
        <div class="job-card">
            <a href="/jobs/python-dev" class="title-link"><h3>Python Developer (m/w/d)</h3></a>
            <p>Spannende Aufgaben im Backend.</p>
            <a href="/jobs/python-dev" class="apply-button">Jetzt bewerben</a>
        </div>
        </body></html>
        """
        sel = Selector(html)
        jobs = extract_job_postings(sel, "https://company.de/karriere", "company.de")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["url"], "https://company.de/jobs/python-dev")
        self.assertEqual(jobs[0]["title"], "Python Developer (m/w/d)")

    # 16. Representative synchronization deletes obsolete persons
    def test_16_representative_synchronization_deletes_obsolete(self):
        from database import delete_company
        company_data = {
            "domain": "sync-test.de",
            "website_url": "https://sync-test.de",
            "name": "Sync Test GmbH",
        }
        # First scan with an invalid/obsolete representative
        reps_batch1 = [
            {"first_name": "Stephan", "last_name": "Müller", "role": "Managing Director"},
            {"first_name": "Sitz:", "last_name": "Karlsruhe", "role": "Managing Director"},
        ]
        c1, _ = save_or_update_company(self.session, company_data, reps_batch1)
        self.assertEqual(len(c1.persons), 2)

        # Second scan with cleaned/updated representatives
        reps_batch2 = [
            {"first_name": "Stephan", "last_name": "Müller", "role": "Managing Director"},
            {"first_name": "Tobias", "last_name": "Joch", "role": "Managing Director"},
        ]
        c2, _ = save_or_update_company(self.session, company_data, reps_batch2)

        # Verify obsolete "Sitz: Karlsruhe" was removed and replaced
        person_names = [f"{p.first_name or ''} {p.last_name}".strip() for p in c2.persons]
        self.assertEqual(len(person_names), 2)
        self.assertIn("Stephan Müller", person_names)
        self.assertIn("Tobias Joch", person_names)
        self.assertNotIn("Sitz: Karlsruhe", person_names)

    # 17. Job synchronization prunes obsolete jobs when website updates
    def test_17_job_synchronization_prunes_removed_jobs(self):
        company_data = {
            "domain": "job-sync-test.de",
            "website_url": "https://job-sync-test.de",
            "name": "Job Sync Test GmbH",
        }
        company, _ = save_or_update_company(self.session, company_data)

        # Batch 1: 3 jobs
        batch1 = [
            {"title": "Job A", "url": "https://job-sync-test.de/jobs/a"},
            {"title": "Job B", "url": "https://job-sync-test.de/jobs/b"},
            {"title": "Job C", "url": "https://job-sync-test.de/jobs/c"},
        ]
        save_or_update_jobs(self.session, company.id, batch1)
        self.assertEqual(self.session.query(JobPosting).filter_by(company_id=company.id).count(), 3)

        # Batch 2: Job B and C removed, Job D added
        batch2 = [
            {"title": "Job A (Updated)", "url": "https://job-sync-test.de/jobs/a"},
            {"title": "Job D (New)", "url": "https://job-sync-test.de/jobs/d"},
        ]
        res = save_or_update_jobs(self.session, company.id, batch2, prune_missing=True)
        self.assertEqual(res.created, 1)
        self.assertEqual(res.updated, 1)
        self.assertEqual(res.deleted, 2)

        remaining_urls = [j.url for j in self.session.query(JobPosting).filter_by(company_id=company.id).all()]
        self.assertEqual(len(remaining_urls), 2)
        self.assertIn("https://job-sync-test.de/jobs/a", remaining_urls)
        self.assertIn("https://job-sync-test.de/jobs/d", remaining_urls)
        self.assertNotIn("https://job-sync-test.de/jobs/b", remaining_urls)
        self.assertNotIn("https://job-sync-test.de/jobs/c", remaining_urls)

    # 18. Cascade delete company
    def test_18_cascade_delete_company(self):
        from database import delete_company
        company_data = {
            "domain": "delete-me.de",
            "website_url": "https://delete-me.de",
            "name": "Delete Me GmbH",
        }
        reps = [{"first_name": "Max", "last_name": "Mustermann", "role": "CEO"}]
        c, _ = save_or_update_company(self.session, company_data, reps)
        save_or_update_jobs(self.session, c.id, [{"title": "Test Job", "url": "https://delete-me.de/job/1"}])

        c_id = c.id
        self.assertEqual(self.session.query(CompanyPerson).filter_by(company_id=c_id).count(), 1)
        self.assertEqual(self.session.query(JobPosting).filter_by(company_id=c_id).count(), 1)

        success = delete_company(self.session, c_id)
        self.assertTrue(success)
        self.assertIsNone(self.session.query(Company).filter_by(id=c_id).first())
        self.assertEqual(self.session.query(CompanyPerson).filter_by(company_id=c_id).count(), 0)
        self.assertEqual(self.session.query(JobPosting).filter_by(company_id=c_id).count(), 0)


if __name__ == "__main__":
    unittest.main()
