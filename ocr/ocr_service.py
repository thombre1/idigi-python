"""
ocr_service.py
--------------
Core OCR extraction logic for Indian KYC documents.
Supports: Aadhaar Card, PAN Card, Driving Licence, Ration Card

Input:  PIL Image OR raw PDF bytes
Output: Structured JSON dict ready for KYC and Risk Scoring modules.
"""

import re
import json
import csv
import io
from PIL import Image, ImageFilter, ImageEnhance
import pytesseract

# pdf2image converts each PDF page into a PIL Image
# Install: pip install pdf2image
# Also needs poppler:
#   Ubuntu : sudo apt-get install poppler-utils
#   macOS  : brew install poppler
#   Windows: https://github.com/oschwartz10612/poppler-windows/releases
try:
    from pdf2image import convert_from_bytes
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False


# ──────────────────────────────────────────────
# PDF → IMAGE CONVERSION
# ──────────────────────────────────────────────

def pdf_to_images(pdf_bytes: bytes) -> list:
    """
    Convert a PDF file (as bytes) into a list of PIL Images, one per page.
    For KYC documents, usually only page 1 matters.

    Args:
        pdf_bytes: raw bytes of the PDF file

    Returns:
        List of PIL Image objects (one per page)

    Raises:
        RuntimeError if pdf2image / poppler is not installed
    """
    if not PDF_SUPPORT:
        raise RuntimeError(
            "pdf2image is not installed. Run: pip install pdf2image\n"
            "Also install poppler:\n"
            "  Ubuntu : sudo apt-get install poppler-utils\n"
            "  macOS  : brew install poppler\n"
            "  Windows: download from github.com/oschwartz10612/poppler-windows"
        )
    # dpi=300 matches what Tesseract prefers for accurate OCR
    images = convert_from_bytes(pdf_bytes, dpi=300)
    return images


# ──────────────────────────────────────────────
# IMAGE PRE-PROCESSING
# ──────────────────────────────────────────────

def preprocess_image(image: Image.Image, doc_type: str = None) -> Image.Image:
    """
    Enhance image before passing to Tesseract.
    Different document types benefit from slightly different settings:
      - PAN cards: lower contrast enhancement (card has clean print)
      - Aadhaar/scanned docs: higher contrast + denoise
    """
    image = image.convert("L")  # grayscale

    # Upscale if too small — Tesseract works best at ~300 DPI
    w, h = image.size
    if w < 1000:
        scale = 1000 / w
        image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    if doc_type == "pan":
        # PAN cards are cleanly printed — gentle contrast boost is enough
        # Over-enhancing blows out the thin font strokes
        image = ImageEnhance.Contrast(image).enhance(1.0)
        image = ImageEnhance.Sharpness(image).enhance(1.2)
    else:
        # Scanned/photographed docs need stronger enhancement
        image = ImageEnhance.Contrast(image).enhance(1.0)
        image = image.filter(ImageFilter.SHARPEN)

    return image


# ──────────────────────────────────────────────
# RAW TEXT EXTRACTION
# ──────────────────────────────────────────────

# PSM (Page Segmentation Mode) tells Tesseract how the text is laid out:
#   psm 6  = uniform block of text      → good for Aadhaar, DL, Ration Card
#   psm 11 = sparse text, no structure  → good for PAN card (fields scattered)
PSM_BY_DOCTYPE = {
    "pan":            11,
    "aadhaar":         6,
    "driving_licence": 6,
    "ration_card":     6,
}

def extract_raw_text(image: Image.Image, doc_type: str = None) -> str:
    """
    Run Tesseract OCR with the right PSM for the document type.
    If doc_type is unknown, tries psm 6 first, falls back to psm 11.
    """
    image = preprocess_image(image, doc_type)

    psm = PSM_BY_DOCTYPE.get(doc_type, 6)
    config = f"--oem 3 --psm {psm} -l eng"
    raw = pytesseract.image_to_string(image, config=config)

    # If very little text was found with psm 6, retry with psm 11
    if len(raw.strip()) < 30 and psm == 6:
        config_fallback = "--oem 3 --psm 11 -l eng"
        raw = pytesseract.image_to_string(image, config=config_fallback)
    print("="*25," START OF RAW ", "="*25)
    print(raw)
    print("="*25,"  END OF RAW ", "="*25)
    return raw.strip()


