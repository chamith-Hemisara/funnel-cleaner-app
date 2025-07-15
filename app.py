import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Funnel Cleaner App", layout="wide")
st.title("📂 Funnel Data Cleaner")

# Upload CSV
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    df.columns = df.columns.str.strip()

    # Convert types
    date_cols = ['Inquiry Created Date', 'Site Visit Date Time', 'Latest Quotation Date',
                 'Task Created Date', 'Completed Date', 'Claimed Date']
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    float_cols = ['Advance Amount', 'Additional Discount',
                  'Latest Quoted Inverter Capacity (kW)', 'Latest Final Investment', 'DC Capacity']
    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    int_cols = ['No of Panels', 'No of Additional Panels']
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')

    bool_cols = ['Customer Contacted?', 'Escalated', 'Lead from Call Center?', 'Claimable']
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].astype(str).str.lower().map({'yes': True, 'no': False, 'true': True, 'false': False})

    category_cols = ['Sales BDO', 'RSM', 'BDM', 'Inquiry Source Category (Source)', 'Inquiry Category (Source Type)',
                     'City (CC)', 'District (CC)', 'Province (CC)', 'System Type', 'Phase', 'Type', 'Brand',
                     'Lead Status', 'Lead Status.1', 'User', 'Assignee', 'User Group']
    for col in category_cols:
        if col in df.columns:
            df[col] = df[col].astype('category')

    if 'Completed Date' in df.columns:
        df['Completed Date'] = pd.to_datetime(df['Completed Date'], errors='coerce') + pd.Timedelta(hours=5.5)

    df.sort_values(by=['REF No', 'Task Created Date'], inplace=True)

    # Keep only first Site Visit
    def filter_site_visits(group):
        site_visits = group[group['Task Name'].str.lower().str.strip() == 'site visit']
        if not site_visits.empty:
            keep_idx = site_visits.head(1).index
            return group[~((group['Task Name'].str.lower().str.strip() == 'site visit') & (~group.index.isin(keep_idx)))]
        return group

    df = df.groupby('REF No', group_keys=False).apply(filter_site_visits)

    # Keep only latest Waiting Customer Feedback*
    def keep_latest_waiting_feedback(group):
        feedback_tasks = group[group['Task Name'].str.startswith('Waiting Customer Feedback', na=False)]
        if not feedback_tasks.empty:
            latest_idx = feedback_tasks['Task Created Date'].idxmax()
            return group[~((group['Task Name'].str.startswith('Waiting Customer Feedback', na=False)) & (group.index != latest_idx))]
        return group

    df = df.groupby('REF No', group_keys=False).apply(keep_latest_waiting_feedback)

    # Rename repeated tasks
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

    # Escalation Status
    def get_escalation_status(row):
        if pd.isna(row['Completed Date']):
            if row['Task Name'].startswith('Contact Customer - DS BDO'):
                return 'BDO Escalation'
            elif row['Task Name'].startswith('Contact Customer - DS RSM'):
                return 'RSM Escalation'
            elif row['Task Name'].startswith('Contact Customer - DS BDM'):
                return 'BDM Escalation'
        return 'Not Escalated'

    df['Escalation Status'] = df.apply(get_escalation_status, axis=1)

    # Final Stage
    def assign_final_stage(group):
        latest_task = group.loc[group['Task Created Date'].idxmax(), 'Task Name']
        group['Final Stage'] = latest_task
        return group

    df = df.groupby('REF No', group_keys=False).apply(assign_final_stage)

    # Product
    def safe_str(val):
        return str(val) if pd.notna(val) else ''

    df['Product'] = df.apply(
        lambda r: f"{safe_str(r.get('Brand',''))} - {safe_str(r.get('Phase',''))} {safe_str(r.get('Type',''))} Inverters - {safe_str(r.get('Latest Quoted Inverter Capacity (kW)',''))} kW",
        axis=1
    )

    # Call center or Self
    if 'Lead Status.1' in df.columns:
        df['Call center or Self'] = df['Lead Status.1'].apply(
            lambda x: 'CRM Call Center' if str(x).strip() == 'CRM Call Center' else 'Self Lead'
        )
        df.drop(columns=['Lead Status.1'], inplace=True)

    # Assign Sales BDO logic
    def assign_sales_bdo(group):
        bdo_tasks = group[
            group['Task Name'].str.startswith('Contact Customer - DS BDO', na=False) &
            group['User'].notna()
        ]

        user = None
        if not bdo_tasks.empty:
            user = bdo_tasks.sort_values('Task Created Date').iloc[-1]['User']
        else:
            sv = group[group['Task Name'].str.lower().str.strip() == 'site visit']
            if not sv.empty and sv.iloc[0]['User']:
                user = sv.iloc[0]['User']

        rsm = group['RSM'].iloc[0] if 'RSM' in group.columns else None
        bdm = group['BDM'].iloc[0] if 'BDM' in group.columns else None

        if user:
            if user == rsm:
                group['Sales BDO'] = 'RSM Lead'
            elif user == bdm:
                group['Sales BDO'] = 'BDM Lead'
            else:
                if pd.api.types.is_categorical_dtype(group['Sales BDO']):
                    if user not in group['Sales BDO'].cat.categories:
                        group['Sales BDO'] = group['Sales BDO'].cat.add_categories([user])
                group['Sales BDO'] = user
        return group

    df = df.groupby('REF No', group_keys=False).apply(assign_sales_bdo)

    df.reset_index(drop=True, inplace=True)

    # Preview & Download
    st.subheader("Preview of Cleaned Data (first 10 rows)")
    st.dataframe(df.head(10))

    towrite = io.BytesIO()
    df.to_excel(towrite, index=False, engine='openpyxl')
    towrite.seek(0)

    st.download_button(
        label="💾 Download Cleaned Excel",
        data=towrite,
        file_name="Funnel_Cleaned.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
