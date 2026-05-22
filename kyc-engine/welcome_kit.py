from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "welcome_kits")
os.makedirs(OUTPUT_DIR, exist_ok=True)

BANK_NAME    = "iDigi Cloud"
BANK_ADDRESS = "123 Finance Street, Mumbai – 400 001, Maharashtra"
BANK_EMAIL   = "support@idigicloud.com"
BANK_PHONE   = "1800-123-4567"
BANK_WEBSITE = "www.idigicloud.com"
BANK_LOGO    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bank_logo.png")

BRAND_DARK   = colors.HexColor("#1A3557")
BRAND_ACCENT = colors.HexColor("#E53935")
BRAND_LIGHT  = colors.HexColor("#F0F4FA")
BRAND_GREEN  = colors.HexColor("#2E7D32")
BRAND_AMBER  = colors.HexColor("#F57C00")
BRAND_RED    = colors.HexColor("#C62828")


@dataclass
class CustomerInfo:
    account_opening_id: str
    first_name: str
    last_name: str
    aadhaar_number: str
    pan_number: str
    date_of_birth: str
    mobile: str
    email: str
    pincode: str
    occupation: str
    income: int
    deposit_amount: int
    account_number: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def masked_aadhaar(self) -> str:
        a = self.aadhaar_number
        return f"XXXX XXXX {a[-4:]}" if len(a) >= 4 else "XXXX XXXX XXXX"


@dataclass
class KycResult:
    verified: bool
    aml_clean: bool
    risk_score: float
    status: str
    remarks: str
    age: int = 0
    deposit_income_ratio: float = 0.0


def _styles():
    base = getSampleStyleSheet()

    def s(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    return {
        "bank_name": s("BankName", fontSize=22, textColor=BRAND_DARK, fontName="Helvetica-Bold", spaceAfter=2),
        "section":   s("Section",  fontSize=14, textColor=BRAND_DARK, fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=6),
        "body":      s("Body",     fontSize=10, textColor=colors.HexColor("#222222"), leading=16, spaceAfter=6),
        "small":     s("Small",    fontSize=8,  textColor=colors.grey, leading=12),
        "label":     s("Label",    fontSize=9,  textColor=colors.HexColor("#555555"), fontName="Helvetica-Bold"),
        "value":     s("Value",    fontSize=10, textColor=colors.HexColor("#111111")),
        "footer":    s("Footer",   fontSize=8,  textColor=colors.grey, alignment=1),
        "status_ok": s("SOk",      fontSize=13, textColor=BRAND_GREEN, fontName="Helvetica-Bold"),
        "status_rv": s("SRv",      fontSize=13, textColor=BRAND_AMBER, fontName="Helvetica-Bold"),
        "status_no": s("SNo",      fontSize=13, textColor=BRAND_RED,   fontName="Helvetica-Bold"),
    }


def _divider(accent=False):
    colour = BRAND_ACCENT if accent else colors.HexColor("#CCCCCC")
    return HRFlowable(width="100%", thickness=1, color=colour, spaceAfter=8, spaceBefore=4)


def _header(st: dict, subtitle: str = "") -> list:
    logo_cell = Image(BANK_LOGO, width=18*mm, height=18*mm) if os.path.exists(BANK_LOGO) else Paragraph("", st["body"])
    name_block = [Paragraph(BANK_NAME, st["bank_name"])]
    header_table = Table([[logo_cell, name_block]], colWidths=[22*mm, 148*mm])
    header_table.setStyle(TableStyle([
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING",   (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
    ]))
    elems = [header_table]
    if subtitle:
        elems.append(Paragraph(subtitle, st["section"]))
    elems.append(_divider(accent=True))
    return elems


def _footer_text(st: dict) -> list:
    return [
        Spacer(1, 10 * mm),
        _divider(),
        Paragraph(
            f"{BANK_NAME} &bull; {BANK_ADDRESS}<br/>{BANK_PHONE} &bull; {BANK_EMAIL} &bull; {BANK_WEBSITE}",
            st["footer"],
        ),
    ]


def _kv_table(rows: list[tuple[str, str]], st: dict) -> Table:
    data = [[Paragraph(k, st["label"]), Paragraph(v, st["value"])] for k, v in rows]
    t = Table(data, colWidths=[55*mm, 110*mm])
    t.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [BRAND_LIGHT, colors.white]),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t