# ──────────────────────────────────────────────
# DOCUMENT TYPE DETECTION
# ──────────────────────────────────────────────

def detect_document_type(text: str) -> str:
    """
    Guess the document type from keywords in the OCR text.
    Returns one of: 'aadhaar', 'pan', 'driving_licence', 'ration_card', 'unknown'
    """
    text_lower = text.lower()

    if any(k in text_lower for k in ["aadhaar", "aadhar", "uidai", "unique identification"]):
        return "aadhaar"
    if any(k in text_lower for k in ["income tax", "permanent account", "pan"]):
        return "pan"
    if any(k in text_lower for k in ["driving licence", "driving license", "dl no", "transport"]):
        return "driving_licence"
    if any(k in text_lower for k in ["ration", "fair price", "food supply", "ration card"]):
        return "ration_card"
    return "unknown"


# ──────────────────────────────────────────────
# FIELD EXTRACTORS — one per document type
# ──────────────────────────────────────────────

def extract_aadhaar_fields(text: str) -> dict:
    """Extract structured fields from Aadhaar card OCR text."""
    fields = {}

    # Aadhaar number: 12 digits in groups of 4 (e.g. 1234 5678 9012)
    aadhaar_match = re.search(r"\b(\d{4}[\s\-]?\d{4}[\s\-]?\d{4})\b", text)
    if aadhaar_match:
        fields["aadhaar_number"] = re.sub(r"[\s\-]", "", aadhaar_match.group(1))

    # Date of Birth: DD/MM/YYYY or DD-MM-YYYY
    dob_match = re.search(r"\b(DOB|Date of Birth|Birth|Year of Birth)[:\s]*(\d{2}[/\-]\d{2}[/\-]\d{4}|\d{4})\b", text, re.IGNORECASE)
    if dob_match:
        fields["date_of_birth"] = dob_match.group(2)


    # Gender
    gender_match = re.search(r"\b(Male|Female|Transgender)|[/][:\s]*(Male|Female|Transgender)\b", text, re.IGNORECASE)
    if gender_match:
        fields["gender"] = gender_match.group(1).capitalize()

    


    # Name: line before or after the Aadhaar number
    # Heuristic: capitalised words on a line by themselves
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for line in lines:
        if re.search(r"^[A-Z][a-z]+(\s[A-Z][a-z]+)+$", line):
            if "aadhaar_number" in fields and line not in ["Government of India"]:
                fields["name"] = line
                break
        
            else:
                line = re.search(r"\b([A-Z][a-z]+\s[A-Z][a-z]+\s[A-Z][a-z]+|[A-Z][a-z]+\s[A-Z][a-z]+)\b")
                fields["name"] = line

    # Address: lines after "Address" keyword
    addr_match = re.search(r"(?:Address|Addr)[:\s]*([\s\S]{10,200}?)(?:\n\n|\Z)", text, re.IGNORECASE)
    if addr_match:
        addr = " ".join(addr_match.group(1).split())
        fields["address"] = addr[:300]  # cap length

    return fields


