import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Funnel Cleaner App", layout="wide")
st.title("📂 Funnel Data Cleaner")

# Upload CSV
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    # Normalize column names just in case
    df.columns = [col.strip() for col in df.columns]

    # Ensure relevant columns exist
    for col in ['REF No', 'Task Name', 'User', 'Task Created Date', 'RSM', 'BDM']:
        if col not in df.columns:
            st.error(f"Missing required column: {col}")
            st.stop()

    # Normalize names for comparison
    def clean_name(name):
        return str(name).strip().lower() if pd.notna(name) else ""

    # Reset Sales BDO before reassigning
    df['Sales BDO'] = pd.NA

    # Assign Sales BDO per REF No group
    def assign_sales_bdo(group):
        rsm = clean_name(group['RSM'].iloc[0])
        bdm = clean_name(group['BDM'].iloc[0])
        bdo = None

        # Step 1: Contact Customer - DS BDO
        contact_rows = group[
            group['Task Name'].str.startswith("Contact Customer - DS BDO", na=False) &
            group['User'].notna()
        ]
        if not contact_rows.empty:
            candidate = contact_rows.sort_values('Task Created Date').iloc[-1]['User']
            if clean_name(candidate) not in {rsm, bdm}:
                bdo = candidate

        # Step 2: Site Visit
        if not bdo:
            site_rows = group[
                (group['Task Name'].str.lower() == 'site visit') &
                group['User'].notna()
            ]
            if not site_rows.empty:
                candidate = site_rows.sort_values('Task Created Date').iloc[0]['User']
                if clean_name(candidate) not in {rsm, bdm}:
                    bdo = candidate

        # Step 3: Final Safety Check — do not assign if BDO matches RSM/BDM
        if bdo and clean_name(bdo) not in {rsm, bdm}:
            group['Sales BDO'] = bdo
        else:
            group['Sales BDO'] = pd.NA

        return group

    df = df.groupby('REF No', group_keys=False).apply(assign_sales_bdo)

    # Final Validation Column (Optional)
    df['BDO Valid?'] = df.apply(
        lambda r: '✅ OK' if pd.notna(r['Sales BDO']) else '❌ Empty or Invalid',
        axis=1
    )

    # Show data
    st.subheader("✅ Cleaned Data Preview")
    st.dataframe(df)

    # Download cleaned CSV
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        "📥 Download Cleaned CSV",
        csv,
        file_name="cleaned_funnel_data.csv",
        mime="text/csv"
    )
