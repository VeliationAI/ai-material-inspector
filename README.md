# AI Material Inspector

Computer vision + OCR material quality inspection for Telangana utility store receipts (TISC Challenge 11).

**Pilot SKU:** porcelain electrical insulators (11 kV / 33 kV)  
**SAP for v1:** sample purchase orders (no live SAP API)  
**Client:** web app with camera / file upload

## Demo credentials

- Email: `officer@tgspdcl.example`
- Password: `ChangeMeNow!23`

## Local run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open http://127.0.0.1:8080

## What the MVP does

1. Store officer selects a sample SAP PO
2. Uploads insulator photos (or uses generated demo images)
3. Enters measured creepage / height / diameter
4. OpenCV flags crack/chip-like anomalies; RapidOCR reads markings
5. Rules engine compares results to PO specs
6. Officer approves/rejects; PDF report downloads

Final acceptance always stays with the human officer.

## Deploy

Docker image binds to `$PORT` for Render. See `Dockerfile` and `scripts/start.sh`.
