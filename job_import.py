"""
job_import.py
--------------
OPTIONALES Zusatzmodul für CTAM: importiert Eckdaten einer Stellenanzeige
(Firma, Rolle, ggf. Standort) aus einem Job-Link.

Wichtiger Hinweis zur Architektur:
    CTAM ist als Offline-Anwendung konzipiert. Dieses Modul ist die EINZIGE
    Stelle im gesamten Programm, die eine Internetverbindung braucht -
    ausschließlich wenn der Nutzer aktiv auf "Aus Link importieren" klickt.
    Ohne Klick auf diese Funktion läuft CTAM weiterhin komplett offline.

Funktionsweise (Text-Heuristik, kein KI-Modell, keine externe API):
    1. HTML der Seite laden (requests, mit Timeout + User-Agent).
    2. Sichtbaren Text extrahieren (BeautifulSoup, Skripte/Styles entfernt).
    3. Firma erkennen über:
       a) <title>-Tag und Meta-Tags (og:site_name, author) als erste Quelle.
       b) Textmuster wie "bei <Firma>", "unternehmen: <Firma>",
          "arbeitgeber: <Firma>" im Fließtext.
    4. Rolle/Jobtitel erkennen über:
       a) Erste <h1>-Übrschrift der Seite (meistens der Stellentitel).
       b) <title>-Tag, sofern er nicht nur der Firmenname ist.
    5. Standort (optional) über Muster wie "Standort:", "Ort:", "in <Stadt>".

    Diese Heuristik ist bewusst konservativ: lieber ein Feld leer lassen als
    einen falschen Wert raten. Alle erkannten Werte werden dem Nutzer nur
    als VORSCHLAG präsentiert (Formular bleibt editierbar, nichts wird
    automatisch gespeichert).

Fehlerverhalten:
    Wirft JobImportError bei Netzwerkfehlern, nicht erreichbarer Seite oder
    wenn praktisch kein Text extrahiert werden konnte (z. B. Seiten, die
    ihren Inhalt erst per JavaScript nachladen - das kann diese Heuristik
    prinzipbedingt nicht lesen).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = (
    "Mozilla/5.0 (compatible; CTAM-JobImport/1.0; "
    "+lokales Bewerbungs-Tool, manueller Einzelabruf)"
)

# Muster, die auf einen Firmennamen im Fließtext hindeuten (deutsch/englisch).
COMPANY_PATTERNS = [
    r"(?:bei|for)\s+(?:der\s+|die\s+|the\s+)?([A-ZÄÖÜ][\wÄÖÜäöüß&.\-]+(?:\s+[A-ZÄÖÜ][\wÄÖÜäöüß&.\-]*){0,3}\s?(?:GmbH|AG|SE|KG|Inc\.?|Ltd\.?|Group|GmbH & Co\. ?KG)?)",
    r"(?:unternehmen|arbeitgeber|company|employer)\s*[:\-]\s*([A-ZÄÖÜ][\wÄÖÜäöüß&.\-]+(?:\s+[A-ZÄÖÜ][\wÄÖÜäöüß&.\-]*){0,3})",
]

# Muster für Standort/Ort
LOCATION_PATTERNS = [
    r"(?:standort|ort|location)\s*[:\-]\s*([A-ZÄÖÜ][\wÄÖÜäöüß\-]+(?:\s*/\s*[A-ZÄÖÜ][\wÄÖÜäöüß\-]+)?)",
]

# Wörter, die auf einen Jobtitel hindeuten (zur Plausibilitätsprüfung von h1)
ROLE_HINT_WORDS = [
    "entwickler", "developer", "engineer", "manager", "analyst", "berater",
    "consultant", "specialist", "spezialist", "leiter", "referent",
    "mitarbeiter", "praktikant", "werkstudent", "trainee", "designer",
    "architekt", "administrator", "koordinator", "sachbearbeiter",
]


class JobImportError(Exception):
    """Wird ausgelöst, wenn die Seite nicht geladen oder nicht sinnvoll
    ausgewertet werden konnte (Netzwerkfehler, leere Seite, ungültige URL)."""
    pass


@dataclass
class JobImportResult:
    """Ergebnis des Imports. Alle Felder sind Vorschläge - der Nutzer sieht
    und bestätigt sie im Formular, nichts wird automatisch übernommen."""
    firmenname: str = ""
    rollenbezeichnung: str = ""
    standort: str = ""
    joblink: str = ""
    quelle_domain: str = ""
    confidence_notes: list[str] | None = None  # kurze Hinweise, was unsicher war

    def has_any_data(self) -> bool:
        return bool(self.firmenname or self.rollenbezeichnung)


def _validate_url(url: str) -> str:
    url = url.strip()
    if not url:
        raise JobImportError("Bitte einen Job-Link eingeben.")
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        raise JobImportError("Das sieht nicht wie eine gültige URL aus.")
    return url


def _fetch_html(url: str) -> str:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        raise JobImportError(
            "Die Seite hat nicht rechtzeitig geantwortet (Timeout)."
        )
    except requests.exceptions.SSLError:
        raise JobImportError("SSL-Fehler beim Verbindungsaufbau zur Seite.")
    except requests.exceptions.ConnectionError:
        raise JobImportError(
            "Seite nicht erreichbar. Internetverbindung oder Link prüfen."
        )
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        raise JobImportError(f"Server antwortete mit Fehlerstatus {status}.")
    except requests.exceptions.RequestException as exc:
        raise JobImportError(f"Unbekannter Netzwerkfehler: {exc}")

    return response.text


def _extract_visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _guess_company_from_meta(soup: BeautifulSoup) -> str:
    for attrs in (
        {"property": "og:site_name"},
        {"name": "author"},
        {"name": "application-name"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            candidate = tag["content"].strip()
            if candidate and len(candidate) < 80:
                return candidate
    return ""


def _guess_company_from_text(text: str) -> str:
    for pattern in COMPANY_PATTERNS:
        match = re.search(pattern, text)
        if match:
            candidate = match.group(1).strip().rstrip(".,;:")
            if 2 <= len(candidate) <= 60:
                return candidate
    return ""


def _guess_role_from_h1(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1:
        candidate = h1.get_text(strip=True)
        if candidate and 3 <= len(candidate) <= 120:
            return candidate
    return ""


def _guess_role_from_title(title_text: str) -> str:
    if not title_text:
        return ""
    # Titel-Tags enthalten oft "Jobtitel | Firma" oder "Jobtitel - Firma (Ort)"
    parts = re.split(r"[|\-–—]", title_text)
    candidates = [p.strip() for p in parts if p.strip()]
    lowered_hints = ROLE_HINT_WORDS
    for candidate in candidates:
        low = candidate.lower()
        if any(hint in low for hint in lowered_hints):
            return candidate
    return candidates[0] if candidates else title_text.strip()


def _guess_location(text: str) -> str:
    for pattern in LOCATION_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip().rstrip(".,;:")
            if 2 <= len(candidate) <= 60:
                return candidate
    return ""


def import_from_url(url: str) -> JobImportResult:
    """Lädt die angegebene Stellenanzeige und extrahiert Firma, Rolle und
    ggf. Standort per Text-Heuristik. Wirft JobImportError bei Problemen.

    Diese Funktion ist die einzige Stelle in CTAM, die eine Netzwerk-
    verbindung herstellt - und nur dann, wenn sie explizit aufgerufen wird
    (z. B. per Klick auf "Aus Link importieren" im Formular)."""
    validated_url = _validate_url(url)
    html = _fetch_html(validated_url)
    soup = BeautifulSoup(html, "html.parser")
    visible_text = _extract_visible_text(soup)

    if len(visible_text) < 50:
        raise JobImportError(
            "Auf der Seite wurde kaum Text gefunden. Vermutlich lädt sie "
            "Inhalte per JavaScript nach - automatischer Import nicht möglich. "
            "Bitte Felder manuell ausfüllen."
        )

    title_tag = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else ""

    notes: list[str] = []

    firma = _guess_company_from_meta(soup) or _guess_company_from_text(visible_text)
    if not firma:
        notes.append("Firma konnte nicht sicher erkannt werden - bitte prüfen.")

    rolle = _guess_role_from_h1(soup) or _guess_role_from_title(title_text)
    if not rolle:
        notes.append("Rolle konnte nicht sicher erkannt werden - bitte prüfen.")
    elif firma and rolle.strip().lower() == firma.strip().lower():
        # h1 war offenbar nur der Firmenname, nicht der Jobtitel
        rolle = ""
        notes.append(
            "Erkannte Überschrift entsprach nur dem Firmennamen - "
            "Rolle bitte manuell eintragen."
        )

    standort = _guess_location(visible_text)

    result = JobImportResult(
        firmenname=firma,
        rollenbezeichnung=rolle,
        standort=standort,
        joblink=validated_url,
        quelle_domain=urlparse(validated_url).netloc,
        confidence_notes=notes,
    )

    if not result.has_any_data():
        raise JobImportError(
            "Es konnten keine verwertbaren Daten aus der Seite extrahiert "
            "werden. Bitte Firma und Rolle manuell eintragen."
        )

    return result
