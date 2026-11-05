"""Extraction logic for Impressum, company metadata, career portals, and job listings."""
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from scrapling import Selector
from crawler import DiscoveredLink, normalize_domain, normalize_url

# Keywords for Impressum discovery
IMPRESSUM_TERMS = [
    "impressum",
    "anbieterkennzeichnung",
    "rechtliche hinweise",
    "rechtliche-hinweise",
    "legal notice",
    "legal-notice",
    "imprint",
    "rechtliches",
]

# Keywords for Career page discovery
CAREER_TERMS = [
    "karriere",
    "jobs",
    "stellenangebote",
    "stellenanzeigen",
    "offene stellen",
    "offene-stellen",
    "careers",
    "vacancies",
    "join our team",
    "join-our-team",
    "work with us",
    "work-with-us",
    "wir suchen",
]

# Known external applicant tracking systems (ATS) / job boards
EXTERNAL_ATS_PATTERNS = [
    "personio.de",
    "personio.com",
    "greenhouse.io",
    "lever.co",
    "workable.com",
    "softgarden.io",
    "softgarden.de",
    "join.com",
    "recruitee.com",
    "bamboohr.com",
    "smartrecruiters.com",
    "stepstone.de",
    "indeed.com",
    "linkedin.com/jobs",
]

# Legal forms recognized in Germany and international equivalents
LEGAL_FORMS = [
    "GmbH & Co. KG",
    "UG (haftungsbeschränkt)",
    "gGmbH",
    "GmbH",
    "AG",
    "e.K.",
    "e.V.",
    "KG",
    "OHG",
    "GbR",
    "SE",
    "Inc.",
    "Ltd.",
    "LLC",
]

# Common non-job button and nav phrases to exclude
NON_JOB_TITLES = {
    "home",
    "startseite",
    "über uns",
    "ueber uns",
    "about us",
    "kontakt",
    "contact",
    "impressum",
    "imprint",
    "datenschutz",
    "privacy policy",
    "privacy",
    "agb",
    "login",
    "anmelden",
    "mehr erfahren",
    "read more",
    "learn more",
    "jetzt bewerben",
    "apply now",
    "details",
    "zurück",
    "back",
    "alle jobs",
    "all jobs",
    "alle stellenangebote",
    "alle stellen",
    "unsere jobs",
    "unsere stellenangebote",
    "offene jobs",
    "offene stellen",
    "suche",
    "search",
    "filter",
    "standorte",
    "locations",
    "teams & projekte",
    "teams und projekte",
    "inovex package",
    "das inovex package",
    "unser package",
    "benefits",
    "vorteile",
    "unsere benefits",
    "ihre vorteile",
    "deine vorteile",
    "warum wir",
    "arbeiten bei uns",
    "initiativbewerbung",
    "bewerbungsprozess",
    "karriere",
    "jobs",
}

# Non-job path slugs to avoid treating category/nav pages as job postings
NON_JOB_SLUGS = {
    "karriere",
    "career",
    "careers",
    "jobs",
    "stellenangebote",
    "stellenanzeigen",
    "offene-stellen",
    "teams-und-projekte",
    "das-inovex-package-fuer-mitarbeiterinnen",
    "package",
    "benefits",
    "vorteile",
    "kultur",
    "culture",
    "standorte",
    "locations",
    "ueber-uns",
    "about-us",
    "team",
    "teams",
    "faq",
    "bewerbungsprozess",
    "bewerbung",
    "initiativbewerbung",
    "datenschutz",
    "impressum",
    "kontakt",
    "contact",
}

# Administrative labels and prefixes that must never be treated as people
ADMIN_LABELS = (
    "sitz",
    "register",
    "amtsgericht",
    "handelsregister",
    "ust",
    "umsatzsteuer",
    "telefon",
    "tel",
    "fax",
    "telefax",
    "e-mail",
    "email",
    "mail",
    "kontakt",
    "contact",
    "aufsichtsrat",
    "vorsitzend",
    "verantwortlich",
    "redaktion",
    "gemäß",
    "gem.",
    "diensteanbieter",
    "iban",
    "bic",
    "bank",
    "steuer",
    "w-idnr",
    "postanschrift",
    "adresse",
)

