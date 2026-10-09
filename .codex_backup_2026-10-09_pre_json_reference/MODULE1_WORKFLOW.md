# CloseGuard Module 1 workflow

## Purpose

Module 1 creates reliable, traceable and standardised evidence for Module 2. It does not perform PO-to-invoice matching, determine AP case completeness, detect business-level duplicate invoices, approve accounting treatment or resolve exceptions.

## OCR setup

RapidOCR and ONNX Runtime are included in `requirements.txt`. They run locally inside the project's Python virtual environment, so no separate desktop application, cloud OCR service or LLM is required. The dashboard's **Supported files and reference guide** panel shows `RAPIDOCR_ONNX` when the engine is ready.

The first OCR run can take longer while the local models initialise. If the Python OCR packages are unavailable, Module 1 continues processing digital PDFs, CSV, XLSX, DOCX and TXT files. Photographs and image-only PDFs are safely routed to intake review instead of being treated as valid blank documents.

## Updated process

1. **Receive unread email**
   - Select messages whose subject contains the configured filter.
   - Accept PDF, PNG, JPG, JPEG, TIFF, BMP, WebP, HEIC, HEIF, CSV, XLSX, DOCX and TXT attachments up to the configured size limit.

2. **Filter exact duplicate attachments**
   - Calculate a SHA-256 hash before saving the attachment.
   - Filter an identical file even if its filename or email is different.
   - Record the event in `review/duplicate_attachments.csv`.

3. **Extract text or table data**
   - Use direct extraction for digital PDFs, spreadsheets, DOCX and TXT.
   - Use OCR for photographs and image-only PDFs.
   - Record whether OCR was used.

4. **Filter content-equivalent copies**
   - Create a fingerprint from normalised full document text or canonical table content.
   - Filter a re-saved or rewrapped copy only when its full extracted content matches.
   - Do not filter records merely because invoice number, supplier and amount match; business duplicate assessment belongs to Module 2.

5. **Classify the evidence**
   - First use an explicit document-type label.
   - Then use a strong title pattern.
   - Finally compare the document's vocabulary with approved files in `reference_samples/`.
   - Uncertain classifications go to intake review.

6. **Extract and standardise fields**
   - Supplier
   - Document number
   - PO reference
   - Document date
   - Amount
   - Currency
   - Add supplier-specific labels to `reference_samples/reference_labels.json`.

7. **Apply the Module 1 routing decision**
   - `READY_FOR_MODULE_2`: readable supported evidence with all expected fields.
   - `READY_WITH_GAPS`: readable supported evidence with missing business fields.
   - `INTAKE_REVIEW`: readable but not reliably classified, or a processing error occurred.
   - `UNREADABLE_DOCUMENT`: no usable text was recovered.
   - `UNSUPPORTED_DOCUMENT`: readable evidence outside the PO and supplier-invoice scope.

8. **Create outputs**
   - Complete evidence register
   - Module 2 CSV and JSON hand-off
   - Intake-review queue
   - Unsupported-document register
   - Duplicate-attachment audit log

## Operational improvements already integrated

- Paths resolve relative to the project instead of the terminal's current folder.
- Attachment filenames include a hash prefix, preventing accidental overwrites.
- Exact duplicates are detected within one email and across different emails.
- Content-equivalent re-saved copies are filtered separately from business duplicates.
- OCR, classification method, matched sample and file type are recorded for traceability.
- Reference samples and label aliases can be updated without changing Python code.

## Recommended next controls

- Add unit tests for every common supplier layout before deployment.
- Review and approve changes to the reference sample library.
- Monitor OCR confidence and require review below an agreed threshold.
- Restrict mailbox access to a dedicated read-only intake account where possible.
- Apply retention rules to source attachments and audit registers.
- Add a controlled retry queue instead of manually editing failed records.
