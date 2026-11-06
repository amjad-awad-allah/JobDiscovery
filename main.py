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
from database import (
    delete_company,
    get_all_companies,
    get_all_jobs,
    get_company_by_id,
    get_company_by_query,
    get_database_stats,
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
        career_page_inspected = False
        if is_external:
            print(f"Career page: FOUND (External Portal: {career_url})")
            print("Notice: External portal extraction is out of scope for this PoC.")
        else:
            print(f"Career page: FOUND ({career_url})")
            career_resp = crawler.fetch(career_url)
            if career_resp and career_resp.status < 400:
                career_page_inspected = True
                discovered_jobs = extract_job_postings(
                    selector=career_resp,
                    career_url=career_url,
                    base_domain=crawler.base_domain,
                )
    else:
        career_page_inspected = False
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
        action_str = "saved successfully." if is_created else "updated & synchronized successfully."
        print(f"Company {action_str}")

        jobs_res = save_or_update_jobs(
            session=session,
            company_id=company_obj.id,
            jobs_data=discovered_jobs,
            prune_missing=career_page_inspected,
        )
        created_jobs = jobs_res[0]
        updated_jobs = jobs_res[1]
        deleted_jobs = getattr(jobs_res, "deleted", 0)

        parts = []
        if created_jobs > 0:
            parts.append(f"{created_jobs} new job postings saved")
        if updated_jobs > 0:
            parts.append(f"{updated_jobs} existing job postings updated")
        if deleted_jobs > 0:
            parts.append(f"{deleted_jobs} obsolete job postings removed")

        if parts:
            print(", ".join(parts) + ".")
        elif discovered_jobs:
            print("All job postings are up to date.")
        else:
            print("No job postings to save.")

        print("\nScan completed.")
        print("========================================")
        return 0
    except Exception as e:
        session.rollback()
        print(f"DATABASE ERROR: Failed to persist results: {e}")
        return 1
    finally:
        session.close()


def display_company_card(company, show_jobs: bool = True) -> None:
    """Format and display detailed information for a company and its jobs."""
    print("\n" + "=" * 70)
    print(f" COMPANY DETAILS: {company.name or company.domain}")
    print("=" * 70)
    print(f"ID:                  {company.id}")
    print(f"Company Name:        {company.name or 'Not specified'}")
    if company.legal_form:
        print(f"Legal Form:          {company.legal_form}")
    print(f"Domain:              {company.domain}")
    print(f"Website URL:         {company.website_url}")
    print(f"Impressum URL:       {company.impressum_url or 'Not found'}")

    # Address
    address_parts = []
    if company.street:
        addr = company.street
        if company.house_number:
            addr += f" {company.house_number}"
        address_parts.append(addr)
    if company.postal_code or company.city:
        plz_city = f"{company.postal_code or ''} {company.city or ''}".strip()
        address_parts.append(plz_city)
    if company.country:
        address_parts.append(company.country)
    address_str = ", ".join(address_parts) if address_parts else "Not found"
    print(f"Address:             {address_str}")

    print(f"Email:               {company.email or 'Not found'}")
    print(f"Phone:               {company.phone or 'Not found'}")
    if company.fax:
        print(f"Fax:                 {company.fax}")
    print(f"VAT ID:              {company.vat_id or 'Not found'}")
    if company.register_number:
        court = f" ({company.register_court})" if company.register_court else ""
        print(f"Commercial Register: {company.register_number}{court}")

    # Representatives
    if company.persons:
        print("\nRepresentatives:")
        for p in company.persons:
            print(f"  • {p.first_name or ''} {p.last_name} ({p.role})")
    else:
        print("Representatives:     None recorded")

    created_str = company.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if company.created_at else "Unknown"
    updated_str = company.updated_at.strftime("%Y-%m-%d %H:%M:%S UTC") if company.updated_at else "Unknown"
    print(f"\nFirst Discovered:    {created_str}")
    print(f"Last Updated:        {updated_str}")

    # Jobs
    if show_jobs:
        jobs = company.jobs or []
        print("\n" + "-" * 70)
        print(f" JOB POSTINGS (Total: {len(jobs)})")
        print("-" * 70)
        if not jobs:
            print("  No job postings recorded for this company.")
        else:
            limit = 10
            for idx, job in enumerate(jobs[:limit], 1):
                loc = f" | {job.location}" if job.location else ""
                emp = f" | {job.employment_type}" if job.employment_type else ""
                first_s = job.first_seen_at.strftime("%Y-%m-%d") if job.first_seen_at else ""
                print(f"  [{idx}] {job.title}{loc}{emp}")
                print(f"      URL: {job.url}")
                if first_s:
                    print(f"      First seen: {first_s}")
            if len(jobs) > limit:
                remaining = len(jobs) - limit
                print(f"\n  ... and {remaining} more job postings.")
                try:
                    show_more = input(f"  View all remaining {remaining} jobs? [y/N]: ").strip().lower()
                    if show_more == "y":
                        for idx, job in enumerate(jobs[limit:], limit + 1):
                            loc = f" | {job.location}" if job.location else ""
                            emp = f" | {job.employment_type}" if job.employment_type else ""
                            print(f"  [{idx}] {job.title}{loc}{emp}")
                            print(f"      URL: {job.url}")
                except (KeyboardInterrupt, EOFError):
                    pass
    print("=" * 70)


def handle_search_company(db_path: str = "company_discovery.db") -> None:
    """Prompt user for URL, domain, or company name and search database."""
    init_db(db_path)
    session = get_session(db_path)
    try:
        print("\n" + "=" * 60)
        print(" [2] SEARCH IN DATABASE")
        print("=" * 60)
        query = input("Enter company website URL, domain, or name: ").strip()
        if not query:
            print("Search cancelled.")
            return

        company = get_company_by_query(session, query)
        if company:
            display_company_card(company, show_jobs=True)
        else:
            print(f"\nNo company found in database matching: '{query}'")
            print("Tip: Use Option [1] to scan this website and add it to the database.")
    finally:
        session.close()


def display_company_jobs(company, batch_size: int = 15) -> None:
    """Display all job postings for a specific company with clean pagination."""
    jobs = company.jobs or []
    print("\n" + "=" * 80)
    print(f" JOB POSTINGS FOR: {company.name or company.domain}")
    print(f" Domain: {company.domain} | Total Jobs: {len(jobs)}")
    print("=" * 80)

    if not jobs:
        print("  No job advertisements found for this company.")
        print("=" * 80)
        return

    total = len(jobs)
    current_idx = 0

    while current_idx < total:
        end_idx = min(current_idx + batch_size, total)
        for i in range(current_idx, end_idx):
            job = jobs[i]
            loc_str = f" | Location: {job.location}" if job.location else ""
            emp_str = f" | Type: {job.employment_type}" if job.employment_type else ""
            first_s = f" | First seen: {job.first_seen_at.strftime('%Y-%m-%d')}" if job.first_seen_at else ""
            last_s = f" | Last seen: {job.last_seen_at.strftime('%Y-%m-%d')}" if job.last_seen_at else ""

            print(f"\n  [{i + 1}/{total}] {job.title}")
            details = f"{loc_str.lstrip(' |')}{emp_str}{first_s}{last_s}"
            if details:
                print(f"      {details}")
            print(f"      URL: {job.url}")

        current_idx = end_idx
        if current_idx < total:
            remaining = total - current_idx
            try:
                prompt = f"\n  --- Showing {current_idx} of {total} jobs. Press Enter for next {min(batch_size, remaining)} (or 'a' for all, 'q' to stop): "
                nav = input(prompt).strip().lower()
                if nav == "q":
                    break
                elif nav == "a":
                    batch_size = total
            except (KeyboardInterrupt, EOFError):
                break
        else:
            print("\n  --- End of job listings ---")

    print("=" * 80)


def display_all_jobs_in_db(session, batch_size: int = 15) -> None:
    """Display all job postings across all companies in database."""
    all_jobs = get_all_jobs(session)
    print("\n" + "=" * 80)
    print(f" ALL JOB POSTINGS IN DATABASE (Total: {len(all_jobs)} jobs)")
    print("=" * 80)

    if not all_jobs:
        print("  No job advertisements stored in the database.")
        print("=" * 80)
        return

    total = len(all_jobs)
    current_idx = 0

    while current_idx < total:
        end_idx = min(current_idx + batch_size, total)
        for i in range(current_idx, end_idx):
            job = all_jobs[i]
            comp_label = job.company.name if job.company and job.company.name else (job.company.domain if job.company else f"Company #{job.company_id}")
            loc_str = f" | {job.location}" if job.location else ""
            emp_str = f" | {job.employment_type}" if job.employment_type else ""

            print(f"\n  [{i + 1}/{total}] {job.title}  [{comp_label}]")
            details = f"{loc_str.lstrip(' |')}{emp_str}"
            if details:
                print(f"      {details}")
            print(f"      URL: {job.url}")

        current_idx = end_idx
        if current_idx < total:
            remaining = total - current_idx
            try:
                prompt = f"\n  --- Showing {current_idx} of {total} jobs. Press Enter for next {min(batch_size, remaining)} (or 'a' for all, 'q' to stop): "
                nav = input(prompt).strip().lower()
                if nav == "q":
                    break
                elif nav == "a":
                    batch_size = total
            except (KeyboardInterrupt, EOFError):
                break
        else:
            print("\n  --- End of job listings ---")

    print("=" * 80)


def handle_browse_database(db_path: str = "company_discovery.db") -> None:
    """List all stored companies and provide clear sub-options to view jobs or company profiles."""
    init_db(db_path)
    session = get_session(db_path)
    try:
        companies = get_all_companies(session)
        stats = get_database_stats(session)

        print("\n" + "=" * 80)
        print(f" [3] BROWSE DATABASE ({stats['companies']} Companies | {stats['jobs']} Jobs)")
        print("=" * 80)

        if not companies:
            print("The database is currently empty.")
            print("Use Option [1] in the main menu to scan your first company website!")
            print("=" * 80)
            return

        # Table header
        print(f"{'ID':<4} | {'Domain':<26} | {'Company Name':<28} | {'City':<12} | {'Jobs':<5}")
        print("-" * 80)

        company_ids = set()
        for c in companies:
            company_ids.add(c.id)
            c_id = str(c.id)
            c_domain = (c.domain[:24] + "..") if len(c.domain) > 26 else c.domain
            c_name = (c.name or "N/A")
            c_name = (c_name[:26] + "..") if len(c_name) > 28 else c_name
            c_city = (c.city or "-")[:12]
            c_jobs = str(len(c.jobs or []))
            print(f"{c_id:<4} | {c_domain:<26} | {c_name:<28} | {c_city:<12} | {c_jobs:<5}")

        print("=" * 80)

        print("\nWhat would you like to view?")
        print("  [1] View Job Postings for a Company (Select by ID)")
        print("  [2] View Full Company Profile & Impressum Info (Select by ID)")
        print("  [3] View All Jobs in the Database")
        print("  [4] Delete a Company & All its Data (Select by ID)")
        print("  [Enter] Return to Main Menu")
        print("-" * 80)

        try:
            choice = input("Select an option [1-4] or press Enter to return: ").strip()
        except (KeyboardInterrupt, EOFError):
            return

        if not choice:
            return

        # If user picked Option 1 (View jobs for a company)
        if choice == "1":
            try:
                sub_id = input(f"Enter Company ID to view its jobs [{', '.join(str(i) for i in sorted(company_ids))}]: ").strip()
                if not sub_id:
                    return
                if sub_id.isdigit():
                    company = get_company_by_id(session, int(sub_id))
                    if company:
                        display_company_jobs(company)
                    else:
                        print(f"Company ID {sub_id} not found.")
                else:
                    company = get_company_by_query(session, sub_id)
                    if company:
                        display_company_jobs(company)
                    else:
                        print(f"No company found matching '{sub_id}'.")
            except (KeyboardInterrupt, EOFError):
                return

        # If user picked Option 2 (View full company profile)
        elif choice == "2":
            try:
                sub_id = input(f"Enter Company ID to view full details [{', '.join(str(i) for i in sorted(company_ids))}]: ").strip()
                if not sub_id:
                    return
                if sub_id.isdigit():
                    company = get_company_by_id(session, int(sub_id))
                    if company:
                        display_company_card(company, show_jobs=True)
                    else:
                        print(f"Company ID {sub_id} not found.")
                else:
                    company = get_company_by_query(session, sub_id)
                    if company:
                        display_company_card(company, show_jobs=True)
                    else:
                        print(f"No company found matching '{sub_id}'.")
            except (KeyboardInterrupt, EOFError):
                return

        # If user picked Option 3 (View all jobs across all companies)
        elif choice == "3":
            display_all_jobs_in_db(session)

        # If user picked Option 4 (Delete company)
        elif choice == "4":
            try:
                sub_id = input(f"Enter Company ID to DELETE [{', '.join(str(i) for i in sorted(company_ids))}]: ").strip()
                if not sub_id:
                    return
                company = get_company_by_id(session, int(sub_id)) if sub_id.isdigit() else get_company_by_query(session, sub_id)
                if not company:
                    print(f"Company '{sub_id}' not found.")
                    return
                confirm = input(f"Are you sure you want to delete '{company.name or company.domain}' and all its jobs? (y/N): ").strip().lower()
                if confirm in ("y", "yes"):
                    delete_company(session, company.id)
                    print(f"Company '{company.domain}' and associated data successfully deleted.")
                else:
                    print("Deletion cancelled.")
            except (KeyboardInterrupt, EOFError):
                return

        # Or if user typed a company query or domain directly
        else:
            company = get_company_by_query(session, choice)
            if company:
                display_company_jobs(company)
            else:
                print("Invalid selection.")
    finally:
        session.close()


def interactive_menu(db_path: str = "company_discovery.db", max_pages: int = 20) -> None:
    """Run interactive console menu loop."""
    init_db(db_path)

    while True:
        print("\n" + "=" * 55)
        print("              COMPANY & JOB DISCOVERY")
        print("=======================================================")
        print("  [1] New Scan (Enter Website URL)")
        print("  [2] Search Database (By URL, Domain, or Name)")
        print("  [3] Browse Database (List All Companies & Jobs)")
        print("  [4] Exit")
        print("=======================================================")

        try:
            choice = input("Select an option [1-4]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting. Goodbye!")
            break

        if choice == "1":
            print("\n" + "=" * 55)
            print(" [1] NEW WEBSITE SCAN")
            print("=" * 55)
            try:
                target_url = input("Enter company website URL (e.g. https://innotech-experts.de/): ").strip()
            except (KeyboardInterrupt, EOFError):
                break

            if not target_url or target_url.lower() in ("back", "0", "exit", "cancel"):
                print("Scan cancelled.")
                continue

            # Check if company already exists in database
            target_domain = normalize_domain(target_url)
            session = get_session(db_path)
            existing = get_company_by_query(session, target_domain) if target_domain else None
            session.close()

            if existing:
                print(f"\nNotice: Company '{existing.name or existing.domain}' already exists in database.")
                print("  [1] Rescan & Synchronize (Update details, remove obsolete jobs/persons, keep history) [Default]")
                print("  [2] Fresh Scan (Delete old company record and scan completely from scratch)")
                print("  [3] Cancel")
                try:
                    rescan_mode = input("Select an option [1-3, Enter=1]: ").strip()
                except (KeyboardInterrupt, EOFError):
                    continue

                if rescan_mode == "2":
                    session = get_session(db_path)
                    delete_company(session, existing.id)
                    session.close()
                    print(f"Cleared previous records for '{existing.domain}'. Starting fresh scan...")
                elif rescan_mode in ("3", "c", "cancel"):
                    print("Scan cancelled.")
                    continue

            run_discovery(
                target_url=target_url,
                db_path=db_path,
                max_pages=max_pages,
                check_dns=True,
            )
            try:
                input("\nPress Enter to return to menu...")
            except (KeyboardInterrupt, EOFError):
                pass

        elif choice == "2":
            handle_search_company(db_path=db_path)
            try:
                input("\nPress Enter to return to menu...")
            except (KeyboardInterrupt, EOFError):
                pass

        elif choice == "3":
            handle_browse_database(db_path=db_path)
            try:
                input("\nPress Enter to return to menu...")
            except (KeyboardInterrupt, EOFError):
                pass

        elif choice in ("4", "q", "exit", "quit"):
            print("\nThank you for using Company & Job Discovery. Goodbye!")
            break

        else:
            print("\nInvalid selection. Please choose 1, 2, 3, or 4.")


def main() -> None:
    """Parse command line arguments and execute discovery."""
    parser = argparse.ArgumentParser(
        prog="company-discovery",
        description="Company & Job Discovery CLI: Automatically extract company and career details from websites.",
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="Target company website URL (e.g. https://innotech-experts.de/). If omitted, interactive menu opens.",
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
    parser.add_argument(
        "--menu",
        action="store_true",
        help="Launch the interactive console menu",
    )

    args = parser.parse_args()

    # If URL is supplied directly via CLI, run scan directly
    if args.url and not args.menu:
        exit_code = run_discovery(
            target_url=args.url,
            db_path=args.db,
            max_pages=args.max_pages,
            check_dns=True,
        )
        sys.exit(exit_code)
    else:
        # Otherwise, launch the interactive menu
        interactive_menu(db_path=args.db, max_pages=args.max_pages)


if __name__ == "__main__":
    main()