# Administrative keywords and city names that cannot form part of a person name
ADMIN_WORDS = {
    "sitz", "register", "registergericht", "amtsgericht", "handelsregister",
    "karlsruhe", "berlin", "münchen", "hamburg", "frankfurt", "köln", "stuttgart",
    "düsseldorf", "germany", "deutschland", "telefon", "fax", "email", "mail",
    "kontakt", "gmbh", "ag", "co", "kg", "hrb", "hra", "ust", "idnr",
    "aufsichtsrat", "vorstand", "geschäftsführer", "geschäftsführung", "inhaber",
    "vorsitzender", "vertreten", "durch", "gericht", "nummer", "gesellschaft",
    "mannheim", "hannover", "nürnberg", "leipzig", "dresden", "bremen", "dortmund",
    "essen", "bonn",
}

# Recognized nobiliary particles in German personal names
GERMAN_NOBLE_PARTICLES = {"von", "van", "de", "zu", "der", "vom"}


def find_impressum_url(
    discovered_links: List[DiscoveredLink],
    base_url: str,
) -> Optional[str]:
    """
    Search discovered links for Impressum references.
    Ranks links and returns the most probable Impressum URL.
    """
    best_url: Optional[str] = None
    best_score = 0

    for link in discovered_links:
        if not link.is_internal:
            continue

        score = 0
        url_lower = link.url.lower()
        text_lower = link.text.lower()
        path = urlparse(url_lower).path

        for term in IMPRESSUM_TERMS:
            # Exact or close text match
            if text_lower == term:
                score += 30
            elif term in text_lower:
                score += 15

            # URL path match
            if f"/{term}" in path:
                score += 25
            elif term in url_lower:
                score += 10

        if score > best_score and score >= 15:
            best_score = score
            best_url = link.url

    # Fallback: check if /impressum was discovered directly
    if not best_url:
        for link in discovered_links:
            if link.is_internal and urlparse(link.url.lower()).path.rstrip("/") == "/impressum":
                return link.url

    return best_url


def find_career_url(
    discovered_links: List[DiscoveredLink],
    base_domain: str,
) -> Tuple[Optional[str], bool]:
    """
    Find internal or external career page URL.
    
    Returns:
        (career_url, is_external)
    """
    best_internal_url: Optional[str] = None
    best_internal_score = 0

    external_ats_url: Optional[str] = None

    for link in discovered_links:
        url_lower = link.url.lower()
        text_lower = link.text.lower()
        path = urlparse(url_lower).path

        # Check for external ATS portals
        for ats in EXTERNAL_ATS_PATTERNS:
            if ats in url_lower:
                if not external_ats_url:
                    external_ats_url = link.url

        if not link.is_internal:
            continue

        score = 0
        for term in CAREER_TERMS:
            if text_lower == term:
                score += 25
            elif term in text_lower:
                score += 15

            if f"/{term}" in path:
                score += 20
            elif term in path:
                score += 10

        if score > best_internal_score and score >= 15:
            best_internal_score = score
            best_internal_url = link.url

    if best_internal_url:
        return best_internal_url, False

    if external_ats_url:
        return external_ats_url, True

    return None, False