def extract_pan_fields(text: str) -> dict:
    """
    Extract structured fields from PAN card OCR text.

    PAN card layout (top to bottom):
      - "INCOME TAX DEPARTMENT" header
      - Name of cardholder   (ALL CAPS)
      - Father's name         (ALL CAPS)
      - Date of Birth
      - PAN number            (AAAAA9999A)

    FIX v2: old regex ^[A-Z\s]{5,50}$ was too strict — required >= 2 words,
    missed single-initial names like "A K SHARMA". Also excluded valid lines.
    New approach: keyword anchors first, then ALL-CAPS line heuristic.
    """
    fields = {}

    # ── PAN number ──────────────────────────────────────
    pan_match = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z]{1})\b", text)
    if pan_match:
        fields["pan_number"] = pan_match.group(1)

    # ── Date of Birth ───────────────────────────────────
    dob_match = re.search(r"\b(\d{2}[/\-]\d{2}[/\-]\d{4})\b", text)
    if dob_match:
        fields["date_of_birth"] = dob_match.group(1)

    # ── Name + Father's Name ────────────────────────────
    # Attempt 1: keyword-anchored search
    # the \u092a\u093f\u0924\u093e means 'name' in Devnagari
    name_kw = re.search(
        r"(?:Name|\u0928\u093e\u092e)[:\s/]*([A-Za-z][A-Za-z\s\.]{3,50})",
        text, re.IGNORECASE
    )
    father_kw = re.search(
        r"(?:Father(?:'s)?\s*Name|S[/\\]O|\u092a\u093f\u0924\u093e)[:\s/]*([A-Za-z][A-Za-z\s\.]{3,50})",
        text, re.IGNORECASE
    )
    if name_kw:
        fields["name"] = name_kw.group(1).strip().title()
    if father_kw:
        fields["father_name"] = father_kw.group(1).strip().title()

    # Attempt 2: ALL-CAPS line heuristic (PAN always prints names in caps)
    EXCLUDED = {
        "INCOME TAX DEPARTMENT", "GOVT OF INDIA",
        "GOVERNMENT OF INDIA", "PERMANENT ACCOUNT NUMBER",
        "INCOME TAX DEPT", "INDIA"
    }
    if "name" not in fields or "father_name" not in fields:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        caps_lines = []
        for line in lines:
            # Accept: all-caps words, may include dots and single letters (initials)
            # Reject: lines with digits, known headers, very short lines
            if (re.match(r"^[A-Z][A-Z\s\.]{3,50}$", line)
                    and line.upper() not in EXCLUDED
                    and not re.search(r"\d", line)
                    and len(line.strip()) > 3):
                caps_lines.append(line)

        if "name" not in fields and len(caps_lines) >= 1:
            fields["name"] = caps_lines[0].title()
        if "father_name" not in fields and len(caps_lines) >= 2:
            fields["father_name"] = caps_lines[1].title()

    return fields


def extract_driving_licence_fields(text: str) -> dict:
    """Extract structured fields from Driving Licence OCR text."""
    fields = {}

    # DL number: varies by state e.g. MH01 20200012345
    dl_match = re.search(r"\b([A-Z]{2}\d{2}[\s\-]?\d{4}[\s\-]?\d{7})\b", text)
    if dl_match:
        fields["dl_number"] = re.sub(r"[\s\-]", "", dl_match.group(1))

    # DOB
    dob_match = re.search(r"(?:DOB|Date of Birth)[:\s]*(\d{2}[/\-]\d{2}[/\-]\d{4})", text, re.IGNORECASE)
    if dob_match:
        fields["date_of_birth"] = dob_match.group(1)

    # Validity
    validity_match = re.search(r"(?:Valid Till|Validity|Expiry)[:\s]*(\d{2}[/\-]\d{2}[/\-]\d{4})", text, re.IGNORECASE)
    if validity_match:
        fields["valid_till"] = validity_match.group(1)

    # Name
    name_match = re.search(r"(?:Name|S/O|W/O|D/O)[:\s]*([A-Za-z\s]{5,50})", text, re.IGNORECASE)
    if name_match:
        fields["name"] = name_match.group(1).strip().title()

    return fields


def extract_ration_card_fields(text: str) -> dict:
    """Extract structured fields from Ration Card OCR text."""
    fields = {}

    # Ration Card number: varies, typically alphanumeric
    rc_match = re.search(r"\b([A-Z]{2,3}[\s\-]?\d{6,12})\b", text)
    if rc_match:
        fields["ration_card_number"] = rc_match.group(1)

    # Head of family name
    name_match = re.search(r"(?:Name|Head)[:\s]*([A-Za-z\s]{5,50})", text, re.IGNORECASE)
    if name_match:
        fields["name"] = name_match.group(1).strip().title()

    # Number of family members
    members_match = re.search(r"(?:Members|Family Size)[:\s]*(\d+)", text, re.IGNORECASE)
    if members_match:
        fields["family_members"] = int(members_match.group(1))

    # Card type (APL/BPL/AAY)
    card_type_match = re.search(r"\b(APL|BPL|AAY|NFSA)\b", text, re.IGNORECASE)
    if card_type_match:
        fields["card_type"] = card_type_match.group(1).upper()

    return fields


# ──────────────────────────────────────────────
# MASTER EXTRACTION FUNCTION
# ──────────────────────────────────────────────

