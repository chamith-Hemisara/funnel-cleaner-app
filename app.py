import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Funnel Cleaner App", layout="wide")
st.title("📂 Funnel Data Cleaner")

# Upload CSV
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df.columns = df.columns.str.strip()  # clean column names

    # --- Data type conversions ---
    date_cols = [
        'Inquiry Created Date', 'Site Visit Date Time', 'Latest Quotation Date',
        'Task Created Date', 'Completed Date', 'Claimed Date'
    ]
    for c in date_cols:
        df[c] = pd.to_datetime(df[c], errors='coerce')

    float_cols = [
        'Advance Amount', 'Additional Discount', 'Latest Quoted Inverter Capacity (kW)',
        'Latest Final Investment', 'DC Capacity'
    ]
    for c in float_cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    int_cols = ['No of Panels', 'No of Additional Panels']
    for c in int_cols:
        df[c] = pd.to_numeric(df[c], errors='coerce').astype('Int64')

    bool_cols = ['Customer Contacted?', 'Escalated', 'Lead from Call Center?', 'Claimable']
    for c in bool_cols:
        df[c] = df[c].astype(str).str.lower().map({'yes': True, 'no': False, 'true': True, 'false': False})

    category_cols = [
        'Sales BDO', 'RSM', 'BDM', 'Inquiry Source Category (Source)',
        'Inquiry Category (Source Type)', 'City (CC)', 'District (CC)',
        'Province (CC)', 'System Type', 'Phase', 'Type', 'Brand',
        'Lead Status', 'Lead Status.1', 'User', 'Assignee', 'User Group'
    ]
    for c in category_cols:
        if c in df.columns:
            df[c] = df[c].astype('category')

    # timezone adjust
    df['Completed Date'] += pd.Timedelta(hours=5.5)

    # sort for grouping
    df.sort_values(by=['REF No', 'Task Created Date'], inplace=True)

    # --- Step 1: First Site Visit per REF No ---
    def filter_site_visits(g):
        sv = g[g['Task Name']=='Site Visit']
        if not sv.empty:
            keep = sv.head(1).index
            return g.drop(sv.index.difference(keep))
        return g
    df = df.groupby('REF No', group_keys=False).apply(filter_site_visits)

    # --- Step 2: Latest Waiting Customer Feedback* per REF No ---
    def keep_latest_feedback(g):
        fb = g[g['Task Name'].str.startswith('Waiting Customer Feedback')]
        if not fb.empty:
            idx = fb['Task Created Date'].idxmax()
            return g.drop(fb.index.difference([idx]))
        return g
    df = df.groupby('REF No', group_keys=False).apply(keep_latest_feedback)

    # --- Step 3: Rename repeated tasks ---
    def rename_tasks(g):
        counts = {}
        new = []
        for t in g['Task Name']:
            counts[t] = counts.get(t,0)+1
            suffix = f" {counts[t]}" if counts[t]>1 else ""
            new.append(t+suffix)
        g['Task Name'] = new
        return g
    df = df.groupby('REF No', group_keys=False).apply(rename_tasks)

    # --- Step 4: Escalation Status & Final Stage ---
    def esc_status(row):
        if pd.isna(row['Completed Date']):
            if row['Task Name'].startswith('Contact Customer - DS BDO'):
                return 'BDO Escalation'
            if row['Task Name'].startswith('Contact Customer - DS RSM'):
                return 'RSM Escalation'
            if row['Task Name'].startswith('Contact Customer - DS BDM'):
                return 'BDM Escalation'
        return 'Not Escalated'
    df['Escalation Status'] = df.apply(esc_status, axis=1)

    def final_stage(g):
        latest = g.loc[g['Task Created Date'].idxmax(), 'Task Name']
        g['Final Stage'] = latest
        return g
    df = df.groupby('REF No', group_keys=False).apply(final_stage)

    # --- Step 5: Product & Lead Source split ---
    df['Product'] = (
        df['Brand'].astype(str)+' - '+
        df['Phase'].astype(str)+' '+
        df['Type'].astype(str)+' Inverters - '+
        df['Latest Quoted Inverter Capacity (kW)'].astype(str)+' kW'
    )
    df['Call center or Self'] = df['Lead Status.1'].apply(
        lambda x: 'CRM Call Center' if str(x).strip()=='CRM Call Center' else 'Self Lead'
    )
    df.drop(columns=['Lead Status.1'], inplace=True)

    # --- Step 6: Assign Sales BDO from Contact or Site Visit (w/ RSM/BDM skip) ---
    def assign_sales_bdo(g):
        # 1) try any DS BDO* task
        bdo_tasks = g[g['Task Name'].str.startswith('Contact Customer - DS BDO') & g['User'].notna()]
        if not bdo_tasks.empty:
            user = bdo_tasks.sort_values('Task Created Date').iloc[-1]['User']
        else:
            # 2) fallback to Site Visit—only if that user != RSM or BDM
            sv = g[g['Task Name']=='Site Visit']
            if not sv.empty:
                candidate = sv.iloc[0]['User']
                # get the group's RSM/BDM (assume same for all rows)
                rsm = g['RSM'].iloc[0] if 'RSM' in g else None
                bdm = g['BDM'].iloc[0] if 'BDM' in g else None
                if candidate not in {rsm, bdm}:
                    user = candidate
                else:
                    return g
            else:
                return g
        # assign
        if 'Sales BDO' in g:
            # if categorical, add category
            if pd.api.types.is_categorical_dtype(g['Sales BDO']):
                if user not in g['Sales BDO'].cat.categories:
                    g['Sales BDO'] = g['Sales BDO'].cat.add_categories([user])
        g['Sales BDO'] = user
        return g

    df = df.groupby('REF No', group_keys=False).apply(assign_sales_bdo)

    df.reset_index(drop=True, inplace=True)

    # --- Preview & Download ---
    st.subheader("Preview of Cleaned Data")
    st.dataframe(df.head(10))

    buffer = io.BytesIO()
    df.to_excel(buffer, index=False, engine='openpyxl')
    buffer.seek(0)
    st.download_button(
        label="💾 Download Cleaned Excel",
        data=buffer,
        file_name="Funnel_Cleaned.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
