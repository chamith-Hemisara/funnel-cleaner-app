import streamlit as st
import pandas as pd
import io

st.set_page_config(page_title="Funnel Cleaner App", layout="wide")
st.title("\U0001F4C2 Funnel Data Cleaner")

# Upload CSV
uploaded_file = st.file_uploader("Upload your CSV file", type=["csv"])

if uploaded_file:
    df = pd.read_csv(uploaded_file)

    # ---- Data Cleaning Begins ----
    date_cols = [
        'Inquiry Created Date', 'Site Visit Date Time', 'Latest Quotation Date',
        'Task Created Date', 'Completed Date', 'Claimed Date'
    ]
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors='coerce')

    float_cols = [
        'Advance Amount', 'Additional Discount', 'Latest Quoted Inverter Capacity (kW)',
        'Latest Final Investment', 'DC Capacity'
    ]
    for col in float_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    int_cols = ['No of Panels', 'No of Additional Panels']
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').astype('Int64')

    bool_cols = ['Customer Contacted?', 'Escalated', 'Lead from Call Center?', 'Claimable']
    for col in bool_cols:
        df[col] = df[col].astype(str).str.lower().map({'yes': True, 'no': False, 'true': True, 'false': False})

    category_candidates = [
        'Sales BDO', 'RSM', 'BDM', 'Inquiry Source Category (Source)',
        'Inquiry Category (Source Type)', 'City (CC)', 'District (CC)',
        'Province (CC)', 'System Type', 'Phase', 'Type', 'Brand',
        'Lead Status', 'Lead Status.1', 'User', 'Assignee', 'User Group'
    ]
    for col in category_candidates:
        if col in df.columns:
            df[col] = df[col].astype('category')

    # Adjust timezone
    df['Completed Date'] = pd.to_datetime(df['Completed Date'], errors='coerce') + pd.Timedelta(hours=5.5)

    df.sort_values(by=['REF No', 'Task Created Date'], inplace=True)

    def filter_site_visits(group):
        site_visits = group[group['Task Name'] == 'Site Visit']
        if not site_visits.empty:
            keep_idx = site_visits.head(1).index
            return group[~((group['Task Name'] == 'Site Visit') & (~group.index.isin(keep_idx)))]
        return group

    df = df.groupby('REF No', group_keys=False).apply(filter_site_visits)

    def keep_latest_waiting_feedback(group):
        feedback_tasks = group[group['Task Name'].str.startswith('Waiting Customer Feedback')]
        if not feedback_tasks.empty:
            latest_idx = feedback_tasks['Task Created Date'].idxmax()
            return group[~((group['Task Name'].str.startswith('Waiting Customer Feedback')) & (group.index != latest_idx))]
        return group

    df = df.groupby('REF No', group_keys=False).apply(keep_latest_waiting_feedback)

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
        latest_task = group.loc[group['Task Created Date'].idxmax(), 'Task Name']
        group['Final Stage'] = latest_task
        return group

    df = df.groupby('REF No', group_keys=False).apply(assign_final_stage)

    df['Product'] = (
        df['Brand'].astype(str) + ' - ' +
        df['Phase'].astype(str) + ' ' +
        df['Type'].astype(str) + ' Inverters - ' +
        df['Latest Quoted Inverter Capacity (kW)'].astype(str) + ' kW'
    )

    df['Call center or Self'] = df['Lead Status.1'].apply(
        lambda x: 'CRM Call Center' if str(x).strip() == 'CRM Call Center' else 'Self Lead'
    )
    df.drop(columns=['Lead Status.1'], inplace=True)

    df.reset_index(drop=True, inplace=True)

    # Display preview
    st.subheader("Preview of Cleaned Data")
    st.dataframe(df.head(10))

    # Download button
    towrite = io.BytesIO()
    df.to_excel(towrite, index=False, engine='openpyxl')
    towrite.seek(0)

    st.download_button(
        label="\U0001F4BE Download Cleaned Excel",
        data=towrite,
        file_name="Funnel_Cleaned.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