def extract_document(image: Image.Image, doc_type_hint: str = None) -> dict:
    """
    Main entry point. Takes a PIL Image, returns a structured dict.

    Two-pass approach:
      Pass 1 — generic extraction to detect document type
      Pass 2 — re-extract using the correct PSM for that doc type
                (critical for PAN cards which need psm 11)

    Args:
        image: PIL Image object of the document
        doc_type_hint: optional override ('aadhaar','pan','driving_licence','ration_card')

    Returns:
        {
          "document_type": str,
          "raw_text": str,
          "fields": dict,
          "confidence": str,
          "missing_fields": list
        }
    """
    # Pass 1: detect doc type with generic settings
    raw_text_generic = extract_raw_text(image, doc_type=None)
    doc_type = doc_type_hint or detect_document_type(raw_text_generic)

    # Pass 2: re-run OCR with PSM tuned for this specific doc type
    raw_text = extract_raw_text(image, doc_type=doc_type)

    extractor_map = {
        "aadhaar":        extract_aadhaar_fields,
        "pan":            extract_pan_fields,
        "driving_licence": extract_driving_licence_fields,
        "ration_card":    extract_ration_card_fields,
    }

    expected_fields_map = {
        "aadhaar":         ["name", "aadhaar_number", "date_of_birth", "gender"],
        "pan":             ["name", "pan_number", "date_of_birth"],
        "driving_licence": ["name", "dl_number", "date_of_birth", "valid_till"],
        "ration_card":     ["name", "ration_card_number"],
    }

    extractor = extractor_map.get(doc_type, lambda t: {})
    fields = extractor(raw_text)

    expected = expected_fields_map.get(doc_type, [])
    missing = [f for f in expected if f not in fields]

    # Confidence based on how many expected fields were found
    found_ratio = (len(expected) - len(missing)) / max(len(expected), 1)
    confidence = "high" if found_ratio >= 0.75 else ("medium" if found_ratio >= 0.5 else "low")

    return {
        "document_type": doc_type,
        "raw_text": raw_text,
        "fields": fields,
        "confidence": confidence,
        "missing_fields": missing,
    }


# ──────────────────────────────────────────────
# FORMAT CONVERTERS
# ──────────────────────────────────────────────

def to_json(result: dict, pretty: bool = True) -> str:
    """Convert extraction result to JSON string."""
    output = {
        "document_type": result["document_type"],
        "confidence": result["confidence"],
        "missing_fields": result["missing_fields"],
        "fields": result["fields"],
    }
    return json.dumps(output, indent=2 if pretty else None)


def to_csv(result: dict) -> str:
    """
    Convert extraction result to CSV string.
    Each field becomes a row: field_name, value
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["document_type", "field", "value", "confidence"])
    doc_type = result["document_type"]
    confidence = result["confidence"]
    for key, value in result["fields"].items():
        writer.writerow([doc_type, key, value, confidence])
    return output.getvalue()


def build_kyc_payload(results: list) -> dict:
    """
    Merge fields from multiple documents into a single
    flat dict ready for the KYC + Risk Scoring module.

    Args:
        results: list of extract_document() outputs

    Returns:
        {
          "name": str,
          "date_of_birth": str,
          "gender": str,
          "aadhaar_number": str,
          "pan_number": str,
          "dl_number": str,
          "ration_card_number": str,
          "address": str,
          "documents_submitted": [str, ...],
          "ocr_confidence": {doc_type: confidence},
          "name_consistent": bool,   ← True if name matches across docs
        }
    """
    payload = {
        "documents_submitted": [],
        "ocr_confidence": {},
        "name_consistent": True,
    }

    names_found = []

    for result in results:
        doc_type = result["document_type"]
        fields = result["fields"]
        confidence = result["confidence"]

        payload["documents_submitted"].append(doc_type)
        payload["ocr_confidence"][doc_type] = confidence

        # Merge fields — don't overwrite if already set
        for key, value in fields.items():
            if key not in payload:
                payload[key] = value
            if key == "name":
                names_found.append(value.lower().strip())

    # Check name consistency across documents
    if len(names_found) > 1:
        # Simple check: first word of name should match
        first_words = [n.split()[0] for n in names_found]
        payload["name_consistent"] = len(set(first_words)) == 1

    return payload
