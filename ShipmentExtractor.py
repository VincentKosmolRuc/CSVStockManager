with st.form("stock_form"):
    edited_df = st.data_editor(
        st.session_state["stock_data"],
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

    submit_and_download = st.form_submit_button("Download final stock CSV")

# ✅ When user clicks button → apply edits FIRST
if submit_and_download and isinstance(edited_df, pd.DataFrame):
    st.session_state["stock_data"] = edited_df.copy()

    df = st.session_state["stock_data"].copy()

    # Parse input
    try:
        df["current_stock"] = (
            df["current_stock"].apply(parse_int_like).astype("int64")
        )
    except ValueError:
        st.error("`current stock` must be a whole number, e.g. -8, 0, 12.")
        st.stop()

    # Calculate final stock
    df["final_stock"] = (
        df["current_stock"] + df["quantity_shipped"]
    ).astype("int64")

    export_df = df[["product_code", "final_stock"]].copy()
    export_df.columns = ["reference", "antal"]

    csv_data = export_df.to_csv(index=False).encode("utf-8")

    # ✅ Trigger actual download AFTER processing
    st.download_button(
        label="Click to download",
        data=csv_data,
        file_name="prestashop_stock_update.csv",
        mime="text/csv",
    )
