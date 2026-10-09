from pathlib import Path
from email import message_from_bytes
from email.header import decode_header
import hashlib
import imaplib
import os
import re

import pandas as pd
import pdfplumber
from dotenv import load_dotenv


# Reload values from .env whenever the application starts.
load_dotenv(override=True)


# -------------------------------------------------------------------
# Folder and file configuration
# -------------------------------------------------------------------

INPUT_FOLDER = Path("input")
OUTPUT_FOLDER = Path("output")
REVIEW_FOLDER = Path("review")

HASH_FILE = Path("processed_hashes.txt")

INTAKE_FILE = OUTPUT_FOLDER / "intake_register.csv"
MODULE2_FILE = OUTPUT_FOLDER / "module2_input.csv"
MODULE2_JSON_FILE = OUTPUT_FOLDER / "module2_input.json"
REVIEW_FILE = REVIEW_FOLDER / "intake_review.csv"
UNSUPPORTED_FILE = REVIEW_FOLDER / "unsupported_documents.csv"

SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".csv",
    ".xlsx",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


STANDARD_COLUMNS = [
    "record_id",
    "document_type",
    "supplier",
    "document_number",
    "po_reference",
    "document_date",
    "amount",
    "currency",
    "source_file",
    "source_hash",
    "source_row",
    "email_id",
    "processing_status",
    "missing_fields",
    "intake_note",
]


# -------------------------------------------------------------------
# General helper functions
# -------------------------------------------------------------------

def create_folders():
    """Create folders used by Module 1."""
    INPUT_FOLDER.mkdir(exist_ok=True)
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    REVIEW_FOLDER.mkdir(exist_ok=True)


def decode_email_text(value):
    """Decode an email subject or attachment filename."""
    if not value:
        return ""

    output = []

    for part, encoding in decode_header(value):
        if isinstance(part, bytes):
            output.append(
                part.decode(
                    encoding or "utf-8",
                    errors="replace",
                )
            )
        else:
            output.append(part)

    return "".join(output)


def safe_filename(filename):
    """Remove unsafe characters from an attachment filename."""
    filename = Path(filename).name

    return re.sub(
        r"[^A-Za-z0-9._-]",
        "_",
        filename,
    )


def calculate_hash(content):
    """Create a fingerprint for a file."""
    return hashlib.sha256(content).hexdigest()


def load_processed_hashes():
    """Load fingerprints of attachments already downloaded."""
    if not HASH_FILE.exists():
        return set()

    return set(
        line.strip()
        for line in HASH_FILE.read_text().splitlines()
        if line.strip()
    )


def save_processed_hash(hash_value):
    """Save one processed attachment fingerprint."""
    with HASH_FILE.open("a", encoding="utf-8") as file:
        file.write(hash_value + "\n")


def create_record_id(
    source_hash,
    source_row=None,
    document_number=None,
):
    """Create a stable ID for one extracted record."""
    identity = (
        f"{source_hash}|"
        f"{source_row or 1}|"
        f"{document_number or ''}"
    )

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:16]


# -------------------------------------------------------------------
# Email intake
# -------------------------------------------------------------------

