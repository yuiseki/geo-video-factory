"""Which photos may be painted into a video, and which only help to place the others.

Only CC0 and public-domain photos are painted (atlases, ground, photo markers). CC BY and CC BY-SA photos are
collected only on request (cc0_photo_collector --license-mode=registration --registration-only) and kept under
their own refs, "registration-<source>:<id>", in their own place in the store; SfM may use them to place the
CC0/PD photos, and only those photos' cameras go on. Why this is sound, and what may leave the registration:
.agents/skills/geo-video-materials/references/registration-only-photos.md.
"""
import json
from pathlib import Path

from photos.photo_licences import is_cc0_or_public_domain

REGISTRATION = "registration-"


class NotPaintable(Exception):
    pass


def is_registration_ref(ref: str) -> bool:
    return str(ref).split(":", 1)[0].startswith(REGISTRATION)


def registration_ref(ref: str) -> str:
    return ref if is_registration_ref(ref) else REGISTRATION + ref


def check_paint(photo) -> None:
    """Raise NotPaintable unless the photo (a file of the store, or a link to one) is CC0 or public domain by the
    store's record. A file outside the store (a project's own copy, without meta.json) is left to its project's
    records."""
    real = Path(photo).resolve()
    meta_file = real.parent / "meta.json"
    if not meta_file.exists():
        return
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    if is_registration_ref(meta.get("ref", "")) or meta.get("use") == "registration":
        raise NotPaintable(f"{photo}: {meta.get('ref')} only helps to place the others")
    if not is_cc0_or_public_domain(meta.get("license", ""), meta.get("license_url", "")):
        raise NotPaintable(f"{photo}: {meta.get('ref')} is {meta.get('license')!r}, only CC0 and public domain are painted")
