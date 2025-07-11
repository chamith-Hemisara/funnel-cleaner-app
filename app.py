import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Funnel Cleaner App", layout="wide")
st.title("📂 Funnel Data Cleaner")

# Upload CSV
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    # Strip and lowercase column names
    df.columns = [col.strip() for col in df.columns]

    required_cols = ['REF No', 'Task Name', 'User', 'Task Created Date', 'RSM', 'BDM']
    for col in required_cols:
        if col not in df.columns:
            st.error(f"Missing required column: {col}")
            st.stop()

    # Helper: clean names for matching
    def clean(name):
        return str(name).strip().lower() if pd.notna(name) else ""

    # Ensure consistent types
    df['Task Created Date'] = pd.to_datetime(df['Task Created Date'], errors='coerce')
    df['Sales BDO'] = pd.NA  # reset

    def assign_sales_bdo(group):
        rsm = clean(group['RSM'].iloc[0])
        bdm = clean(group['BDM'].iloc[0])
        bdo = None

        # Step 1: Contact Customer - DS BDO
        contact = group[
            group['Task Name'].str.startswith("Contact Customer - DS BDO", na=False) &
            group['User'].notna()
        ].sort_values('Task Created Date')

        for user in contact['User']:
            if clean(user) not in {rsm, bdm}:
                bdo = user
                break

        # Step 2: Site Visit
        if not bdo:
            site_visit = group[
                (group['Task Name'].str.lower() == 'site visit') &
                group['User'].notna()
            ].sort_values('Task Created Date')

            for user in site_visit['User']:
                if clean(user) not in {rsm, bdm}:
                    bdo = user
                    break

        # Final check: remove if same as RSM or BDM
        if bdo and clean(bdo) in {rsm, bdm}:
            bdo = None

        group['Sales BDO'] = bdo if bdo else pd.NA
        return group

    df = df.groupby('REF No', group_keys=False).apply(assign_sales_bdo)

    # Validation
    def validate_bdo(row):
        bdo = clean(row['Sales BDO'])
        if not bdo:
            return '❌ Empty'
        if bdo == clean(row['RSM']) or bdo == clean(row['BDM']):
            return '❌ RSM or BDM used'
        return '✅ OK'

    df['BDO Valid?'] = df.apply(validate_bdo, axis=1)

    # Show
    st.subheader("✅ Cleaned Data")
    st.dataframe(df)

    # Download
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Cleaned CSV", csv, file_name="cleaned_funnel_data.csv")

    # Show invalids
    st.subheader("❌ Invalid BDO Entries")
    bad = df[df['BDO Valid?'] != '✅ OK'][['REF No', 'Sales BDO', 'RSM', 'BDM', 'BDO Valid?']]
    st.dataframe(bad)
