import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Funnel Cleaner App", layout="wide")
st.title("📂 Funnel Data Cleaner")

# Upload CSV
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    # Clean up possible date fields
    for col in df.columns:
        if "Date" in col:
            try:
                df[col] = pd.to_datetime(df[col])
            except:
                pass

    # --- Helper to normalize names ---
    def clean_user(val):
        return str(val).strip().lower() if pd.notna(val) else ""

    # --- Reset Sales BDO before reassigning ---
    df['Sales BDO'] = pd.NA

    # --- Assign Sales BDO ---
    def assign_sales_bdo(group):
        rsm = clean_user(group['RSM'].iloc[0]) if 'RSM' in group.columns else ""
        bdm = clean_user(group['BDM'].iloc[0]) if 'BDM' in group.columns else ""
        bdo_user = None

        # First: Contact Customer - DS BDO
        bdo_tasks = group[
            group['Task Name'].str.startswith("Contact Customer - DS BDO", na=False) &
            group['User'].notna()
        ]
        if not bdo_tasks.empty:
            candidate = bdo_tasks.sort_values('Task Created Date').iloc[-1]['User']
            if clean_user(candidate) not in {rsm, bdm}:
                bdo_user = candidate

        # Second: Site Visit
        if not bdo_user:
            site_visit = group[group['Task Name'] == 'Site Visit']
            if not site_visit.empty:
                candidate = site_visit.iloc[0]['User']
                if clean_user(candidate) not in {rsm, bdm}:
                    bdo_user = candidate

        if bdo_user:
            group['Sales BDO'] = bdo_user

        return group

    df = df.groupby('REF No', group_keys=False).apply(assign_sales_bdo)

    # Final Check: Clear if BDO = RSM or BDM
    def clear_if_invalid(row):
        bdo = clean_user(row['Sales BDO'])
        rsm = clean_user(row.get('RSM'))
        bdm = clean_user(row.get('BDM'))
        return pd.NA if bdo in {rsm, bdm} else row['Sales BDO']

    df['Sales BDO'] = df.apply(clear_if_invalid, axis=1)

    # Optional: Add a check column
    df['BDO Valid?'] = df.apply(
        lambda r: '✅ OK' if pd.notna(r['Sales BDO']) else '❌ Cleared (RSM/BDM match)',
        axis=1
    )

    # Show cleaned results
    st.subheader("Cleaned Data Preview")
    st.dataframe(df)

    # Download button
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Cleaned CSV",
        data=csv,
        file_name="cleaned_funnel.csv",
        mime='text/csv'
    )

    # Optional debug
    st.subheader("❌ Rows Where BDO Was Cleared")
    st.dataframe(df[df['BDO Valid?'] == '❌ Cleared (RSM/BDM match)'][['REF No', 'Sales BDO', 'RSM', 'BDM']])
