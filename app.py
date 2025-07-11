import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Funnel Cleaner App", layout="wide")
st.title("📂 Funnel Data Cleaner")

# Upload CSV
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    # --- Clean up dates ---
    for col in df.columns:
        if "Date" in col:
            try:
                df[col] = pd.to_datetime(df[col])
            except:
                pass

    # --- Clean user string for comparison ---
    def clean_user(val):
        return str(val).strip().lower() if pd.notna(val) else None

    # --- STEP 1: Reset Sales BDO ---
    df['Sales BDO'] = pd.NA

    # --- STEP 2: Assign Sales BDO safely ---
    def assign_sales_bdo(group):
        rsm_clean = clean_user(group['RSM'].iloc[0]) if 'RSM' in group.columns else None
        bdm_clean = clean_user(group['BDM'].iloc[0]) if 'BDM' in group.columns else None

        user_to_assign = None

        # Try Contact Customer - DS BDO
        bdo_tasks = group[
            group['Task Name'].str.startswith('Contact Customer - DS BDO', na=False) & group['User'].notna()
        ]
        if not bdo_tasks.empty:
            candidate_user = bdo_tasks.sort_values('Task Created Date').iloc[-1]['User']
            if clean_user(candidate_user) not in {rsm_clean, bdm_clean}:
                user_to_assign = candidate_user

        # Fallback: Site Visit
        if not user_to_assign:
            site_visits = group[group['Task Name'] == 'Site Visit']
            if not site_visits.empty:
                candidate_user = site_visits.iloc[0]['User']
                if clean_user(candidate_user) not in {rsm_clean, bdm_clean}:
                    user_to_assign = candidate_user

        # Assign if valid
        if user_to_assign:
            group['Sales BDO'] = user_to_assign
        return group

    df = df.groupby('REF No', group_keys=False).apply(assign_sales_bdo)

    # --- STEP 3: Final cleanup to remove invalid RSM/BDM accidentally assigned ---
    def remove_invalid_bdo(row):
        bdo_clean = clean_user(row.get('Sales BDO'))
        rsm_clean = clean_user(row.get('RSM'))
        bdm_clean = clean_user(row.get('BDM'))
        return pd.NA if bdo_clean in {rsm_clean, bdm_clean} else row['Sales BDO']

    df['Sales BDO'] = df.apply(remove_invalid_bdo, axis=1)

    # --- Optional: Add Validation Column ---
    df['BDO Valid?'] = df.apply(
        lambda r: '❌ RSM/BDM as BDO' if clean_user(r['Sales BDO']) in {
            clean_user(r.get('RSM')), clean_user(r.get('BDM'))
        } else '✅ OK', axis=1
    )

    # --- Display Results ---
    st.subheader("Cleaned Data Preview")
    st.dataframe(df)

    # --- Download Link ---
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Cleaned CSV",
        data=csv,
        file_name="cleaned_funnel.csv",
        mime='text/csv'
    )

    # --- Optional Debug: Show Invalid Assignments ---
    bad_rows = df[df['BDO Valid?'] == '❌ RSM/BDM as BDO']
    if not bad_rows.empty:
        st.warning("⚠️ Some rows had RSM or BDM wrongly in Sales BDO. They were removed.")
        st.dataframe(bad_rows[['REF No', 'Sales BDO', 'RSM', 'BDM']])