def download_email_attachments():
    """
    Download supported attachments from unread emails.

    The email subject must contain the value configured in
    EMAIL_SUBJECT_FILTER.
    """
    create_folders()

    email_host = os.getenv("EMAIL_HOST")
    email_address = os.getenv("EMAIL_ADDRESS")
    email_password = os.getenv("EMAIL_PASSWORD")
    subject_filter = os.getenv(
        "EMAIL_SUBJECT_FILTER",
        "",
    ).strip()

    if not email_host:
        raise ValueError(
            "EMAIL_HOST is missing from the .env file."
        )

    if not email_address:
        raise ValueError(
            "EMAIL_ADDRESS is missing from the .env file."
        )

    if not email_password:
        raise ValueError(
            "EMAIL_PASSWORD is missing from the .env file."
        )

    processed_hashes = load_processed_hashes()
    downloaded_files = []

    mailbox = None

    try:
        mailbox = imaplib.IMAP4_SSL(email_host)
        mailbox.login(email_address, email_password)
        mailbox.select("INBOX")

        status, message_numbers = mailbox.search(
            None,
            "UNSEEN",
        )

        if status != "OK":
            raise RuntimeError(
                "The inbox could not be searched."
            )

        for message_number in message_numbers[0].split():
            status, message_data = mailbox.fetch(
                message_number,
                "(RFC822)",
            )

            if status != "OK":
                continue

            raw_message = message_data[0][1]
            message = message_from_bytes(raw_message)

            subject = decode_email_text(
                message.get("Subject")
            )

            if (
                subject_filter
                and subject_filter.upper()
                not in subject.upper()
            ):
                continue

            email_id = message_number.decode()
            attachment_saved = False

            for part in message.walk():
                original_filename = part.get_filename()

                if not original_filename:
                    continue

                filename = safe_filename(
                    decode_email_text(
                        original_filename
                    )
                )

                extension = Path(filename).suffix.lower()

                if extension not in SUPPORTED_EXTENSIONS:
                    continue

                content = part.get_payload(decode=True)

                if not content:
                    continue

                if len(content) > MAX_FILE_SIZE:
                    continue

                source_hash = calculate_hash(content)

                if source_hash in processed_hashes:
                    continue

                output_name = (
                    f"{email_id}_{filename}"
                )

                output_path = (
                    INPUT_FOLDER / output_name
                )

                output_path.write_bytes(content)

                downloaded_files.append(
                    {
                        "path": output_path,
                        "email_id": email_id,
                        "source_hash": source_hash,
                    }
                )

                save_processed_hash(source_hash)
                processed_hashes.add(source_hash)
                attachment_saved = True

            # Only mark the message as read if at least one
            # supported attachment was downloaded.
            if attachment_saved:
                mailbox.store(
                    message_number,
                    "+FLAGS",
                    "\\Seen",
                )

    finally:
        if mailbox is not None:
            try:
                mailbox.logout()
            except Exception:
                pass

    return downloaded_files


# -------------------------------------------------------------------
# PDF extraction
# -------------------------------------------------------------------

def extract_pdf_text(file_path):
    """Extract text from a text-based PDF."""
    pages = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            pages.append(
                page.extract_text() or ""
            )

    return "\n".join(pages).strip()


def find_first(patterns, text):
    """Return the first captured value found in the text."""
    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )

        if match:
            return match.group(1).strip()

    return None


