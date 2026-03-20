import io
import streamlit as st
import pandas as pd

st.set_page_config(page_title="Shipment Extractor", layout="wide")

st.title("CSV Shipment Extractor")
st.write(
    "Upload en eller flere CSV filer. Søg produkterne i shoppen via d-nummer og skriv nuværende antal ind i 'current stock' kolonnen."
)


def read_csv_flexible(uploaded_file):
    raw = uploaded_file.getvalue()
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = raw.decode(encoding)
            return pd.read_csv(io.StringIO(text), sep=None, engine="python"), encoding
        except Exception:
            continue
    raise ValueError(f"Could not read file: {uploaded_file.name}")


def parse_int_like(value):
    text = str(value).strip()
    if text in ("", "-", "+"):
        return 0
    return int(float(text))


uploaded_files = st.file_uploader(
    "Upload CSV file(s)",
    type=["csv"],
    accept_multiple_files=True,
)

if uploaded_files:
    extracted_parts = []
    upload_signature = tuple((f.name, f.size) for f in uploaded_files)

    for uploaded_file in uploaded_files:
        try:
            df, _ = read_csv_flexible(uploaded_file)

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
        grouped_df["quantity_shipped"] = (
            pd.to_numeric(grouped_df["quantity_shipped"], errors="coerce")
            .fillna(0)
            .round()
            .astype("int64")
        )

        st.caption("Skriv nuværende antal på lager ind i 'current stock' kolonnen.")

        # ✅ Initialize ONLY when files change
        if (
            "upload_signature" not in st.session_state
            or st.session_state["upload_signature"] != upload_signature
        ):
            grouped_df["current_stock"] = "0"
            st.session_state["stock_data"] = grouped_df.copy()
            st.session_state["upload_signature"] = upload_signature

        # ✅ Render editor and capture output safely
        edited_df = st.data_editor(
            st.session_state["stock_data"],
            key="stock_editor",
            use_container_width=True,
            hide_index=True,
            column_config={
                "product_name": st.column_config.TextColumn("ProductName", disabled=True),
                "product_code": st.column_config.TextColumn("ProductCode", disabled=True),
                "quantity_shipped": st.column_config.NumberColumn(
                    "QuantityShipped", disabled=True, step=1, format="%d"
                ),
                "current_stock": st.column_config.TextColumn("current stock"),
            },
            disabled=["product_name", "product_code", "quantity_shipped"],
        )

        # ✅ Only update if valid DataFrame (prevents crash)
        if isinstance(edited_df, pd.DataFrame):
            st.session_state["stock_data"] = edited_df.copy()

        # Always read from session state (single source of truth)
        edited_df = st.session_state["stock_data"].copy()

        # Parse input
        try:
            edited_df["current_stock"] = (
                edited_df["current_stock"].apply(parse_int_like).astype("int64")
            )
        except ValueError:
            st.error("`current stock` must be a whole number, e.g. -8, 0, 12.")
            st.stop()

        # Calculate final stock
        edited_df["final_stock"] = (
            edited_df["current_stock"] + edited_df["quantity_shipped"]
        ).astype("int64")

        # Export
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
