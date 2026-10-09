from pathlib import Path

import pandas as pd
import streamlit as st

from module1_pipeline import (
    create_folders,
    download_email_attachments,
    process_attachments,
    export_results,
)


# Files created by Module 1
INTAKE_FILE = Path("output/intake_register.csv")
MODULE2_FILE = Path("output/module2_input.csv")
MODULE2_JSON_FILE = Path("output/module2_input.json")
REVIEW_FILE = Path("review/intake_review.csv")
UNSUPPORTED_FILE = Path("review/unsupported_documents.csv")


st.set_page_config(
    page_title="CloseGuard Module 1",
    page_icon="📄",
    layout="wide",
)

create_folders()


def load_csv(file_path):
    """Load a CSV safely if it exists."""
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
st.subheader("Document Intake and Validation")

st.write(
    "Module 1 receives documents from email, extracts and standardises "
    "their information, and registers the source evidence. Module 2 "
    "assesses matching, completeness and AP exceptions."
)

st.divider()

# Run Module 1
st.subheader("Check for new documents")

st.write(
    "Click the button to check the configured email inbox for unread "
    "PDF, CSV or Excel attachments."
)

if st.button(
    "Check email and process documents",
    type="primary",
):
    try:
        with st.spinner(
            "Checking email and processing attachments..."
        ):
            downloaded_files = download_email_attachments()

            if downloaded_files:
                records = process_attachments(downloaded_files)
                export_results(records)

                st.success(
                    f"Processing completed. "
                    f"{len(downloaded_files)} attachment(s) downloaded."
                )
            else:
                st.info(
                    "No new supported attachments were found. "
                    "Existing results were not changed."
                )

    except Exception as error:
        st.error(f"Module 1 could not complete: {error}")


# Load the latest output files
intake_data = load_csv(INTAKE_FILE)
module2_data = load_csv(MODULE2_FILE)
review_data = load_csv(REVIEW_FILE)
unsupported_data = load_csv(UNSUPPORTED_FILE)


# Count hand-off statuses
ready_count = 0
gaps_count = 0

if (
    not module2_data.empty
    and "processing_status" in module2_data.columns
):
    ready_count = (
        module2_data["processing_status"]
        == "READY_FOR_MODULE_2"
    ).sum()

    gaps_count = (
        module2_data["processing_status"]
        == "READY_WITH_GAPS"
    ).sum()


# Dashboard metrics
st.divider()
st.subheader("Module 1 intake summary")

column1, column2, column3, column4 = st.columns(4)

column1.metric(
    "Evidence received",
    len(intake_data),
)

column2.metric(
    "Complete extraction",
    int(ready_count),
)

column3.metric(
    "Passed with gaps",
    int(gaps_count),
)

column4.metric(
    "Needs intake review",
    len(review_data),
)


# Dashboard tabs
st.divider()

handoff_tab, review_tab, unsupported_tab, register_tab = st.tabs(
    [
        "Module 2 hand-off",
        "Intake review",
        "Unsupported documents",
        "Evidence register",
    ]
)


# Tab 1: Module 2 hand-off
with handoff_tab:
    st.subheader("Structured evidence for Module 2")

    st.write(
        "These documents were readable and successfully converted "
        "into structured records. A record may still contain missing "
        "business information. Module 2 will assess those gaps."
    )

    if module2_data.empty:
        st.info(
            "No records are currently available for Module 2."
        )
    else:
        status_filter = st.selectbox(
            "Filter by intake status",
            [
                "All",
                "READY_FOR_MODULE_2",
                "READY_WITH_GAPS",
            ],
        )

        if status_filter == "All":
            filtered_module2_data = module2_data
        else:
            filtered_module2_data = module2_data[
                module2_data["processing_status"]
                == status_filter
            ]

        st.dataframe(
            filtered_module2_data,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            label="Download Module 2 CSV",
            data=MODULE2_FILE.read_bytes(),
            file_name="module2_input.csv",
            mime="text/csv",
        )

        if MODULE2_JSON_FILE.exists():
            st.download_button(
                label="Download Module 2 JSON",
                data=MODULE2_JSON_FILE.read_bytes(),
                file_name="module2_input.json",
                mime="application/json",
            )


# Tab 2: Intake review
with review_tab:
    st.subheader("Correct unclear intake information")

    st.write(
        "These documents could not be classified or read reliably. "
        "They must be corrected or clarified and then processed "
        "through Module 1 again."
    )

    if review_data.empty:
        st.success(
            "There are currently no documents requiring "
            "intake review."
        )
    else:
        st.dataframe(
            review_data,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            label="Download intake-review queue",
            data=REVIEW_FILE.read_bytes(),
            file_name="intake_review.csv",
            mime="text/csv",
        )


# Tab 3: Unsupported documents
with unsupported_tab:
    st.subheader(
        "Readable documents outside the current scope"
    )

    st.write(
        "These documents were readable, but they are not currently "
        "supported purchase orders or supplier invoices. They remain "
        "registered and are not deleted."
    )

    if unsupported_data.empty:
        st.info(
            "No unsupported documents have been received."
        )
    else:
        st.dataframe(
            unsupported_data,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            label="Download unsupported-document register",
            data=UNSUPPORTED_FILE.read_bytes(),
            file_name="unsupported_documents.csv",
            mime="text/csv",
        )


# Tab 4: Complete intake register
with register_tab:
    st.subheader("Complete source-evidence register")

    st.write(
        "This register contains every document processed by Module 1, "
        "including records passed to Module 2, review items and "
        "unsupported documents."
    )

    if intake_data.empty:
        st.info(
            "No source evidence has been registered."
        )
    else:
        st.dataframe(
            intake_data,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            label="Download complete evidence register",
            data=INTAKE_FILE.read_bytes(),
            file_name="intake_register.csv",
            mime="text/csv",
        )


st.divider()

st.caption(
    "Module 1 prepares and registers evidence. It does not determine "
    "whether the AP case is complete, approve accounting treatment, "
    "or resolve an exception."
)