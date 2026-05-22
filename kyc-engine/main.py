import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime
import re
import joblib
import os

from welcome_kit import generate_welcome_kit, CustomerInfo, KycResult as WelcomeKycResult

app = FastAPI(
    title="KYC Risk Engine",
    description="KYC verification and AML risk scoring API for banking onboarding",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_BASE = os.path.dirname(os.path.abspath(__file__))
model = joblib.load(os.path.join(_BASE, "training", "model.pkl"))


class KycRequest(BaseModel):
    accountOpeningId: str = Field(default="")
    aadhaarNumber: str    = Field(...)
    panNumber: str        = Field(...)
    firstName: str        = Field(...)
    lastName: str         = Field(...)
    dateOfBirth: str      = Field(...)
    income: int           = Field(..., gt=0)
    depositAmount: int    = Field(..., ge=0)
    mobile: str           = Field(default="")
    email: str            = Field(default="")
    pincode: str          = Field(default="")
    occupation: str       = Field(default="unknown")

    class Config:
        json_schema_extra = {
            "example": {
                "accountOpeningId": "ACC-2024-001",
                "aadhaarNumber": "234567890123",
                "panNumber": "ABCDE1234F",
                "firstName": "Rajesh",
                "lastName": "Kumar",
                "dateOfBirth": "1990-05-15",
                "income": 600000,
                "depositAmount": 50000,
                "mobile": "9876543210",
                "email": "rajesh.kumar@example.com",
                "pincode": "400001",
                "occupation": "salaried"
            }
        }


class DerivedInfo(BaseModel):
    age: int
    depositIncomeRatio: float


class KycResponse(BaseModel):
    accountOpeningId: str
    verified: bool
    amlClean: bool
    riskScore: float
    status: str
    remarks: str
    welcomeKitPath: str | None = None
    derived: DerivedInfo | None = None


PAN_REGEX = r"^[A-Z]{5}[0-9]{4}[A-Z]$"

def calc_age(dob: str) -> int:
    for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]:
        try:
            d = datetime.strptime(dob, fmt).date()
            today = datetime.today().date()
            return today.year - d.year - ((today.month, today.day) < (d.month, d.day))
        except ValueError:
            pass
    return -1

def valid_pan(pan: str) -> bool:
    return bool(re.match(PAN_REGEX, pan.strip().upper()))

def valid_aadhaar(a: str) -> bool:
    return a.isdigit() and len(a) == 12

def email_valid(email: str) -> bool:
    if not email:
        return True
    return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", email))

def mobile_valid(mobile: str) -> bool:
    if not mobile:
        return True
    return mobile.isdigit() and len(mobile) == 10 and mobile[0] in "6789"

def pincode_risk(pin: str) -> int:
    if not pin:
        return 0
    return 1 if pin.startswith(("90", "91", "92")) else 0

def occupation_risk(occ: str) -> int:
    risky = {"cash", "broker", "unknown"}
    return 1 if occ.lower().strip() in risky else 0

def deposit_income_ratio(income: int, deposit: int) -> float:
    if income <= 0:
        return 999.0
    return round(deposit / income, 2)

def _reject(account_id: str, remarks: str, score: float = 1.00) -> KycResponse:
    return KycResponse(accountOpeningId=account_id, verified=False, amlClean=False,
                       riskScore=score, status="REJECTED", remarks=remarks)

def _review(account_id: str, remarks: str, score: float = 0.95) -> KycResponse:
    return KycResponse(accountOpeningId=account_id, verified=False, amlClean=False,
                       riskScore=score, status="REVIEW", remarks=remarks)

def _make_welcome_kit(data: KycRequest, age: int, ratio: float,
                      prob: float, status: str, remarks: str) -> str | None:
    try:
        customer = CustomerInfo(
            account_opening_id = data.accountOpeningId,
            first_name         = data.firstName,
            last_name          = data.lastName,
            aadhaar_number     = data.aadhaarNumber,
            pan_number         = data.panNumber,
            date_of_birth      = data.dateOfBirth,
            mobile             = data.mobile,
            email              = data.email,
            pincode            = data.pincode,
            occupation         = data.occupation,
            income             = data.income,
            deposit_amount     = data.depositAmount,
        )
        kyc_result = WelcomeKycResult(
            verified             = True,
            aml_clean            = (status != "REJECTED"),
            risk_score           = prob,
            status               = status,
            remarks              = remarks,
            age                  = age,
            deposit_income_ratio = ratio,
        )
        return generate_welcome_kit(customer, kyc_result)
    except Exception as e:
        print(f"[WelcomeKit] Failed to generate: {e}")
        return None


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "KYC Risk Engine", "version": "1.0.0"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy", "model_loaded": model is not None}


@app.post("/kyc/verify", response_model=KycResponse, tags=["KYC"])
def verify(data: KycRequest):
    aid = data.accountOpeningId

    age = calc_age(data.dateOfBirth)
    if age < 0:
        raise HTTPException(status_code=422, detail="Unparseable dateOfBirth. Use YYYY-MM-DD, DD-MM-YYYY, or DD/MM/YYYY.")
    if age < 18:
        return _reject(aid, "Applicant must be 18+")

    if not valid_aadhaar(data.aadhaarNumber):
        return _reject(aid, "Invalid Aadhaar number — must be exactly 12 digits")

    if not valid_pan(data.panNumber):
        return _reject(aid, "Invalid PAN number — expected format ABCDE1234F")

    if data.income <= 0:
        return _reject(aid, "Income must be greater than zero")

    if data.depositAmount < 0:
        return _reject(aid, "Deposit amount cannot be negative")

    if not email_valid(data.email):
        return _review(aid, "Invalid email format", score=0.95)

    if not mobile_valid(data.mobile):
        return _review(aid, "Invalid mobile number", score=0.95)

    ratio = deposit_income_ratio(data.income, data.depositAmount)

    if ratio > 10:
        kit_path = _make_welcome_kit(data, age, ratio, 0.98, "REVIEW",
                                     "Deposit unusually high compared to income — AML flag")
        return KycResponse(
            accountOpeningId=aid, verified=True, amlClean=False,
            riskScore=0.98, status="REVIEW",
            remarks="Deposit unusually high compared to income — AML flag",
            welcomeKitPath=kit_path,
            derived=DerivedInfo(age=age, depositIncomeRatio=ratio),
        )

    manual_ratio_flag = 1 if ratio > 5 else 0
    name_match = 1 if len(data.firstName.strip()) >= 2 and len(data.lastName.strip()) >= 2 else 0

    features = pd.DataFrame([{
        "age":            age,
        "income":         data.income,
        "pincodeRisk":    pincode_risk(data.pincode),
        "duplicatePan":   0,
        "nameMatch":      name_match,
        "occupationRisk": occupation_risk(data.occupation),
    }])

    prob = float(model.predict_proba(features)[0][1])

    if manual_ratio_flag:
        prob = min(1.0, prob + 0.15)

    prob = round(prob, 2)

    if prob < 0.35:
        status, remarks = "APPROVED", "Low risk applicant"
    elif prob < 0.70:
        status, remarks = "REVIEW",   "Manual review recommended"
    else:
        status, remarks = "REJECTED", "High risk applicant"

    kit_path = _make_welcome_kit(data, age, ratio, prob, status, remarks)

    return KycResponse(
        accountOpeningId=aid,
        verified=True,
        amlClean=(status != "REJECTED"),
        riskScore=prob,
        status=status,
        remarks=remarks,
        welcomeKitPath=kit_path,
        derived=DerivedInfo(age=age, depositIncomeRatio=ratio),
    )