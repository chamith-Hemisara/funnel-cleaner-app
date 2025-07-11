import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Funnel Cleaner App", layout="wide")
st.title("📂 Funnel Data Cleaner")

# Upload CSV
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    # Standardize column names
    df.columns = [col.strip() for col in df.columns]

    # Required columns
    required_cols = ['REF No', 'Task Name', 'User', 'Task Created Date', 'RSM', 'BDM']
    for col in required_cols:
        if col not in df.columns:
            st.error(f"Missing required column: {col}")
            st.stop()

    # Ensure datetime format
    df['Task Created Date'] = pd.to_datetime(df['Task Created Date'], errors='coerce')

    # Helper: clean strings
    def clean(val):
        return str(val).strip().lower() if pd.notna(val) else ""

    # Reset Sales BDO
    df['Sales BDO'] = pd.NA

    # Step 1: Assign Sales BDO
    def assign_sales_bdo(group):
        rsm = clean(group['RSM'].iloc[0])
        bdm = clean(group['BDM'].iloc[0])
        bdo = None

        # Check Contact Customer - DS BDO
        cc_rows = group[
            group['Task Name'].str.startswith("Contact Customer - DS BDO", na=False) &
            group['User'].notna()
        ].sort_values('Task Created Date')

        for user in cc_rows['User']:
            if clean(user) not in {rsm, bdm}:
                bdo = user
                break

        # If still not found, try Site Visit
        if not bdo:
            site_rows = group[
                group['Task Name'].str.lower() == 'site visit'
            ].sort_values('Task Created Date')

            for user in site_rows['User']:
                if clean(user) not in {rsm, bdm}:
                    bdo = user
                    break

        group['Sales BDO'] = bdo if bdo else pd.NA
        return group

    df = df.groupby('REF No', group_keys=False).apply(assign_sales_bdo)

    # Step 2: Final cleanup — remove if Sales BDO == RSM or BDM
    def final_clean(row):
        bdo = clean(row['Sales BDO'])
        rsm = clean(row['RSM'])
        bdm = clean(row['BDM'])

        if bdo and (bdo == rsm or bdo == bdm):
            return pd.NA
        return row['Sales BDO']

    df['Sales BDO'] = df.apply(final_clean, axis=1)

    # Optional: Add flag for visibility
    df['BDO Valid?'] = df['Sales BDO'].apply(
        lambda x: '✅ OK' if pd.notna(x) else '❌ Removed or Empty'
    )

    # Show final data
    st.subheader("✅ Final Cleaned Data")
    st.dataframe(df)

    # Download cleaned CSV
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        "📥 Download Cleaned CSV",
        csv,
        file_name="final_cleaned_funnel_data.csv",
        mime="text/csv"
    )

    # Show invalids (optional)
    st.subheader("❌ Rows with Empty or Removed BDO")
    st.dataframe(df[df['BDO Valid?'] == '❌ Removed or Empty'][['REF No', 'RSM', 'BDM', 'Sales BDO']])
