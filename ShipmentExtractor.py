import io
import streamlit as st
import pandas as pd


st.set_page_config(page_title="Shipment Extractor", layout="wide")

st.title("CSV Shipment Extractor")
st.write(
    "Upload one or more CSV files. The app extracts `reference` as product code and "
    "`antal` as quantity shipped, then lets you download the result."
)


def read_csv_flexible(uploaded_file):
    """Read CSV with robust delimiter and encoding handling."""
    raw = uploaded_file.getvalue()
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = raw.decode(encoding)
            return pd.read_csv(io.StringIO(text), sep=None, engine="python"), encoding
        except Exception:
            continue
    raise ValueError(f"Could not read file: {uploaded_file.name}")


uploaded_files = st.file_uploader(
    "Upload CSV file(s)",
    type=["csv"],
    accept_multiple_files=True,
)

if uploaded_files:
    extracted_parts = []
    file_summaries = []

    for uploaded_file in uploaded_files:
        try:
            df, encoding_used = read_csv_flexible(uploaded_file)

            required_columns = {"reference", "antal"}
            missing = required_columns - set(df.columns)
            if missing:
                st.warning(
                    f"`{uploaded_file.name}` skipped. Missing column(s): {', '.join(sorted(missing))}"
                )
                continue

            extracted = df[["reference", "antal"]].copy()
            extracted.columns = ["product_code", "quantity_shipped"]
            extracted["product_code"] = extracted["product_code"].astype(str).str.strip()
            extracted["quantity_shipped"] = pd.to_numeric(extracted["quantity_shipped"], errors="coerce").fillna(0)

            extracted_parts.append(extracted)
            file_summaries.append(
                {
                    "file": uploaded_file.name,
                    "rows_extracted": len(extracted),
                    "encoding": encoding_used,
                }
            )
        except Exception as err:
            st.error(f"Error reading `{uploaded_file.name}`: {err}")

    if extracted_parts:
        result_df = pd.concat(extracted_parts, ignore_index=True)
        result_df = result_df[result_df["product_code"] != ""]
        grouped_df = (
            result_df.groupby("product_code", as_index=False)["quantity_shipped"]
            .sum()
            .sort_values("product_code")
            .reset_index(drop=True)
        )

        st.subheader("Shipped Quantity Per Product")
        st.dataframe(grouped_df, use_container_width=True)

        st.subheader("File Summary")
        st.dataframe(pd.DataFrame(file_summaries), use_container_width=True)

        st.subheader("Current Stock Input")
        stock_input_df = grouped_df.copy()
        stock_input_df["current_stock"] = 0
        stock_input_df["new_stock"] = stock_input_df["quantity_shipped"]

        edited_df = st.data_editor(
            stock_input_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "product_code": st.column_config.TextColumn("Product code", disabled=True),
                "quantity_shipped": st.column_config.NumberColumn("Shipped quantity", disabled=True, step=1),
                "current_stock": st.column_config.NumberColumn("Current stock", min_value=0, step=1),
                "new_stock": st.column_config.NumberColumn("New stock", disabled=True, step=1),
            },
            disabled=["product_code", "quantity_shipped", "new_stock"],
        )

        edited_df["current_stock"] = pd.to_numeric(edited_df["current_stock"], errors="coerce").fillna(0)
        edited_df["new_stock"] = edited_df["current_stock"] + edited_df["quantity_shipped"]

        st.subheader("Final Export Preview")
        export_df = edited_df[["product_code", "new_stock"]].copy()
        st.dataframe(export_df, use_container_width=True)

        csv_data = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download final stock CSV",
            data=csv_data,
            file_name="prestashop_stock_update.csv",
            mime="text/csv",
        )
    else:
        st.info("No valid rows extracted. Check that your CSV files contain `reference` and `antal`.")
else:
    st.info("Upload one or more CSV files to begin.")
