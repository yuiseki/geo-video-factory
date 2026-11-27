"""Licence predicates of the photo catalogues: which licences a collector takes, in which mode.

    cc0           strict CC0 / CC-Zero
    cc0_pd        CC0 or public domain: neither needs attribution; the only photos painted into a video
    ccby_nosa     CC0 or CC BY (no SA, NC, ND)
    registration  CC BY or CC BY-SA only: photos that help SfM place the others, never painted (photos/photo_use.py)
"""
from __future__ import annotations

import re

DISALLOWED_LICENSE_RE = re.compile(
    r"(?:^|[^a-zA-Z])(?:NC|ND|SA|BY|PDM|GPL|GFDL)(?:[^a-zA-Z]|$)|PD-|Public\s*domain|Copyright|Fair\s*use|Attribution|ShareAlike|NoDerivatives|NonCommercial",
    re.IGNORECASE,
)


def is_strict_cc0(license_short: str, license_url: str = "") -> bool:
    """Return True strictly for CC0 / CC-Zero licenses only."""
    short = (license_short or "").strip()
    url = (license_url or "").strip().lower()
    if short and DISALLOWED_LICENSE_RE.search(short):
        return False
    low = short.lower()
    if low in ("cc0", "cc0 1.0", "cc-zero", "cc0-1.0", "cc0 1.0 universal"):
        return True
    if low.startswith("cc0 ") or low.startswith("cc-zero"):
        return True
    if "creativecommons.org/publicdomain/zero/1.0" in url and (
        not short or "no restriction" in low or "cc0" in low or "zero" in low
    ):
        return True
    return False


def is_ccby_nosa_or_cc0(license_short: str, license_url: str = "") -> bool:
    """Return True for CC0 / CC-Zero or CC BY (non-SA, non-NC, non-ND) licenses."""
    if is_strict_cc0(license_short, license_url):
        return True
    short = (license_short or "").strip()
    url = (license_url or "").strip().lower()
    if re.search(
        r"(?:^|[^a-zA-Z])(?:NC|ND|SA|PDM|GPL|GFDL)(?:[^a-zA-Z]|$)|PD-|Public\s*domain|Copyright|Fair\s*use|ShareAlike|NoDerivatives|NonCommercial",
        short,
        re.IGNORECASE,
    ):
        return False
    low = short.lower()
    if re.search(r"(?:^|[^a-z])cc[ -]by(?:\s|$|[0-9-])", low):
        return True
    if "creativecommons.org/licenses/by/" in url:
        return True
    return False


CC0_URL = "https://creativecommons.org/publicdomain/zero/1.0/"


def licence_name_and_url(license_short: str, license_url: str) -> tuple[str, str]:
    """Fill in a missing licence name or URL from the other one, for a licence that already passed the filter.

    Nothing is assumed to be CC0: an attribution licence known only by its URL keeps its own name, and one known
    only by a name without a version gets no URL rather than a guessed one."""
    short, url = (license_short or "").strip(), (license_url or "").strip()
    if is_strict_cc0(short, url):
        return short or "CC0", url or CC0_URL
    by_url = re.search(r"creativecommons\.org/licenses/by/(\d+(?:\.\d+)?)", url, re.IGNORECASE)
    if not short and by_url:
        short = f"CC BY {by_url.group(1)}"
    by_name = re.fullmatch(r"cc[ -]by[ -](\d+(?:\.\d+)?)", short, re.IGNORECASE)
    if not url and by_name:
        url = f"https://creativecommons.org/licenses/by/{by_name.group(1)}/"
    return short, url


def is_cc0_or_public_domain(license_short: str, license_url: str = "") -> bool:
    """CC0, or public domain (Commons' "Public domain", PD-* templates, the Public Domain Mark): no attribution
    needed and no share-alike. Anything with BY, SA or NC in it is refused."""
    if is_strict_cc0(license_short, license_url):
        return True
    low = (license_short or "").strip().lower()
    if not low or re.search(r"\b(by|sa|nc|nd|gfdl)\b", low):
        return False
    return low.startswith(("public domain", "pd-", "pd ", "pdm")) or low == "pd" or \
        "creativecommons.org/publicdomain/mark" in (license_url or "").lower()


def is_registration_only(license_short: str, license_url: str = "") -> bool:
    """CC BY or CC BY-SA (no NC, no ND, not CC0 or public domain): a photo that may only help to place the others,
    never be painted (references/registration-only-photos.md in the geo-video-materials skill)."""
    low = (license_short or "").strip().lower()
    if not low or re.search(r"\b(nc|nd)\b", low) or is_cc0_or_public_domain(license_short, license_url):
        return False
    return re.match(r"^cc[ -]by(-sa)?\b", low) is not None


def _license_allowed(license_short: str, license_url: str, license_mode: str) -> bool:
    if license_mode == "registration":
        return is_registration_only(license_short, license_url)
    if license_mode == "cc0_pd":
        return is_cc0_or_public_domain(license_short, license_url)
    if license_mode == "ccby_nosa":
        return is_ccby_nosa_or_cc0(license_short, license_url)
    return is_strict_cc0(license_short, license_url)
