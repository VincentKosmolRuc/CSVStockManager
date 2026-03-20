import io
import streamlit as st
import pandas as pd


st.set_page_config(page_title="Shipment Extractor", layout="wide")

st.title("CSV Shipment Extractor")
st.write(
    "Upload one or more CSV files. The app extracts `ProductName`, `ProductCode` and "
    "`QuantityShipped`, then exports mapped columns: `reference` and `antal`."
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

    for uploaded_file in uploaded_files:
        try:
            df, encoding_used = read_csv_flexible(uploaded_file)

            required_columns = {"ProductName", "ProductCode", "QuantityShipped"}
            missing = required_columns - set(df.columns)
            if missing:
                st.warning(
                    f"`{uploaded_file.name}` skipped. Missing column(s): {', '.join(sorted(missing))}"
                )
                continue

            extracted = df[["ProductName", "ProductCode", "QuantityShipped"]].copy()
            extracted.columns = ["product_name", "product_code", "quantity_shipped"]
            extracted["product_name"] = extracted["product_name"].astype(str).str.strip()
            extracted["product_code"] = extracted["product_code"].astype(str).str.strip()
            extracted["quantity_shipped"] = pd.to_numeric(
                extracted["quantity_shipped"], errors="coerce"
            ).fillna(0)

            extracted_parts.append(extracted)
        except Exception as err:
            st.error(f"Error reading `{uploaded_file.name}`: {err}")

    if extracted_parts:
        result_df = pd.concat(extracted_parts, ignore_index=True)
        result_df = result_df[result_df["product_code"] != ""]
        grouped_df = result_df.groupby("product_code", as_index=False).agg(
            product_name=("product_name", "first"),
            quantity_shipped=("quantity_shipped", "sum"),
        )
        grouped_df = grouped_df.sort_values("product_code").reset_index(drop=True)

        st.caption("Skriv nuvaerende antal paa lager, hvis det er over 0.")
        stock_input_df = grouped_df.copy()
        stock_input_df["current_stock"] = 0

        edited_df = st.data_editor(
            stock_input_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "product_name": st.column_config.TextColumn("ProductName", disabled=True),
                "product_code": st.column_config.TextColumn("ProductCode", disabled=True),
                "quantity_shipped": st.column_config.NumberColumn(
                    "QuantityShipped", disabled=True, step=1
                ),
                "current_stock": st.column_config.NumberColumn(
                    "current stock", min_value=0, step=1
                ),
            },
            disabled=["product_name", "product_code", "quantity_shipped"],
        )

        edited_df["current_stock"] = pd.to_numeric(
            edited_df["current_stock"], errors="coerce"
        ).fillna(0)
        edited_df["final_stock"] = edited_df["current_stock"] + edited_df["quantity_shipped"]

        export_df = edited_df[["product_code", "final_stock"]].copy()
        export_df.columns = ["reference", "antal"]

        csv_data = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download final stock CSV",
            data=csv_data,
            file_name="prestashop_stock_update.csv",
            mime="text/csv",
        )
    else:
        st.info(
            "No valid rows extracted. Check that your CSV files contain "
            "`ProductName`, `ProductCode` and `QuantityShipped`."
        )
else:
    st.info("Upload one or more CSV files to begin.")
