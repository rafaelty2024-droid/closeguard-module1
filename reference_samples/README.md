# Reference samples

This folder contains approved examples that guide Module 1 classification.

Place representative purchase orders in `purchase_orders/` and representative supplier, sales or tax invoices in `supplier_invoices/`.

Supported reference formats are PDF, JSON, PNG, JPG, JPEG, TIFF, BMP, WebP, HEIC, HEIF, DOCX and TXT. JSON is reference-only: JSON attachments received by email are not treated as submitted AP evidence.

For a PDF and its structured metadata, use the same stem:

```text
purchase_orders/supplier_a_po.pdf
purchase_orders/supplier_a_po.json
```

Use this JSON structure:

```json
{
  "document_type": "PURCHASE_ORDER",
  "field_values": {
    "supplier": "Example Supplier Pte. Ltd.",
    "document_number": "PO-1001",
    "document_date": "2026-10-09",
    "amount": 1526.0,
    "currency": "SGD"
  },
  "labels": {
    "supplier": ["Vendor Name"],
    "purchase_order_number": ["Buyer Order ID"],
    "amount": ["Approved Order Value"]
  },
  "keywords": ["approved order", "procurement"]
}
```

Valid `labels` keys are `document_type`, `supplier`, `invoice_number`, `purchase_order_number`, `po_reference`, `document_date`, `amount` and `currency`.

Guidelines:

- Use fictional, anonymised or approved documents only.
- Include several layouts from the suppliers that commonly submit evidence.
- Do not place receipts, statements or unrelated correspondence in these folders.
- Keep one clean example of each layout; technical duplicates add no value.
- Update `reference_labels.json` when a supplier uses a label not already listed, such as `Buyer Order ID` for the PO reference.
- Keep JSON metadata beside the correct PO or invoice folder. A conflicting `document_type` is rejected.

PDFs provide layout and visible vocabulary. JSON provides verified field names, alternative labels and optional keywords. The sample folders help identify document type and terminology only. They do not teach Module 1 whether a PO and invoice match; that remains Module 2's responsibility.
