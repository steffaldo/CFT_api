import streamlit as st
import pandas as pd
import psycopg2
import os
import requests
import json
from openpyxl import load_workbook


st.title("CFT Dairy Data Upload")

SUPABASE_URL = st.secrets["supabase-public"]["url"]
SUPABASE_KEY = st.secrets["supabase-public"]["key"]
TABLE_NAME = "dairy_farm_inputs"

url = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}"

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Prefer": "return=representation"
}

# -----------------------------
# Fetch table
# -----------------------------
def fetch_table():
    try:
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
        data = response.json()
        return pd.DataFrame(data)
    except requests.exceptions.RequestException as e:
        st.error("Failed to fetch table :(")
        st.error(e)
        return pd.DataFrame()

df = fetch_table()
st.subheader("Current Table")
st.dataframe(df)

# ---- Drop files

survey_dump = st.file_uploader(
    "Upload data", accept_multiple_files=True, type="xlsx"
)



# initialise mapping schema
schema_path = os.path.join("schema", "input_schema_mapping.csv")
input_schema = pd.read_csv(schema_path)

# Build structured mapping
schema_dict = {
    row.metric: {
        "cell": row.survey_mapping,
        "type": row.types
    }
    for _, row in input_schema.iterrows()
}

# Extract columns
input_columns = list(schema_dict.keys())



# Init empty df to hold ingested data
survey_loader = pd.DataFrame()

# Loop and ingest each survey
for survey in survey_dump:
    # read each notebook into a pandas df, ensuring correct values and mapping when they go in

    wb = load_workbook(survey, data_only=True)
    ws = wb.active

    row_data = {}

    for metric, info in schema_dict.items():
        try:
            value = ws[info["cell"]].value
        except:
            value = None
        row_data[metric] = value

    survey_loader = pd.concat([survey_loader, pd.DataFrame([row_data])], ignore_index=True)

    st.write(survey_loader)

    # after in df interactive uui check values are right, push to supabase



    pass

# # -----------------------------
# # 3️⃣ Add a new row
# # -----------------------------
# st.subheader("Add a New Row")

# with st.form("add_row_form"):
#     project_id = st.text_input("Project ID")
#     description = st.text_area("Description")
#     submitted = st.form_submit_button("Add Row")
    
#     if submitted:
#         new_row = {
#             "PROJECT_ID": project_id,
#             "PROJECT_DESCRIPTION": description,
#         }
#         try:
#             resp = requests.post(url, headers=headers, json=new_row, verify=False)
#             resp.raise_for_status()
#             st.success("Row added successfully! 🎉")
#             df = fetch_table()
#             st.dataframe(df)
#         except requests.exceptions.RequestException as e:
#             st.error("Failed to insert row :(")
#             st.error(e)