"""Command-line entrypoint and workflow orchestration for Company Discovery PoC."""
import argparse
import logging
import sys
from typing import Any, Dict, List, Optional

from scrapling.core.utils import log

# Configure Scrapling logger to only emit errors to maintain clean console output
try:
    log.setLevel(logging.ERROR)
except Exception:
    pass

from crawler import Crawler, normalize_domain, validate_url
from database import get_session, init_db, save_or_update_company, save_or_update_jobs
from extractor import (
    extract_company_data,
    extract_job_postings,
    find_career_url,
    find_impressum_url,
)
from scrapling import Selector


def run_discovery(
    target_url: str,
    db_path: str = "company_discovery.db",
    max_pages: int = 20,
    check_dns: bool = True,
) -> int:
    """Execute the full company discovery workflow."""
    print("========================================")
    print("       COMPANY DISCOVERY")
    print("========================================")
    print(f"\nWebsite: {target_url}\n")

    # Step 0: URL Validation & Security Checks
    is_valid, reason = validate_url(target_url, check_dns=check_dns)
    if not is_valid:
        print(f"ERROR: Invalid or unsafe URL: {reason}")
        return 1

    # Initialize Database
    init_db(db_path)
    session = get_session(db_path)

    # Step 1: Website Crawling
    print("[1/4] Fetching website...")
    crawler = Crawler(
        start_url=target_url,
        max_pages=max_pages,
        timeout=12,
        check_dns=check_dns,
    )
    homepage_resp = crawler.crawl_homepage()
    if not homepage_resp:
        print("FAILED: Could not retrieve homepage. Please verify URL and network connection.")
        session.close()
        return 1
    print("SUCCESS")

    # Step 2: Impressum Discovery
    print("\n[2/4] Finding Impressum...")
    impressum_url = find_impressum_url(
        crawler.discovered_internal_links,
        base_url=target_url,
    )

    impressum_resp = None
    if impressum_url:
        print(f"FOUND: {impressum_url}")
        # Fetch the Impressum page
        impressum_resp = crawler.fetch(impressum_url)
    else:
        print("NOT FOUND: Continuing with homepage data...")

    # Step 3: Company Data Extraction
    print("\n[3/4] Extracting company information...")
    company_data: Dict[str, Any]
    persons_data: List[Dict[str, str]]

    if impressum_resp and impressum_resp.status < 400:
        company_data, persons_data = extract_company_data(
            selector=impressum_resp,
            source_url=impressum_url,
            website_url=target_url,
        )
    else:
        # Fallback to homepage selector
        company_data, persons_data = extract_company_data(
            selector=homepage_resp,
            source_url=homepage_resp.url or target_url,
            website_url=target_url,
        )

    # Format address string for display
    address_parts = []
    if company_data.get("street"):
        addr_line = company_data["street"]
        if company_data.get("house_number"):
            addr_line += f" {company_data['house_number']}"
        address_parts.append(addr_line)
    if company_data.get("postal_code") or company_data.get("city"):
        plz_city = f"{company_data.get('postal_code') or ''} {company_data.get('city') or ''}".strip()
        address_parts.append(plz_city)
    if company_data.get("country"):
        address_parts.append(company_data["country"])

    address_display = ", ".join(address_parts) if address_parts else "Not found"

    print(f"\nCompany: {company_data.get('name') or 'Not found'}")
    if company_data.get("legal_form"):
        print(f"Legal Form: {company_data['legal_form']}")
    print(f"Address: {address_display}")
    print(f"Email: {company_data.get('email') or 'Not found'}")
    print(f"Phone: {company_data.get('phone') or 'Not found'}")
    if company_data.get("fax"):
        print(f"Fax: {company_data['fax']}")
    print(f"VAT ID: {company_data.get('vat_id') or 'Not found'}")
    if company_data.get("register_number"):
        court_info = f" ({company_data.get('register_court')})" if company_data.get("register_court") else ""
        print(f"Commercial Register: {company_data['register_number']}{court_info}")

    if persons_data:
        person_names = [f"{p.get('first_name', '')} {p['last_name']} ({p['role']})".strip() for p in persons_data]
        print(f"Representatives: {', '.join(person_names)}")

    # Step 4: Career Page Discovery & Job Extraction
    print("\n[4/4] Finding job advertisements...")
    career_url, is_external = find_career_url(
        crawler.discovered_internal_links + crawler.discovered_external_links,
        base_domain=crawler.base_domain,
    )

    discovered_jobs: List[Dict[str, Any]] = []

    if career_url:
        if is_external:
            print(f"Career page: FOUND (External Portal: {career_url})")
            print("Notice: External portal extraction is out of scope for this PoC.")
        else:
            print(f"Career page: FOUND ({career_url})")
            career_resp = crawler.fetch(career_url)
            if career_resp and career_resp.status < 400:
                discovered_jobs = extract_job_postings(
                    selector=career_resp,
                    career_url=career_url,
                    base_domain=crawler.base_domain,
                )
    else:
        print("Career page: NOT FOUND")

    print(f"Jobs discovered: {len(discovered_jobs)}")
    for idx, job in enumerate(discovered_jobs[:5], 1):
        loc_info = f" | {job['location']}" if job.get("location") else ""
        emp_info = f" | {job['employment_type']}" if job.get("employment_type") else ""
        print(f"  [{idx}] {job['title']}{loc_info}{emp_info}")
    if len(discovered_jobs) > 5:
        print(f"  ... and {len(discovered_jobs) - 5} more.")

    # Step 5: Persistence to SQLite
    print("\n========================================")
    print("DATABASE")
    print("========================================")

    try:
        company_obj, is_created = save_or_update_company(
            session=session,
            company_data=company_data,
            persons_data=persons_data,
        )
        action_str = "saved successfully." if is_created else "updated successfully."
        print(f"Company {action_str}")

        created_jobs, updated_jobs = save_or_update_jobs(
            session=session,
            company_id=company_obj.id,
            jobs_data=discovered_jobs,
        )
        if discovered_jobs:
            print(f"{created_jobs} new job postings saved, {updated_jobs} existing job postings updated.")
        else:
            print("No new job postings to save.")

        print("\nScan completed.")
        print("========================================")
        return 0
    except Exception as e:
        session.rollback()
        print(f"DATABASE ERROR: Failed to persist results: {e}")
        return 1
    finally:
        session.close()


def main() -> None:
    """Parse command line arguments and execute discovery."""
    parser = argparse.ArgumentParser(
        prog="company-discovery",
        description="Company & Job Discovery CLI: Automatically extract company and career details from websites.",
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="Target company website URL (e.g. https://www.example.de)",
    )
    parser.add_argument(
        "--db",
        default="company_discovery.db",
        help="Path to the SQLite database file (default: company_discovery.db)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="Maximum number of pages to visit (default: 20)",
    )

    args = parser.parse_args()

    if not args.url:
        parser.print_help()
        sys.exit(1)

    exit_code = run_discovery(
        target_url=args.url,
        db_path=args.db,
        max_pages=args.max_pages,
        check_dns=True,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