def _build_cover(c: CustomerInfo, kyc: KycResult, st: dict) -> list:
    today = datetime.today().strftime("%d %B %Y")
    elems = _header(st)
    elems += [
        Spacer(1, 10 * mm),
        Paragraph(f"Dear {c.full_name},", st["body"]),
        Spacer(1, 4 * mm),
        Paragraph(
            f"We are delighted to welcome you to <b>{BANK_NAME}</b> — your trusted partner "
            f"for secure, modern digital banking. Your account opening application "
            f"<b>({c.account_opening_id})</b> has been received and your KYC verification "
            f"has been completed on <b>{today}</b>.",
            st["body"],
        ),
        Spacer(1, 4 * mm),
        Paragraph(
            "This Welcome Kit contains all the important information about your new account. "
            "Please keep it in a safe place for your reference.",
            st["body"],
        ),
        Spacer(1, 6 * mm),
        Paragraph("What's inside this kit:", st["section"]),
        _kv_table([
            ("Section 1", "Welcome Letter (this page)"),
            ("Section 2", "Account Summary"),
            ("Section 3", "KYC Verification Result"),
            ("Section 4", "Terms &amp; Conditions"),
        ], st),
        Spacer(1, 8 * mm),
        Paragraph(
            f"If you have any questions, our support team is available 24/7 at "
            f"<b>{BANK_PHONE}</b> or <b>{BANK_EMAIL}</b>.",
            st["body"],
        ),
        Spacer(1, 6 * mm),
        Paragraph("Warm regards,", st["body"]),
        Paragraph(f"<b>The {BANK_NAME} Onboarding Team</b>", st["body"]),
        Paragraph(today, st["small"]),
    ]
    elems += _footer_text(st)
    return elems


def _build_account_summary(c: CustomerInfo, st: dict) -> list:
    today = datetime.today().strftime("%d %B %Y")
    acc_no = c.account_number or f"IDIGI{c.account_opening_id[-6:].upper().zfill(6)}"
    elems = _header(st, subtitle="Section 2 — Account Summary")
    elems += [
        Paragraph("Personal Details", st["section"]),
        _kv_table([
            ("Full Name",    c.full_name),
            ("Date of Birth",c.date_of_birth),
            ("Occupation",   c.occupation.title()),
            ("Mobile",       c.mobile or "—"),
            ("Email",        c.email or "—"),
            ("PIN Code",     c.pincode or "—"),
        ], st),
        Spacer(1, 6 * mm),
        Paragraph("Identity Details", st["section"]),
        _kv_table([
            ("Aadhaar Number", c.masked_aadhaar),
            ("PAN Number",     c.pan_number.upper()),
        ], st),
        Spacer(1, 6 * mm),
        Paragraph("Account Details", st["section"]),
        _kv_table([
            ("Account Number",  acc_no),
            ("Account Type",    "Savings Account"),
            ("Opening Date",    today),
            ("Annual Income",   f"Rs. {c.income:,}"),
            ("Initial Deposit", f"Rs. {c.deposit_amount:,}"),
            ("Branch",          "Digital / Online"),
            ("IFSC Code",       "IDIGI0000001"),
        ], st),
    ]
    elems += _footer_text(st)
    return elems


def _build_kyc_result(c: CustomerInfo, kyc: KycResult, st: dict) -> list:
    status_style = {"APPROVED": st["status_ok"], "REVIEW": st["status_rv"], "REJECTED": st["status_no"]}.get(kyc.status, st["status_rv"])
    status_icon  = {"APPROVED": "✔ APPROVED", "REVIEW": "⚠ MANUAL REVIEW", "REJECTED": "✘ REJECTED"}.get(kyc.status, kyc.status)
    elems = _header(st, subtitle="Section 3 — KYC Verification Result")
    elems += [
        Paragraph("Verification Outcome", st["section"]),
        Spacer(1, 3 * mm),
        Paragraph(status_icon, status_style),
        Spacer(1, 3 * mm),
        _kv_table([
            ("Reference ID",      c.account_opening_id),
            ("Applicant Name",    c.full_name),
            ("Verification Date", datetime.today().strftime("%d %B %Y")),
            ("Identity Verified", "Yes" if kyc.verified  else "No"),
            ("AML Status",        "Clean" if kyc.aml_clean else "Flagged"),
            ("Risk Score",        f"{kyc.risk_score:.2f} / 1.00"),
            ("Status",            kyc.status),
            ("Remarks",           kyc.remarks),
        ], st),
        Spacer(1, 6 * mm),
        Paragraph("Derived Risk Factors", st["section"]),
        _kv_table([
            ("Age at Application",     f"{kyc.age} years"),
            ("Deposit / Income Ratio", f"{kyc.deposit_income_ratio:.2f}x"),
        ], st),
        Spacer(1, 6 * mm),
        Paragraph(
            "<b>Risk Score Guide:</b> &lt; 0.35 = Low Risk (Approved) &nbsp;|&nbsp; "
            "0.35 – 0.69 = Medium Risk (Review) &nbsp;|&nbsp; &ge; 0.70 = High Risk (Rejected)",
            st["small"],
        ),
    ]
    elems += _footer_text(st)
    return elems


