"""Website crawler using Scrapling with security validation and internal link discovery."""
import ipaddress
import socket
from typing import Dict, List, NamedTuple, Optional, Set, Tuple
from urllib.parse import urldefrag, urljoin, urlparse

from scrapling import Fetcher, Selector
from scrapling.engines.toolbelt.custom import Response


class DiscoveredLink(NamedTuple):
    """Represents a hyperlink found during crawling."""
    url: str
    text: str
    is_internal: bool


def normalize_domain(url_or_domain: str) -> str:
    """
    Extract a normalized domain name from a URL or raw domain.
    Strips protocol, paths, and leading 'www.' prefix.
    """
    candidate = url_or_domain.strip().lower()
    if "://" in candidate:
        parsed = urlparse(candidate)
        hostname = parsed.hostname or ""
    else:
        # If passed without scheme
        parsed = urlparse(f"http://{candidate}")
        hostname = parsed.hostname or candidate.split("/")[0]

    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def validate_url(url: str, check_dns: bool = True) -> Tuple[bool, str]:
    """
    Validate that an input URL is safe and acceptable:
    - HTTP or HTTPS only
    - Valid hostname
    - Rejects localhost and private/reserved IP addresses
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string."

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL syntax: {e}"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Unsupported scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL does not contain a valid hostname."

    hostname_lower = hostname.lower()
    if hostname_lower in ("localhost", "localhost.localdomain") or hostname_lower.endswith(".localhost"):
        return False, f"Localhost destination '{hostname}' is rejected for security."

    # Check if host is a direct IP address
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, f"Private or reserved IP address '{hostname}' is rejected."
        return True, ""
    except ValueError:
        # Host is a domain name
        pass

    if check_dns:
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for info in addr_info:
                ip_str = info[4][0]
                ip = ipaddress.ip_address(ip_str)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    return False, f"Domain '{hostname}' resolves to private/reserved IP '{ip_str}'."
        except socket.gaierror:
            # DNS resolution failed or host unreachable
            pass
        except Exception as e:
            return False, f"Error validating host address: {e}"

    return True, ""


def normalize_url(url: str, base_url: str = "") -> Optional[str]:
    """
    Normalize URL:
    - Resolves relative paths using base_url
    - Strips fragment identifiers (#...)
    - Lowercases scheme and netloc
    - Rejects invalid schemes (mailto:, tel:, javascript:)
    """
    if not url or not isinstance(url, str):
        return None

    url = url.strip()
    if url.startswith(("javascript:", "mailto:", "tel:", "sms:", "#", "data:")):
        return None

    if base_url:
        url = urljoin(base_url, url)

    clean_url, _ = urldefrag(url)
    try:
        parsed = urlparse(clean_url)
    except Exception:
        return None

    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return None

    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    # Clean redundant trailing slashes on non-root paths
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{netloc}{path}{query}"


def is_internal_url(url: str, base_domain: str) -> bool:
    """Check if the given URL belongs to the target company domain."""
    try:
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        norm_host = normalize_domain(hostname)
        norm_base = normalize_domain(base_domain)
        return norm_host == norm_base or norm_host.endswith(f".{norm_base}")
    except Exception:
        return False


class Crawler:
    """Scrapling-based web crawler for discovering company pages."""

    def __init__(
        self,
        start_url: str,
        max_pages: int = 20,
        timeout: int = 12,
        check_dns: bool = True,
    ):
        self.start_url = start_url.strip()
        self.max_pages = max_pages
        self.timeout = timeout
        self.check_dns = check_dns
        self.base_domain = normalize_domain(self.start_url)

        self.visited_urls: Set[str] = set()
        self.discovered_internal_links: List[DiscoveredLink] = []
        self.discovered_external_links: List[DiscoveredLink] = []
        self.pages: Dict[str, Response] = {}
        self.homepage_response: Optional[Response] = None

    def fetch(self, url: str) -> Optional[Response]:
        """Fetch a page using Scrapling Fetcher with timeouts and validation."""
        is_valid, reason = validate_url(url, check_dns=self.check_dns)
        if not is_valid:
            return None

        try:
            response = Fetcher.get(
                url,
                timeout=self.timeout,
                follow_redirects=True,
                retries=1,
            )
            # Ensure final redirect URL is still safe and valid
            if response and response.url:
                is_valid_dest, _ = validate_url(response.url, check_dns=self.check_dns)
                if not is_valid_dest:
                    return None
            return response
        except Exception:
            return None

    def extract_links_from_response(self, response: Response) -> List[DiscoveredLink]:
        """Extract all valid hyperlinks from a fetched page."""
        links: List[DiscoveredLink] = []
        page_url = response.url or self.start_url

        try:
            anchor_elements = response.css("a")
        except Exception:
            anchor_elements = []

        for anchor in anchor_elements:
            raw_href = anchor.attrib.get("href")
            if not raw_href:
                continue

            normalized = normalize_url(raw_href, base_url=page_url)
            if not normalized:
                continue

            # Anchor text
            text = (anchor.get_all_text() or "").strip()
            # Clean inner whitespace
            text = " ".join(text.split())

            internal = is_internal_url(normalized, self.base_domain)
            discovered = DiscoveredLink(url=normalized, text=text, is_internal=internal)
            links.append(discovered)

        return links

    def crawl_homepage(self) -> Optional[Response]:
        """Fetch the homepage and index its links."""
        norm_start = normalize_url(self.start_url)
        if not norm_start:
            return None

        response = self.fetch(norm_start)
        if not response or response.status >= 400:
            return None

        self.homepage_response = response
        self.visited_urls.add(norm_start)
        if response.url:
            self.visited_urls.add(normalize_url(response.url) or response.url)

        self.pages[norm_start] = response

        # Extract links from homepage
        links = self.extract_links_from_response(response)
        seen_urls: Set[str] = set()

        for link in links:
            if link.url in seen_urls:
                continue
            seen_urls.add(link.url)

            if link.is_internal:
                self.discovered_internal_links.append(link)
            else:
                self.discovered_external_links.append(link)

        return response

    def crawl_targeted_pages(self, prioritized_urls: List[str]) -> Dict[str, Response]:
        """
        Crawl specific discovered pages (e.g. Impressum, Career pages)
        respecting the max_pages limit.
        """
        for url in prioritized_urls:
            if len(self.visited_urls) >= self.max_pages:
                break

            norm = normalize_url(url, base_url=self.start_url)
            if not norm or norm in self.visited_urls:
                continue

            if not is_internal_url(norm, self.base_domain):
                continue

            self.visited_urls.add(norm)
            resp = self.fetch(norm)
            if resp and resp.status < 400:
                self.pages[norm] = resp
                # Also extract any additional internal links
                additional = self.extract_links_from_response(resp)
                for item in additional:
                    if item.is_internal and not any(x.url == item.url for x in self.discovered_internal_links):
                        self.discovered_internal_links.append(item)

        return self.pages

