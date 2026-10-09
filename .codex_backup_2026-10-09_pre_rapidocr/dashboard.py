import pandas as pd
import streamlit as st

from module1_pipeline import (
    DUPLICATE_FILE,
    INTAKE_FILE,
    MODULE2_FILE,
    MODULE2_JSON_FILE,
    REVIEW_FILE,
    UNSUPPORTED_FILE,
    create_folders,
    download_email_attachments,
    export_results,
    get_reference_summary,
    process_attachments,
)


st.set_page_config(page_title="CloseGuard Module 1", page_icon="📄", layout="wide")
create_folders()


def load_csv(file_path):
    if not file_path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(file_path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    except Exception as error:
        st.error(f"Could not read {file_path.name}: {error}")
        return pd.DataFrame()


st.title("CloseGuard Module 1")
st.subheader("Document Intake, OCR and Standardisation")
st.write(
    "Module 1 receives evidence, filters duplicate attachments, extracts text, "
    "classifies the document and creates a traceable structured hand-off. "
    "Module 2 remains responsible for matching, completeness and AP exceptions."
)

reference_summary = get_reference_summary()
with st.expander("Supported files and reference guide", expanded=False):
    st.write(
        "Supported formats: "
        + ", ".join(reference_summary["supported_extensions"])
    )
    st.write(
        f"Reference samples loaded: {reference_summary['purchase_orders']} purchase order(s) "
        f"and {reference_summary['supplier_invoices']} supplier invoice(s)."
    )
    if reference_summary["ocr_available"]:
        st.success("OCR is available for photographs and image-only PDFs.")
    else:
        st.warning(
            "OCR is not currently available. Digital PDFs, spreadsheets, DOCX and TXT can "
            "still be processed, but photographs and image-only PDFs will require intake review."
        )

st.divider()
st.subheader("Check for new documents")
st.write(
    "Checks unread matching emails for unique PDF, image, CSV, Excel, DOCX and TXT attachments."
)

if st.button("Check email and process documents", type="primary"):
    try:
        with st.spinner("Checking email, filtering duplicates and processing attachments..."):
            downloaded_files = download_email_attachments()
            if downloaded_files:
                records = process_attachments(downloaded_files)
                export_results(records)
                st.success(
                    f"Completed. {len(downloaded_files)} unique attachment(s) downloaded; "
                    f"{len(records)} structured record(s) created."
                )
            else:
                st.info(
                    "No new unique supported attachments were found. Exact duplicates, if any, "
                    "were filtered and recorded."
                )
    except Exception as error:
        st.error(f"Module 1 could not complete: {error}")

intake_data = load_csv(INTAKE_FILE)
module2_data = load_csv(MODULE2_FILE)
review_data = load_csv(REVIEW_FILE)
unsupported_data = load_csv(UNSUPPORTED_FILE)
duplicate_data = load_csv(DUPLICATE_FILE)

ready_count = 0
gaps_count = 0
if not module2_data.empty and "processing_status" in module2_data.columns:
    ready_count = (module2_data["processing_status"] == "READY_FOR_MODULE_2").sum()
    gaps_count = (module2_data["processing_status"] == "READY_WITH_GAPS").sum()

st.divider()
st.subheader("Module 1 intake summary")
column1, column2, column3, column4, column5 = st.columns(5)
column1.metric("Evidence received", len(intake_data))
column2.metric("Complete extraction", int(ready_count))
column3.metric("Passed with gaps", int(gaps_count))
column4.metric("Needs intake review", len(review_data))
column5.metric("Duplicates filtered", len(duplicate_data))

st.divider()
handoff_tab, review_tab, unsupported_tab, duplicate_tab, register_tab = st.tabs(
    [
        "Module 2 hand-off",
        "Intake review",
        "Unsupported documents",
        "Filtered duplicates",
        "Evidence register",
    ]
)

with handoff_tab:
    st.subheader("Structured evidence for Module 2")
    st.write(
        "Readable PO and supplier-invoice evidence is passed forward. Missing business fields "
        "remain visible for Module 2 to assess."
    )
    if module2_data.empty:
        st.info("No records are currently available for Module 2.")
    else:
        status_filter = st.selectbox(
            "Filter by intake status", ["All", "READY_FOR_MODULE_2", "READY_WITH_GAPS"]
        )
        filtered = module2_data if status_filter == "All" else module2_data[
            module2_data["processing_status"] == status_filter
        ]
        st.dataframe(filtered, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Module 2 CSV",
            MODULE2_FILE.read_bytes(),
            "module2_input.csv",
            "text/csv",
        )
        if MODULE2_JSON_FILE.exists():
            st.download_button(
                "Download Module 2 JSON",
                MODULE2_JSON_FILE.read_bytes(),
                "module2_input.json",
                "application/json",
            )

with review_tab:
    st.subheader("Correct unclear intake information")
    st.write(
        "These files could not be read or classified reliably. Correct them or verify OCR, "
        "then process them again through Module 1."
    )
    if review_data.empty:
        st.success("There are currently no documents requiring intake review.")
    else:
        st.dataframe(review_data, use_container_width=True, hide_index=True)
        st.download_button(
            "Download intake-review queue", REVIEW_FILE.read_bytes(), "intake_review.csv", "text/csv"
        )

with unsupported_tab:
    st.subheader("Readable documents outside the current scope")
    st.write(
        "These files were readable but are not purchase orders or supplier invoices. "
        "They remain registered and are not passed to Module 2."
    )
    if unsupported_data.empty:
        st.info("No unsupported documents have been received.")
    else:
        st.dataframe(unsupported_data, use_container_width=True, hide_index=True)
        st.download_button(
            "Download unsupported-document register",
            UNSUPPORTED_FILE.read_bytes(),
            "unsupported_documents.csv",
            "text/csv",
        )

with duplicate_tab:
    st.subheader("Attachments filtered before Module 2")
    st.write(
        "Exact file duplicates and content-equivalent copies are removed regardless of filename "
        "or email. This is technical deduplication only; business-level duplicate invoices are "
        "still assessed by Module 2."
    )
    if duplicate_data.empty:
        st.success("No duplicate attachments have been filtered.")
    else:
        st.dataframe(duplicate_data, use_container_width=True, hide_index=True)
        st.download_button(
            "Download duplicate log",
            DUPLICATE_FILE.read_bytes(),
            "duplicate_attachments.csv",
            "text/csv",
        )

with register_tab:
    st.subheader("Complete source-evidence register")
    st.write(
        "Every unique document processed by Module 1 is retained here with its source hash, "
        "extraction method, OCR flag and classification basis."
    )
    if intake_data.empty:
        st.info("No source evidence has been registered.")
    else:
        st.dataframe(intake_data, use_container_width=True, hide_index=True)
        st.download_button(
            "Download complete evidence register",
            INTAKE_FILE.read_bytes(),
            "intake_register.csv",
            "text/csv",
        )

st.divider()
st.caption(
    "Module 1 prepares, validates and registers evidence. It does not match a PO to an invoice, "
    "determine case completeness, approve accounting treatment or resolve an AP exception."
)