def _build_terms(st: dict) -> list:
    elems = _header(st, subtitle="Section 4 — Terms &amp; Conditions")
    clauses = [
        ("1. Account Usage",
         "Your account is for personal banking use only. Commercial transactions must be conducted "
         "through a business account. Misuse may result in account suspension without prior notice."),
        ("2. KYC Compliance",
         "You are required to keep your KYC documents up to date. Failure to comply with periodic "
         "re-KYC requirements may result in restrictions on your account."),
        ("3. Confidentiality",
         f"You must keep your account credentials, OTPs, and PINs strictly confidential. "
         f"{BANK_NAME} will never ask for your password or OTP via phone or email."),
        ("4. Transaction Limits",
         "Default daily transaction limits apply to your account type. Limits can be revised "
         "through the mobile app or by visiting your nearest branch."),
        ("5. Interest &amp; Charges",
         "Interest rates and service charges are subject to change as per RBI guidelines and "
         "bank policy. You will be notified of any changes via registered email or SMS."),
        ("6. Dispute Resolution",
         f"Any dispute must be reported within 30 days of the transaction date. Contact our "
         f"grievance officer at {BANK_EMAIL} or call {BANK_PHONE}."),
        ("7. Governing Law",
         "These terms are governed by the laws of India. Any disputes shall be subject to the "
         "exclusive jurisdiction of courts in Mumbai, Maharashtra."),
        ("8. Amendments",
         f"{BANK_NAME} reserves the right to amend these terms at any time. Continued use of "
         "the account constitutes acceptance of the revised terms."),
    ]
    for title, body in clauses:
        elems.append(Paragraph(title, st["section"]))
        elems.append(Paragraph(body, st["body"]))
        elems.append(Spacer(1, 2 * mm))
    elems += _footer_text(st)
    return elems


def _section_to_bytes(story: list) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20*mm, rightMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)
    doc.build(story)
    return buf.getvalue()


def generate_welcome_kit(customer: CustomerInfo, kyc: KycResult) -> str:
    st = _styles()
    sections = [
        _build_cover(customer, kyc, st),
        _build_account_summary(customer, st),
        _build_kyc_result(customer, kyc, st),
        _build_terms(st),
    ]
    writer = PdfWriter()
    for story in sections:
        pdf_bytes = _section_to_bytes(story)
        reader = PdfReader(BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)
    date_str = datetime.today().strftime("%Y%m%d")
    safe_id  = customer.account_opening_id.replace("/", "-").replace("\\", "-")
    filepath = os.path.join(OUTPUT_DIR, f"WelcomeKit_{safe_id}_{date_str}.pdf")
    with open(filepath, "wb") as f:
        writer.write(f)
    print(f"[WelcomeKit] Saved → {filepath}")
    return filepath


def customer_from_request(req_dict: dict, account_opening_id: str = "") -> CustomerInfo:
    return CustomerInfo(
        account_opening_id = account_opening_id or req_dict.get("accountOpeningId", ""),
        first_name         = req_dict.get("firstName", ""),
        last_name          = req_dict.get("lastName", ""),
        aadhaar_number     = req_dict.get("aadhaarNumber", ""),
        pan_number         = req_dict.get("panNumber", ""),
        date_of_birth      = req_dict.get("dateOfBirth", ""),
        mobile             = req_dict.get("mobile", ""),
        email              = req_dict.get("email", ""),
        pincode            = req_dict.get("pincode", ""),
        occupation         = req_dict.get("occupation", "unknown"),
        income             = req_dict.get("income", 0),
        deposit_amount     = req_dict.get("depositAmount", 0),
    )


if __name__ == "__main__":
    sample_customer = CustomerInfo(
        account_opening_id = "ACC-2024-001",
        first_name         = "Rajesh",
        last_name          = "Kumar",
        aadhaar_number     = "234567890123",
        pan_number         = "ABCDE1234F",
        date_of_birth      = "1990-05-15",
        mobile             = "9876543210",
        email              = "rajesh.kumar@example.com",
        pincode            = "400001",
        occupation         = "Salaried",
        income             = 600000,
        deposit_amount     = 50000,
    )
    sample_kyc = KycResult(
        verified             = True,
        aml_clean            = True,
        risk_score           = 0.21,
        status               = "APPROVED",
        remarks              = "Low risk applicant",
        age                  = 35,
        deposit_income_ratio = 0.08,
    )
    path = generate_welcome_kit(sample_customer, sample_kyc)
    print(f"Done! Open: {path}")