## Setup

pip install -r requirements.txt

## Run

uvicorn main:app --reload --port 5000


## Endpoints

### `GET /health`

```json
{ "status": "healthy", "model_loaded": true }
```



### `POST /kyc/verify`
Run KYC verification and AML risk scoring on an applicant.


**Example request:**
```json
{
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
```

**Response:**

| Field             | Type    | Description                                      |
|-------------------|---------|--------------------------------------------------|
| `accountOpeningId`| string  | Echoed back from request                         |
| `verified`        | boolean | Whether identity passed hard validation          |
| `amlClean`        | boolean | Whether applicant passed AML checks              |
| `riskScore`       | float   | ML-predicted risk score (0.0 = low, 1.0 = high) |
| `status`          | string  | `APPROVED` / `REVIEW` / `REJECTED`               |
| `remarks`         | string  | Human-readable reason                            |
| `derived`         | object  | `{ age, depositIncomeRatio }` (when computed)    |

**Status thresholds:**
- `APPROVED` — `riskScore < 0.35`
- `REVIEW`   — `0.35 ≤ riskScore < 0.70`
- `REJECTED` — `riskScore ≥ 0.70` or hard validation failure

**Example response:**
```json
{
  "accountOpeningId": "ACC-2024-001",
  "verified": true,
  "amlClean": true,
  "riskScore": 0.21,
  "status": "APPROVED",
  "remarks": "Low risk applicant",
  "derived": {
    "age": 35,
    "depositIncomeRatio": 0.08
  }
}


##train the Model


cd training/
python training.py


The new `model.pkl` will be picked up automatically on the next server start.

## Welcome kit will automatically generated and saved in the welcome_kits folder upon executing /kyc/verify