def extract_company_data(
    selector: Selector,
    source_url: str,
    website_url: str,
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """
    Extract company metadata and representatives from an Impressum page selector.
    
    Returns:
        (company_dict, persons_list)
    """
    # Extract clean full text representation
    body_text = selector.get_all_text() or ""
    raw_lines = [line.strip() for line in body_text.splitlines() if line.strip()]
    full_text = "\n".join(raw_lines)

    domain = normalize_domain(website_url or source_url)
    is_impressum_source = bool(re.search(r"impressum|imprint|legal", source_url, re.IGNORECASE))

    data: Dict[str, Any] = {
        "domain": domain,
        "website_url": website_url or source_url,
        "impressum_url": source_url if is_impressum_source else None,
        "name": None,
        "legal_form": None,
        "street": None,
        "house_number": None,
        "postal_code": None,
        "city": None,
        "country": None,
        "email": None,
        "phone": None,
        "fax": None,
        "vat_id": None,
        "register_number": None,
        "register_court": None,
    }

    # 1. VAT ID Extraction (USt-IdNr.)
    vat_match = re.search(r"\b(DE\s?[0-9]{9})\b", full_text)
    if not vat_match:
        vat_match = re.search(
            r"(?:USt-?Id(?:-?Nr\.?|entifikationsnummer)?|VAT(?:\s*ID)?|UID)\s*[:.]?\s*([A-Z]{2}\s?[0-9A-Za-z]{8,12})\b",
            full_text,
            re.IGNORECASE,
        )
    if vat_match:
        data["vat_id"] = re.sub(r"\s+", "", vat_match.group(1).upper())

    # 2. Commercial Register Number & Court
    reg_match = re.search(
        r"\b(HRB|HRA)\s*[:.]?\s*([0-9]{3,7}(?:\s*[A-Z])?)\b", full_text, re.IGNORECASE
    )
    if reg_match:
        data["register_number"] = f"{reg_match.group(1).upper()} {reg_match.group(2).strip()}"

    court_match = re.search(
        r"(?:Amtsgericht|Registergericht)\s+([A-ZÄÖÜ][a-zäöüß\-]+)", full_text
    )
    if court_match:
        data["register_court"] = f"Amtsgericht {court_match.group(1).strip()}"

    # 3. Email Extraction
    email_matches = re.findall(
        r"\b([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b", full_text
    )
    valid_emails = [
        e for e in email_matches
        if not re.search(r"\.(png|jpg|jpeg|gif|svg|webp|css|js)$", e, re.IGNORECASE)
        and "example.com" not in e.lower()
    ]
    if valid_emails:
        prioritized = [e for e in valid_emails if domain in e.lower()]
        data["email"] = prioritized[0] if prioritized else valid_emails[0]

    # 4. Phone & Fax Extraction
    phone_match = re.search(
        r"(?:Telefon|Tel(?:efon)?\.?|Phone|Fon)\s*[:.]?\s*(\+?[0-9\s\/\(\)\-\.]{7,25}\b)",
        full_text,
        re.IGNORECASE,
    )
    if phone_match:
        clean_phone = " ".join(phone_match.group(1).split())
        data["phone"] = clean_phone

    fax_match = re.search(
        r"(?:Telefax|Fax)\s*[:.]?\s*(\+?[0-9\s\/\(\)\-\.]{7,25}\b)",
        full_text,
        re.IGNORECASE,
    )
    if fax_match:
        clean_fax = " ".join(fax_match.group(1).split())
        data["fax"] = clean_fax

    # 5. Street, House number, Postal Code, and City (Line-based parsing)
    for line in raw_lines:
        line_clean = line.strip()

        # Street and house number
        if not data["street"]:
            street_m = re.match(
                r"^[ \t]*([A-ZÄÖÜa-zäöüß\.\-\s]+(?:straße|strasse|str\.|weg|platz|allee|ring|gasse|ufer|damm|chaussee|pfad))\s+(\d+\s*[a-zA-Z]?)$",
                line_clean,
                re.IGNORECASE,
            )
            if street_m:
                data["street"] = street_m.group(1).strip()
                data["house_number"] = street_m.group(2).strip()

        # Postal code and City (German 5-digit PLZ + City)
        if not data["postal_code"]:
            plz_m = re.match(
                r"^(?:D-)?[ \t]*(\d{5})\s+([A-ZÄÖÜ][a-zäöüßA-Z\s\-]+(?:\s*\([A-ZÄÖÜa-zäöüß]+\))?)$",
                line_clean,
            )
            if plz_m:
                data["postal_code"] = plz_m.group(1).strip()
                data["city"] = plz_m.group(2).strip()

    # Fallback for PLZ/City if not on dedicated line
    if not data["postal_code"]:
        plz_city_match = re.search(
            r"\b(?:D-)?(\d{5})\s+([A-ZÄÖÜ][a-zäöüßA-Z\s\-]+)",
            full_text,
        )
        if plz_city_match:
            data["postal_code"] = plz_city_match.group(1).strip()
            data["city"] = plz_city_match.group(2).split("\n")[0].split(",")[0].strip()

    # Fallback for Street
    if not data["street"]:
        street_match = re.search(
            r"\b([A-ZÄÖÜa-zäöüß\.\-\s]+(?:straße|strasse|str\.|weg|platz|allee|ring|gasse|ufer|damm|chaussee|pfad))\s+(\d+\s*[a-zA-Z]?)",
            full_text,
            re.IGNORECASE,
        )
        if street_match:
            data["street"] = street_match.group(1).strip()
            data["house_number"] = street_match.group(2).strip()

    # Country detection
    if re.search(r"\b(Deutschland|Germany)\b", full_text, re.IGNORECASE):
        data["country"] = "Germany"
    elif re.search(r"\b(Österreich|Austria)\b", full_text, re.IGNORECASE):
        data["country"] = "Austria"
    elif re.search(r"\b(Schweiz|Switzerland)\b", full_text, re.IGNORECASE):
        data["country"] = "Switzerland"
    elif data["postal_code"] or data["register_court"] or (data["vat_id"] and data["vat_id"].startswith("DE")):
        data["country"] = "Germany"

    # 6. Legal Form & Company Name
    for form in LEGAL_FORMS:
        pattern = r"\b" + re.escape(form) + r"\b"
        if re.search(pattern, full_text, re.IGNORECASE):
            data["legal_form"] = form
            break

    # Extract company name by searching individual lines
    if data["legal_form"]:
        form_pattern = re.compile(r"\b" + re.escape(data["legal_form"]) + r"\b", re.IGNORECASE)
        for line in raw_lines:
            clean_l = re.sub(r"^(Impressum|Imprint|Legal Notice)\s*[-–|:]\s*", "", line, flags=re.IGNORECASE).strip()
            lower_l = clean_l.lower()
            if lower_l in ("impressum", "imprint", "legal notice", "angaben gemäß § 5 tmg", "angaben gemaess § 5 tmg"):
                continue

            if form_pattern.search(clean_l) and len(clean_l) <= 90:
                name_clean = re.sub(
                    r"^(Angaben gemäß § 5 TMG|Diensteanbieter|Firmenname|Firma|Name)\s*[:.]?\s*",
                    "",
                    clean_l,
                    flags=re.IGNORECASE,
                ).strip()
                data["name"] = name_clean
                break

    # Strategy B: Fallback from Page Title / Meta / Heading if name still empty
    if not data["name"]:
        page_title = ""
        try:
            title_el = selector.css("title")
            if title_el:
                page_title = (title_el[0].text or "").strip()
        except Exception:
            pass

        if page_title:
            parts = re.split(r"[-–|:]", page_title)
            for part in parts:
                clean_part = part.strip()
                if clean_part and not re.search(r"impressum|imprint|legal", clean_part, re.IGNORECASE):
                    data["name"] = clean_part
                    break

    # 7. Managing Directors / Representatives (company_persons)
    persons: List[Dict[str, str]] = []
    rep_section_match = re.search(
        r"(?:Vertreten durch(?:\s+die\s+Geschäftsführer|\s+den\s+Vorstand)?|Geschäftsführer(?:in)?|Geschäftsführung|Vorstand|Inhaber(?:in)?|Managing Director(?:s)?|CEO)\s*[:.]?\s*\n?([^\n\r]+(?:\n[^\n\r]+)*)",
        full_text,
        re.IGNORECASE,
    )
    if rep_section_match:
        section_raw = rep_section_match.group(1).strip()
        valid_lines: List[str] = []

        for line in section_raw.splitlines():
            line_clean = line.strip()
            if not line_clean:
                continue

            # Truncate line at administrative labels if present
            trunc = re.split(
                r"(?:Registergericht|Handelsregister|USt-?Id|Telefon|Tel\.|E-Mail|Fax|Kontakt|Sitz(?:\s+der\s+Gesellschaft)?\s*:|Amtsgericht)",
                line_clean,
                flags=re.IGNORECASE,
            )[0].strip()

            if not trunc:
                break
            valid_lines.append(trunc)

        text_to_process = " ".join(valid_lines)

        # Split multiple candidate names by comma, semicolon, 'und', 'and', '&'
        candidates = re.split(r"[,;]|\bund\b|\band\b|&", text_to_process)
        for c in candidates:
            name = c.strip()
            # Remove parenthetical roles e.g. (Vorsitzender), (CEO)
            name = re.sub(r"\(.*?\)", "", name).strip()
            # Remove German academic & professional titles
            name = re.sub(
                r"^(?:(?:Herr|Frau|Dr\.|Prof\.|Dipl\.-[a-zA-Z]+(?:\.)?|med\.|rer\.\s*nat\.|Ing\.|Kfm\.)\s*)+",
                "",
                name,
                flags=re.IGNORECASE,
            ).strip()

            tokens = name.split()
            # Plausible human names must have between 2 and 4 tokens
            if not (2 <= len(tokens) <= 4):
                continue

            # Ensure none of the tokens is an administrative word
            if any(t.lower().rstrip(":.,") in ADMIN_WORDS for t in tokens):
                continue

            # Verify that each token contains valid name characters (allow noble particles)
            valid_tokens = True
            for idx, t in enumerate(tokens):
                if t.lower() in GERMAN_NOBLE_PARTICLES and 0 < idx < len(tokens) - 1:
                    continue
                if not re.match(r"^[A-ZÄÖÜ][a-zäöüßA-ZÄÖÜ\.\-]*$", t) or len(t) < 2:
                    valid_tokens = False
                    break

            if not valid_tokens:
                continue

            first_name = " ".join(tokens[:-1])
            last_name = tokens[-1]

            # Avoid adding duplicate persons
            if not any(p["last_name"] == last_name and p["first_name"] == first_name for p in persons):
                persons.append({
                    "first_name": first_name,
                    "last_name": last_name,
                    "role": "Managing Director",
                })

    return data, persons


def extract_job_postings(
    selector: Selector,
    career_url: str,
    base_domain: str,
) -> List[Dict[str, Any]]:
    """
    Extract job advertisements from a career page using Scrapling selector.
    
    Identifies genuine job listings using structural HTML patterns, link targets,
    and job-specific terminology while filtering out non-job navigation and category links.
    """
    jobs: List[Dict[str, Any]] = []
    seen_urls: set = set()

    page_url = selector.url or career_url

    try:
        anchors = selector.css("a")
    except Exception:
        anchors = []

    # Job slug pattern for detail pages
    job_slug_patterns = re.compile(
        r"/(?:job|jobs|stellenangebot|stellenangebote|stelle|stellen|position|positions|karriere|career|careers|offene-stellen)/([a-zA-Z0-9\-_]{3,})",
        re.IGNORECASE,
    )

    # Job title indicator keywords (German & English)
    job_keywords = re.compile(
        r"(\((?:m/w/d|w/m/d|d/m/w|f/m/d|m/f/d|all genders)\)|\*m/w/d\*|:in\*|\*in|:in\b|\b(Developer|Entwickler|Engineer|Manager|Consultant|Berater|Assistent|Specialist|Spezialist|Designer|Praktikant|Praktikum|Werkstudent|Techniker|Architekt|Architect|Koordinator|Administrator|Analyst|Sales|Marketing|Buchhalter|Kaufmann|Kauffrau|Lead|Officer|Expert|Scientist|DevOps|Scrum Master|Product Owner|Recruiter|Thesis)\b)",
        re.IGNORECASE,
    )

    for a in anchors:
        raw_href = a.attrib.get("href")
        if not raw_href:
            continue

        normalized = normalize_url(raw_href, base_url=page_url)
        if not normalized or normalized in seen_urls:
            continue

        # Rule 1: Exclude self-references to career landing page
        if normalized.rstrip("/") == career_url.rstrip("/"):
            continue

        # Rule 2: Inspect URL path segments
        parsed_url = urlparse(normalized)
        path_segments = [s.lower() for s in parsed_url.path.split("/") if s]
        if not path_segments:
            continue

        last_slug = path_segments[-1]
        if last_slug in NON_JOB_SLUGS:
            continue

        # Rule 3: Extract and clean candidate job title
        headings = a.css("h1, h2, h3, h4, h5, .title, .job-title, .job-name")
        if headings:
            heading_text = (headings.first.get_all_text() or "").strip()
            text = " ".join(heading_text.split())
        else:
            raw_text = (a.get_all_text() or "").strip()
            text = " ".join(raw_text.split())

        if not text:
            continue

        lower_text = text.lower()
        if lower_text in NON_JOB_TITLES or len(text) < 5 or len(text) > 160:
            continue

        # Rule 4: Check for job indicators
        has_job_keyword = bool(job_keywords.search(text))

        # Check for specific job URL path
        slug_match = job_slug_patterns.search(normalized)
        is_job_url = False
        if slug_match:
            sub_slug = slug_match.group(1).lower()
            if sub_slug not in NON_JOB_SLUGS and len(sub_slug) >= 4:
                is_job_url = True

        # Check for specific job container classes (excluding generic 'career' or 'listing')
        parent_has_job_card = False
        try:
            parent = a.parent
            if parent:
                parent_cls = parent.attrib.get("class", "").lower()
                parent_classes = set(parent_cls.split())
                if any(
                    any(item in cls for item in ("job-card", "job-item", "job-post", "job-entry", "job-listing-item"))
                    for cls in parent_classes
                ):
                    parent_has_job_card = True
        except Exception:
            pass

        # Decision rule: Must have job title evidence, OR job-specific URL with plausible title, OR specific job card container
        if has_job_keyword or is_job_url or parent_has_job_card:
            seen_urls.add(normalized)

            location: Optional[str] = None
            employment_type: Optional[str] = None
            description: Optional[str] = None

            combined_context = text
            try:
                parent_text = a.parent.get_all_text() if a.parent else ""
                combined_context += " " + parent_text
            except Exception:
                pass

            if re.search(r"\b(Vollzeit|Full-time)\b", combined_context, re.IGNORECASE):
                employment_type = "Full-time"
            elif re.search(r"\b(Teilzeit|Part-time)\b", combined_context, re.IGNORECASE):
                employment_type = "Part-time"
            elif re.search(r"\b(Werkstudent|Working Student)\b", combined_context, re.IGNORECASE):
                employment_type = "Working Student"
            elif re.search(r"\b(Praktikum|Internship)\b", combined_context, re.IGNORECASE):
                employment_type = "Internship"

            loc_match = re.search(
                r"\b(Berlin|München|Munich|Hamburg|Köln|Cologne|Frankfurt|Stuttgart|Düsseldorf|Leipzig|Dresden|Nürnberg|Karlsruhe|Remote|Homeoffice|Hybrid)\b",
                combined_context,
                re.IGNORECASE,
            )
            if loc_match:
                location = loc_match.group(1).capitalize()

            jobs.append({
                "title": text,
                "url": normalized,
                "location": location,
                "employment_type": employment_type,
                "description": description,
            })

    return jobs
