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
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors='coerce')

    float_cols = [
        'Advance Amount', 'Additional Discount', 'Latest Quoted Inverter Capacity (kW)',
        'Latest Final Investment', 'DC Capacity'
    ]
    for c in float_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    int_cols = ['No of Panels', 'No of Additional Panels']
    for c in int_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').astype('Int64')

    bool_cols = ['Customer Contacted?', 'Escalated', 'Lead from Call Center?', 'Claimable']
    for c in bool_cols:
        if c in df.columns:
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

    # Timezone adjustment
    if 'Completed Date' in df.columns:
        df['Completed Date'] = pd.to_datetime(df['Completed Date'], errors='coerce') + pd.Timedelta(hours=5.5)

    # Sort for grouping
    if {'REF No', 'Task Created Date'}.issubset(df.columns):
        df.sort_values(by=['REF No', 'Task Created Date'], inplace=True)

    # --- Step 1: First Site Visit per REF No ---
    def filter_site_visits(group):
        site_visits = group[group['Task Name'] == 'Site Visit']
        if not site_visits.empty:
            keep_idx = site_visits.head(1).index
            return group[~((group['Task Name'] == 'Site Visit') & (~group.index.isin(keep_idx)))]
        return group
    df = df.groupby('REF No', group_keys=False).apply(filter_site_visits)

    # --- Step 2: Latest Waiting Customer Feedback per REF No ---
    def keep_latest_waiting_feedback(group):
        feedback_tasks = group[group['Task Name'].str.startswith('Waiting Customer Feedback')]
        if not feedback_tasks.empty:
            latest_idx = feedback_tasks['Task Created Date'].idxmax()
            return group[~((group['Task Name'].str.startswith('Waiting Customer Feedback')) & (group.index != latest_idx))]
        return group
    df = df.groupby('REF No', group_keys=False).apply(keep_latest_waiting_feedback)

    # --- Step 3: Rename repeated tasks ---
    def rename_repeated_tasks(group):
        task_counts = {}
        new_task_names = []
        for task in group['Task Name']:
            task_counts[task] = task_counts.get(task, 0) + 1
            suffix = f" {task_counts[task]}" if task_counts[task] > 1 else ""
            new_task_names.append(f"{task}{suffix}")
        group['Task Name'] = new_task_names
        return group
    df = df.groupby('REF No', group_keys=False).apply(rename_repeated_tasks)

    # Run filter_site_visits again after rename (Step 1 repeated)
    df = df.groupby('REF No', group_keys=False).apply(filter_site_visits)

    # --- Step 4: Escalation Status & Final Stage ---
    def get_escalation_status(row):
        task = row['Task Name']
        completed = row['Completed Date']
        if pd.isna(completed):
            if task.startswith('Contact Customer - DS BDO'):
                return 'BDO Escalation'
            elif task.startswith('Contact Customer - DS RSM'):
                return 'RSM Escalation'
            elif task.startswith('Contact Customer - DS BDM'):
                return 'BDM Escalation'
        return 'Not Escalated'
    df['Escalation Status'] = df.apply(get_escalation_status, axis=1)

    def assign_final_stage(group):
        if 'Task Created Date' in group.columns and not group.empty:
            latest_task = group.loc[group['Task Created Date'].idxmax(), 'Task Name']
            group['Final Stage'] = latest_task
        else:
            group['Final Stage'] = None
        return group
    df = df.groupby('REF No', group_keys=False).apply(assign_final_stage)

    # --- Step 5: Product & Lead Source split ---
    # Build Product column safely
    def build_product(row):
        parts = []
        for col in ['Brand', 'Phase', 'Type', 'Latest Quoted Inverter Capacity (kW)']:
            if col in row and pd.notna(row[col]):
                parts.append(str(row[col]))
            else:
                parts.append('')
        return f"{parts[0]} - {parts[1]} {parts[2]} Inverters - {parts[3]} kW"
    df['Product'] = df.apply(build_product, axis=1)

    # Call center or Self
    if 'Lead Status.1' in df.columns:
        df['Call center or Self'] = df['Lead Status.1'].apply(
            lambda x: 'CRM Call Center' if str(x).strip() == 'CRM Call Center' else 'Self Lead'
        )
        df.drop(columns=['Lead Status.1'], inplace=True)

    # --- Step 6: Assign Sales BDO from Contact or Site Visit, fallback RSM/BDM ---
    def assign_sales_bdo(g):
        user = None
        if 'Task Name' in g.columns and 'User' in g.columns:
            bdo_tasks = g[g['Task Name'].str.startswith('Contact Customer - DS BDO') & g['User'].notna()]
            if not bdo_tasks.empty:
                user = bdo_tasks.sort_values('Task Created Date', ascending=False)['User'].iloc[0]
            else:
                site_visit = g[g['Task Name'] == 'Site Visit']
                if not site_visit.empty:
                    candidate = site_visit.iloc[0]['User']
                    rsm = g['RSM'].iloc[0] if 'RSM' in g else None
                    bdm = g['BDM'].iloc[0] if 'BDM' in g else None
                    if candidate not in {rsm, bdm}:
                        user = candidate

        if 'Sales BDO' in g.columns:
            # Add user to categories if categorical dtype
            if pd.api.types.is_categorical_dtype(g['Sales BDO']):
                if user and user not in g['Sales BDO'].cat.categories:
                    g['Sales BDO'] = g['Sales BDO'].cat.add_categories([user])

            # Fill missing Sales BDO with user if found
            if user:
                g['Sales BDO'] = g['Sales BDO'].fillna(user)

            # Fill any remaining missing Sales BDO cells with RSM or BDM values
            missing_mask = g['Sales BDO'].isna() | (g['Sales BDO'] == '')
            if missing_mask.any():
                rsm_val = g['RSM'].iloc[0] if 'RSM' in g else None
                bdm_val = g['BDM'].iloc[0] if 'BDM' in g else None

                # Fill missing with RSM first, then BDM if still missing
                g.loc[missing_mask, 'Sales BDO'] = g.loc[missing_mask, 'Sales BDO'].fillna(rsm_val)
                g.loc[missing_mask, 'Sales BDO'] = g.loc[missing_mask, 'Sales BDO'].fillna(bdm_val)

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
