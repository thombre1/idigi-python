# OCR Module — API Contract
> Share this file with the Frontend and Java teams.

**Base URL:** `http://localhost:5000`  
**All responses:** JSON unless CSV format is requested.

---

## GET /ping
Health check. Call this to confirm the OCR service is running.

**Response:**
```json
{ "status": "ok", "service": "OCR Module", "version": "1.0" }
```

---

## POST /ocr/single
Process **one** document image. Used after the customer uploads a single file.

**Request** — `multipart/form-data`

| Field      | Type   | Required | Description |
|------------|--------|----------|-------------|
| `file`     | File   | ✅       | Image of the document (JPG / PNG / TIFF) |
| `doc_type` | String | ❌       | Hint: `aadhaar`, `pan`, `driving_licence`, `ration_card` |
| `format`   | String | ❌       | `json` (default) or `csv` |

**Success Response (200):**
```json
{
  "status": "success",
  "document_type": "aadhaar",
  "confidence": "high",
  "missing_fields": [],
  "fields": {
    "name": "Ramesh Kumar",
    "aadhaar_number": "123456789012",
    "date_of_birth": "01/01/1990",
    "gender": "Male",
    "address": "123 MG Road, Pune, Maharashtra 411001"
  },
  "kyc_payload": {
    "name": "Ramesh Kumar",
    "aadhaar_number": "123456789012",
    "date_of_birth": "01/01/1990",
    "gender": "Male",
    "address": "...",
    "documents_submitted": ["aadhaar"],
    "ocr_confidence": { "aadhaar": "high" },
    "name_consistent": true
  }
}
```

**Error Responses:**
| Code | Reason |
|------|--------|
| 400  | No file uploaded |
| 422  | File could not be opened as image |
| 500  | OCR processing failed |

---

## POST /ocr/batch
Process **multiple** documents at once. The `kyc_payload` merges all extracted fields.  
Call this when the customer submits all documents together (Step 4 in the project).

**Request** — `multipart/form-data`

| Field       | Type        | Required | Description |
|-------------|-------------|----------|-------------|
| `files[]`   | File (multi)| ✅       | Multiple document images |
| `doc_types` | String      | ❌       | Comma-separated hints: `"aadhaar,pan"` |

**Success Response (200):**
```json
{
  "status": "success",
  "total_documents": 2,
  "results": [
    {
      "filename": "aadhaar.jpg",
      "document_type": "aadhaar",
      "confidence": "high",
      "missing_fields": [],
      "fields": { "name": "Ramesh Kumar", "aadhaar_number": "123456789012", ... }
    },
    {
      "filename": "pan.jpg",
      "document_type": "pan",
      "confidence": "high",
      "missing_fields": [],
      "fields": { "name": "Ramesh Kumar", "pan_number": "ABCDE1234F", ... }
    }
  ],
  "kyc_payload": {
    "name": "Ramesh Kumar",
    "aadhaar_number": "123456789012",
    "pan_number": "ABCDE1234F",
    "date_of_birth": "01/01/1990",
    "documents_submitted": ["aadhaar", "pan"],
    "ocr_confidence": { "aadhaar": "high", "pan": "high" },
    "name_consistent": true
  }
}
```

---

## How the KYC payload is used downstream

```
Frontend  ──POST /ocr/batch──►  Python OCR  ──kyc_payload──►  Python KYC (Step 5)
                                                         └───►  Java CBS (Step 6)
```

The **Java module** should call `POST /ocr/batch` after the customer submits all documents,
then pass the returned `kyc_payload` JSON to its KYC verification service.

The **Frontend** can use the `confidence` and `missing_fields` fields to show the customer
which documents were read successfully and which may need to be re-uploaded.

---

## Confidence levels

| Level    | Meaning |
|----------|---------|
| `high`   | ≥75% of expected fields extracted. Safe to proceed. |
| `medium` | 50–74% extracted. Proceed with manual review flag. |
| `low`    | <50% extracted. Ask customer to re-upload the document. |