def classify_document(text):
    """
    Identify the document type.

    This only classifies the evidence. It does not decide
    whether an AP case is complete.
    """
    type_match = re.search(
        r"^Document Type\s*[:\-]?\s*(.+)$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    if type_match:
        type_value = (
            type_match.group(1)
            .strip()
            .upper()
        )

        if "INVOICE" in type_value:
            return "SUPPLIER_INVOICE"

        if "PURCHASE ORDER" in type_value:
            return "PURCHASE_ORDER"

        if "RECEIPT" in type_value:
            return "RECEIPT"

        return "UNKNOWN"

    # Fallback for documents without a labelled
    # "Document Type" field.
    if re.search(
        r"\bPURCHASE\s+ORDER\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "PURCHASE_ORDER"

    if re.search(
        r"\b(?:TAX\s+)?INVOICE\b",
        text,
        flags=re.IGNORECASE,
    ):
        return "SUPPLIER_INVOICE"

    return "UNKNOWN"


def extract_pdf_fields(
    file_path,
    email_id,
    source_hash,
):
    """Extract structured fields from one PDF."""
    text = extract_pdf_text(file_path)
    document_type = classify_document(text)

    supplier = find_first(
        [
            r"^Supplier\s*[:\-]?\s+(.+)$",
            r"^Vendor\s*[:\-]?\s+(.+)$",
            r"^Issued By\s*[:\-]?\s+(.+)$",
            r"^From\s*[:\-]?\s+(.+)$",
        ],
        text,
    )

    document_number = find_first(
        [
            r"^Document Number\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
            r"^Invoice Number\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
            r"^Invoice No\.?\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
            r"^Invoice #\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
            r"^PO Number\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
            r"^PO No\.?\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
            r"^PO #\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
        ],
        text,
    )

    po_reference = find_first(
        [
            r"^PO Reference\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
            r"^Purchase Order Number\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
            r"^Purchase Order No\.?\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
            r"^PO Number\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
            r"^PO No\.?\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
            r"^PO #\s*[:\-]?\s+([A-Z0-9\-\/]+)$",
        ],
        text,
    )

    # For a PO, its document number is also its
    # reference for later matching.
    if (
        document_type == "PURCHASE_ORDER"
        and not po_reference
    ):
        po_reference = document_number

    document_date = find_first(
        [
            r"^Document Date\s*[:\-]?\s+(.+)$",
            r"^Invoice Date\s*[:\-]?\s+(.+)$",
            r"^Order Date\s*[:\-]?\s+(.+)$",
            r"^Date\s*[:\-]?\s+(.+)$",
        ],
        text,
    )

    amount_match = re.search(
        r"^(?:Amount|Total Amount|Invoice Total|"
        r"Order Total|Amount Due|Total)"
        r"\s*[:\-]?\s*"
        r"(SGD|USD|EUR|GBP|MYR)?"
        r"\s*\$?\s*"
        r"([\d,]+\.\d{2})$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    currency = None
    amount = None

    if amount_match:
        currency = amount_match.group(1)
        amount = amount_match.group(2)

    return {
        "document_type": document_type,
        "supplier": supplier,
        "document_number": document_number,
        "po_reference": po_reference,
        "document_date": document_date,
        "amount": amount,
        "currency": currency,
        "source_file": file_path.name,
        "source_hash": source_hash,
        "source_row": None,
        "email_id": email_id,
        "text_extracted": bool(text.strip()),
    }


# -------------------------------------------------------------------
# CSV and Excel extraction
# -------------------------------------------------------------------

def normalise_table_columns(dataframe):
    """Convert common column labels to the Module 1 schema."""
    aliases = {
        "type": "document_type",
        "document type": "document_type",
        "document_type": "document_type",

        "vendor": "supplier",
        "vendor name": "supplier",
        "vendor_name": "supplier",
        "supplier name": "supplier",
        "supplier_name": "supplier",
        "supplier": "supplier",

        "document number": "document_number",
        "document_number": "document_number",
        "invoice number": "document_number",
        "invoice_number": "document_number",
        "invoice no": "document_number",
        "invoice_no": "document_number",

        "po reference": "po_reference",
        "po_reference": "po_reference",
        "po number": "po_reference",
        "po_number": "po_reference",
        "po no": "po_reference",
        "po_no": "po_reference",

        "document date": "document_date",
        "document_date": "document_date",
        "invoice date": "document_date",
        "invoice_date": "document_date",
        "date": "document_date",

        "total": "amount",
        "total amount": "amount",
        "total_amount": "amount",
        "amount": "amount",

        "currency": "currency",
    }

    renamed_columns = {}

    for column in dataframe.columns:
        normalised_name = (
            str(column)
            .strip()
            .lower()
        )

        renamed_columns[column] = aliases.get(
            normalised_name,
            normalised_name.replace(" ", "_"),
        )

    return dataframe.rename(
        columns=renamed_columns
    )


def read_table(
    file_path,
    email_id,
    source_hash,
):
    """Read records from a CSV or Excel attachment."""
    extension = file_path.suffix.lower()

    if extension == ".csv":
        dataframe = pd.read_csv(file_path)
    else:
        dataframe = pd.read_excel(file_path)

    dataframe = normalise_table_columns(
        dataframe
    )

    records = []

    for index, row in dataframe.iterrows():
        record = row.to_dict()

        record["source_file"] = file_path.name
        record["source_hash"] = source_hash
        record["source_row"] = index + 2
        record["email_id"] = email_id
        record["text_extracted"] = True

        records.append(record)

    return records


# -------------------------------------------------------------------
# Standardisation
# -------------------------------------------------------------------

def standardise_text(value):
    """Standardise supplier and similar text values."""
    if pd.isna(value) or not str(value).strip():
        return None

    value = str(value).upper().strip()
    value = re.sub(r"[^\w\s]", "", value)
    value = re.sub(r"\s+", " ", value)

    return value


def standardise_reference(value):
    """Standardise PO, invoice, and document references."""
    if pd.isna(value) or not str(value).strip():
        return None

    return re.sub(
        r"[^A-Z0-9]",
        "",
        str(value).upper(),
    )


def standardise_date(value):
    """Convert a date into YYYY-MM-DD format."""
    if pd.isna(value) or not str(value).strip():
        return None

    parsed = pd.to_datetime(
        value,
        errors="coerce",
        dayfirst=True,
    )

    if pd.isna(parsed):
        return None

    return parsed.strftime("%Y-%m-%d")


def standardise_amount(value):
    """Convert a monetary value into a number."""
    if pd.isna(value) or not str(value).strip():
        return None

    cleaned = re.sub(
        r"[^\d.\-]",
        "",
        str(value),
    )

    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def standardise_currency(value):
    """Standardise a currency code."""
    if pd.isna(value) or not str(value).strip():
        return None

    return str(value).upper().strip()


def normalise_document_type(value):
    """Convert document-type descriptions into fixed categories."""
    if pd.isna(value) or not str(value).strip():
        return "UNKNOWN"

    value = str(value).upper().strip()

    if "INVOICE" in value:
        return "SUPPLIER_INVOICE"

    if (
        "PURCHASE ORDER" in value
        or value in {"PO", "PURCHASE_ORDER"}
    ):
        return "PURCHASE_ORDER"

    if "RECEIPT" in value:
        return "RECEIPT"

    return "UNKNOWN"


# -------------------------------------------------------------------
# Intake validation and hand-off decision
# -------------------------------------------------------------------

def clean_record(record):
    """
    Prepare a record for Module 2.

    Module 1 decides only whether the document was technically
    readable and could be represented as structured evidence.

    It does not decide whether the AP case is complete.
    """
    document_type = normalise_document_type(
        record.get("document_type")
    )

    supplier = standardise_text(
        record.get("supplier")
    )

    document_number = standardise_reference(
        record.get("document_number")
    )

    po_reference = standardise_reference(
        record.get("po_reference")
    )

    document_date = standardise_date(
        record.get("document_date")
    )

    amount = standardise_amount(
        record.get("amount")
    )

    currency = standardise_currency(
        record.get("currency")
    )

    source_hash = record.get("source_hash")
    source_row = record.get("source_row")

    record_id = create_record_id(
        source_hash=source_hash,
        source_row=source_row,
        document_number=document_number,
    )

    cleaned = {
        "record_id": record_id,
        "document_type": document_type,
        "supplier": supplier,
        "document_number": document_number,
        "po_reference": po_reference,
        "document_date": document_date,
        "amount": amount,
        "currency": currency,
        "source_file": record.get("source_file"),
        "source_hash": source_hash,
        "source_row": source_row,
        "email_id": record.get("email_id"),
    }

    supported_types = {
        "PURCHASE_ORDER",
        "SUPPLIER_INVOICE",
    }

    fields_to_check = [
        "supplier",
        "document_number",
        "document_date",
        "amount",
        "currency",
    ]

    # A missing PO reference is passed to Module 2 as a gap.
    if document_type == "SUPPLIER_INVOICE":
        fields_to_check.append("po_reference")

    missing_fields = [
        field
        for field in fields_to_check
        if cleaned.get(field) is None
    ]

    text_extracted = record.get(
        "text_extracted",
        True,
    )

    if not text_extracted:
        processing_status = "UNREADABLE_DOCUMENT"

        intake_note = (
            "No usable text was extracted. "
            "Correct the document or use OCR, then recheck."
        )

    elif document_type == "UNKNOWN":
        processing_status = "INTAKE_REVIEW"

        intake_note = (
            "The document type could not be determined. "
            "A reviewer must classify or clarify it."
        )

    elif document_type not in supported_types:
        processing_status = "UNSUPPORTED_DOCUMENT"

        intake_note = (
            f"{document_type} is readable but outside "
            "the current PO and supplier-invoice scope."
        )

    elif missing_fields:
        processing_status = "READY_WITH_GAPS"

        intake_note = (
            "The document was readable and standardised. "
            "Module 2 must assess the missing information."
        )

    else:
        processing_status = "READY_FOR_MODULE_2"

        intake_note = (
            "The document was extracted and "
            "standardised successfully."
        )

    cleaned["processing_status"] = processing_status
    cleaned["missing_fields"] = ", ".join(
        missing_fields
    )
    cleaned["intake_note"] = intake_note

    return cleaned


# -------------------------------------------------------------------
# Process downloaded attachments
# -------------------------------------------------------------------

def process_attachments(downloaded_files):
    """Process attachments downloaded from email."""
    records = []

    for item in downloaded_files:
        file_path = Path(item["path"])
        email_id = item["email_id"]
        source_hash = item.get("source_hash")

        if not source_hash:
            source_hash = calculate_hash(
                file_path.read_bytes()
            )

        try:
            if file_path.suffix.lower() == ".pdf":
                raw_records = [
                    extract_pdf_fields(
                        file_path=file_path,
                        email_id=email_id,
                        source_hash=source_hash,
                    )
                ]

            elif file_path.suffix.lower() in {
                ".csv",
                ".xlsx",
            }:
                raw_records = read_table(
                    file_path=file_path,
                    email_id=email_id,
                    source_hash=source_hash,
                )

            else:
                continue

            for raw_record in raw_records:
                records.append(
                    clean_record(raw_record)
                )

        except Exception as error:
            record_id = create_record_id(
                source_hash=source_hash,
                source_row=None,
                document_number=None,
            )

            records.append(
                {
                    "record_id": record_id,
                    "document_type": "UNKNOWN",
                    "supplier": None,
                    "document_number": None,
                    "po_reference": None,
                    "document_date": None,
                    "amount": None,
                    "currency": None,
                    "source_file": file_path.name,
                    "source_hash": source_hash,
                    "source_row": None,
                    "email_id": email_id,
                    "processing_status": "INTAKE_REVIEW",
                    "missing_fields": (
                        "document_type, supplier, "
                        "document_number, document_date, "
                        "amount, currency"
                    ),
                    "intake_note": (
                        f"Processing error: {error}"
                    ),
                }
            )

    return records


# -------------------------------------------------------------------
# Export and Module 2 hand-off
# -------------------------------------------------------------------

def ensure_standard_columns(dataframe):
    """Ensure that every expected output column exists."""
    for column in STANDARD_COLUMNS:
        if column not in dataframe.columns:
            dataframe[column] = None

    return dataframe[STANDARD_COLUMNS]


def export_results(records):
    """
    Update the evidence register and generate hand-off files.

    Existing records are preserved. Reprocessing the same source
    replaces its earlier record using record_id.
    """
    create_folders()

    new_data = pd.DataFrame(
        records,
        columns=STANDARD_COLUMNS,
    )

    if INTAKE_FILE.exists():
        try:
            existing_data = pd.read_csv(
                INTAKE_FILE
            )
        except pd.errors.EmptyDataError:
            existing_data = pd.DataFrame(
                columns=STANDARD_COLUMNS
            )
    else:
        existing_data = pd.DataFrame(
            columns=STANDARD_COLUMNS
        )

    existing_data = ensure_standard_columns(
        existing_data
    )

    new_data = ensure_standard_columns(
        new_data
    )

    all_data = pd.concat(
        [
            existing_data,
            new_data,
        ],
        ignore_index=True,
    )

    all_data = all_data.drop_duplicates(
        subset=["record_id"],
        keep="last",
    )

    all_data = ensure_standard_columns(
        all_data
    )

    module2_data = all_data[
        all_data["processing_status"].isin(
            [
                "READY_FOR_MODULE_2",
                "READY_WITH_GAPS",
            ]
        )
    ]

    intake_review = all_data[
        all_data["processing_status"].isin(
            [
                "INTAKE_REVIEW",
                "UNREADABLE_DOCUMENT",
            ]
        )
    ]

    unsupported_data = all_data[
        all_data["processing_status"]
        == "UNSUPPORTED_DOCUMENT"
    ]

    # Complete source-evidence register
    all_data.to_csv(
        INTAKE_FILE,
        index=False,
    )

    # Records that Module 2 can assess
    module2_data.to_csv(
        MODULE2_FILE,
        index=False,
    )

    module2_data.to_json(
        MODULE2_JSON_FILE,
        orient="records",
        indent=2,
    )

    # Documents requiring correction and recheck
    intake_review.to_csv(
        REVIEW_FILE,
        index=False,
    )

    # Readable but currently out-of-scope documents
    unsupported_data.to_csv(
        UNSUPPORTED_FILE,
        index=False,
    )

    ready_count = (
        all_data["processing_status"]
        == "READY_FOR_MODULE_2"
    ).sum()

    gaps_count = (
        all_data["processing_status"]
        == "READY_WITH_GAPS"
    ).sum()

    print(f"Evidence received: {len(all_data)}")
    print(
        f"Complete extraction: {ready_count}"
    )
    print(
        f"Passed with gaps: {gaps_count}"
    )
    print(
        f"Needs intake review: {len(intake_review)}"
    )
    print(
        f"Unsupported documents: "
        f"{len(unsupported_data)}"
    )


# -------------------------------------------------------------------
# Run Module 1 without the dashboard
# -------------------------------------------------------------------

def main():
    create_folders()

    print("Checking the email inbox...")

    downloaded_files = (
        download_email_attachments()
    )

    print(
        f"Downloaded attachments: "
        f"{len(downloaded_files)}"
    )

    if not downloaded_files:
        print(
            "No new supported attachments were found."
        )
        return

    records = process_attachments(
        downloaded_files
    )

    export_results(records)


if __name__ == "__main__":
    main()