import io
import os
import streamlit as st
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STOCK_CSV = os.path.join(SCRIPT_DIR, "FFV12Marts.csv")

st.set_page_config(page_title="Shipment Extractor", layout="wide")

st.title("CSV Shipment Extractor")
st.write(
    "Upload en eller flere forsendelses-CSV'er. Du kan uploade en shop-eksport (fx FFV12Marts.csv) "
    "med kolonnerne Reference og Antal, så 'current stock' udfyldes automatisk for matchende varenumre."
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


def parse_int_like(value):
    text = str(value).strip()
    if text in ("", "-", "+"):
        return 0
    return int(float(text))


def load_stock_map_reference_to_antal(source):
    """Build product reference -> stock from FFV12Marts-style CSV (semicolon; columns Reference, Antal)."""
    if isinstance(source, str):
        with open(source, "rb") as f:
            raw = f.read()
    else:
        raw = source.getvalue()
    last_err = None
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = raw.decode(encoding)
            df = pd.read_csv(io.StringIO(text), sep=";", dtype=str)
            break
        except Exception as e:
            last_err = e
            continue
    else:
        raise ValueError(last_err or "Could not decode stock catalog")

    if "Reference" not in df.columns or "Antal" not in df.columns:
        raise ValueError("Forventede kolonnerne Reference og Antal (fx FFV12Marts.csv).")

    df = df[["Reference", "Antal"]].copy()
    df["Reference"] = df["Reference"].astype(str).str.strip()
    df["Antal"] = pd.to_numeric(df["Antal"], errors="coerce").fillna(0)
    df = df[df["Reference"] != ""]
    df = df.drop_duplicates(subset="Reference", keep="last")
    return df.set_index("Reference")["Antal"].astype("int64").to_dict()


stock_catalog_file = st.file_uploader(
    "Shop-lager CSV (valgfri, fx FFV12Marts.csv)",
    type=["csv"],
    accept_multiple_files=False,
    key="stock_catalog_uploader",
)
use_local_ffv = st.checkbox(
    f"Brug FFV12Marts.csv fra app-mappen",
    value=os.path.isfile(DEFAULT_STOCK_CSV),
    disabled=not os.path.isfile(DEFAULT_STOCK_CSV),
    help=f"Søger efter: {DEFAULT_STOCK_CSV}",
)

stock_map = {}
stock_source_label = None
try:
    if stock_catalog_file is not None:
        stock_map = load_stock_map_reference_to_antal(stock_catalog_file)
        stock_source_label = stock_catalog_file.name
    elif use_local_ffv:
        stock_map = load_stock_map_reference_to_antal(DEFAULT_STOCK_CSV)
        stock_source_label = "FFV12Marts.csv"
except Exception as err:
    st.warning(f"Kunne ikke læse lagercatalog: {err}")

uploaded_files = st.file_uploader(
    "Upload CSV file(s)",
    type=["csv"],
    accept_multiple_files=True,
)

if uploaded_files:
    extracted_parts = []
    shipment_sig = tuple((f.name, f.size) for f in uploaded_files)
    if stock_catalog_file is not None:
        stock_sig = ("upload", stock_catalog_file.name, stock_catalog_file.size)
    elif use_local_ffv and os.path.isfile(DEFAULT_STOCK_CSV):
        stock_sig = ("local", os.path.getmtime(DEFAULT_STOCK_CSV))
    else:
        stock_sig = ("none",)
    upload_signature = (shipment_sig, stock_sig)

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

        if stock_source_label:
            st.caption(
                f"Nuværende lager er hentet fra **{stock_source_label}** (Reference → Antal). "
                "Ret i tabellen ved behov."
            )
        else:
            st.caption("Skriv nuværende antal på lager ind i 'current stock' kolonnen.")
        if (
            "stock_table_df" not in st.session_state
            or st.session_state.get("upload_signature") != upload_signature
        ):
            stock_input_df = grouped_df.copy()
            if stock_map:
                stock_input_df["current_stock"] = stock_input_df["product_code"].map(
                    lambda c: str(stock_map.get(str(c).strip(), 0))
                )
            else:
                stock_input_df["current_stock"] = "0"
            st.session_state["stock_table_df"] = stock_input_df
            st.session_state["upload_signature"] = upload_signature

        edited_df = st.data_editor(
            st.session_state["stock_table_df"],
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

        st.session_state["stock_table_df"] = edited_df.copy()

        try:
            edited_df["current_stock"] = edited_df["current_stock"].apply(parse_int_like).astype("int64")
        except ValueError:
            st.error("`current stock` must be a whole number, e.g. -8, 0, 12.")
            st.stop()

        edited_df["final_stock"] = (
            edited_df["current_stock"] + edited_df["quantity_shipped"]
        ).astype("int64")

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
