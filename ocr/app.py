"""
app.py
------
Flask server exposing OCR endpoints.

Endpoints:
  POST /ocr/single    — process one document image
  POST /ocr/batch     — process multiple document images at once
  GET  /ping          — health check

Run with:
  pip install flask flask-cors pillow pytesseract
  python app.py
"""

import json
from flask import Flask, request, jsonify, render_template,send_file
from flask_cors import CORS
from PIL import Image
import io
import os

import pytesseract
import shutil



# This helps find where tesseract was installed in the Render environment
tesseract_path = shutil.which("tesseract")

if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
else:
    # Fallback/Default path if you installed it to a custom local bin
    pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"




from ocr_service import extract_document, to_json, to_csv, build_kyc_payload, pdf_to_images

app = Flask(__name__, template_folder='.')
CORS(app)   # Allow the Frontend (React) to call this server from a different port


# ──────────────────────────────────────────────
# HEALTH CHECK
# ──────────────────────────────────────────────

@app.route("/ping", methods=["GET"])
def ping():
    """Quick health check — Frontend and Java can call this to confirm server is up."""
    return jsonify({"status": "ok", "service": "OCR Module", "version": "1.0"})


# ──────────────────────────────────────────────
# SINGLE DOCUMENT
# ──────────────────────────────────────────────

@app.route("/ocr/single", methods=["POST"])
def ocr_single():
    """
    Process a single uploaded document image.

    Request (multipart form):
      - file: the image file (jpg/png/pdf)
      - doc_type (optional): 'aadhaar' | 'pan' | 'driving_licence' | 'ration_card'
      - format (optional): 'json' (default) | 'csv'

    Response (JSON):
      {
        "status": "success",
        "document_type": "aadhaar",
        "confidence": "high",
        "missing_fields": [],
        "fields": { "name": "...", "aadhaar_number": "...", ... },
        "kyc_payload": { ... }   ← ready for KYC module
      }
    """
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded. Send a file with key 'file'."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"status": "error", "message": "Empty filename."}), 400

    doc_type_hint = request.form.get("doc_type", None)
    output_format = request.form.get("format", "json").lower()

    # ── PDF or Image? ───────────────────────────────────────
    filename_lower = file.filename.lower()
    is_pdf = filename_lower.endswith(".pdf")

    try:
        if is_pdf:
            pdf_bytes = file.stream.read()
            images = pdf_to_images(pdf_bytes)
            # For single-document PDFs (KYC docs) use page 1 only
            image = images[0]
        else:
            image = Image.open(file.stream)
    except RuntimeError as e:
        # pdf2image/poppler not installed
        return jsonify({"status": "error", "message": str(e)}), 501
    except Exception:
        return jsonify({
            "status": "error",
            "message": "Could not open file. Supported formats: JPG, PNG, TIFF, PDF"
        }), 422

    try:
        result = extract_document(image, doc_type_hint)
    except Exception as e:
        return jsonify({"status": "error", "message": f"OCR processing failed: {str(e)}"}), 500

    # CSV download
    if output_format == "csv":
        csv_data = to_csv(result)
        buf = io.BytesIO(csv_data.encode("utf-8"))
        buf.seek(0)
        return send_file(buf, mimetype="text/csv", as_attachment=True,
                         download_name=f"{result['document_type']}_ocr.csv")

    # Default: JSON response
    kyc_payload = build_kyc_payload([result])
    response = {
        "status": "success",
        "document_type": result["document_type"],
        "confidence": result["confidence"],
        "missing_fields": result["missing_fields"],
        "fields": result["fields"],
        "kyc_payload": kyc_payload,
    }
    return jsonify(response), 200


# ──────────────────────────────────────────────
# BATCH — multiple documents in one request
# ──────────────────────────────────────────────

@app.route("/ocr/batch", methods=["POST"])
def ocr_batch():
    """
    Process multiple document images in one request.
    Merges all results into a single KYC payload.

    Request (multipart form):
      - files[]: multiple image files
      - doc_types (optional): comma-separated list matching file order
                              e.g. "aadhaar,pan,driving_licence"

    Response (JSON):
      {
        "status": "success",
        "results": [ { per-document result }, ... ],
        "kyc_payload": { merged fields from all docs, ready for KYC module }
      }
    """
    files = request.files.getlist("files[]")
    if not files:
        return jsonify({"status": "error", "message": "No files uploaded. Use key 'files[]'."}), 400

    doc_types_raw = request.form.get("doc_types", "")
    doc_types = [d.strip() or None for d in doc_types_raw.split(",")]

    all_results = []
    per_doc = []

    for i, file in enumerate(files):
        doc_type_hint = doc_types[i] if i < len(doc_types) else None
        try:
            fname_lower = file.filename.lower()
            if fname_lower.endswith(".pdf"):
                pdf_bytes = file.stream.read()
                images = pdf_to_images(pdf_bytes)
                image = images[0]
            else:
                image = Image.open(file.stream)
            result = extract_document(image, doc_type_hint)
        except Exception as e:
            result = {
                "document_type": doc_type_hint or "unknown",
                "error": str(e),
                "fields": {},
                "confidence": "low",
                "missing_fields": [],
            }

        all_results.append(result)
        per_doc.append({
            "filename": file.filename,
            "document_type": result["document_type"],
            "confidence": result["confidence"],
            "missing_fields": result.get("missing_fields", []),
            "fields": result.get("fields", {}),
            "error": result.get("error"),
        })

    # Merge into one KYC payload
    kyc_payload = build_kyc_payload(all_results)

    return jsonify({
        "status": "success",
        "total_documents": len(files),
        "results": per_doc,
        "kyc_payload": kyc_payload,
    }), 200


# ──────────────────────────────────────────────
# RUN
# ──────────────────────────────────────────────
@app.route('/')
def home():
    # Looks for index.html in the 'templates' folder
    return render_template('test_ui.html')


if __name__ == "__main__":
    print("=" * 50)
    print("  OCR Service running at http://localhost:5000")
    print("  Endpoints:")
    print("    GET  /ping")
    print("    POST /ocr/single")
    print("    POST /ocr/batch")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)
