import streamlit as st
import pandas as pd
import psycopg2
import os
import requests
import json
from openpyxl import load_workbook
from config.config_loader import load_toml
from components.data_cleaning import *
import streamlit_notify as stn
from utils.api_parser import submit_new_surveys, flatten_json

st.set_page_config(layout="wide")

st.title("CFT Dairy Data Upload")   

stn.notify()

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
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0


survey_dump = st.file_uploader(
    "Upload surveys", accept_multiple_files=True, type="xlsx",
    key=f"uploader{st.session_state.uploader_key}"
)



# initialise mapping schema
schema_path = os.path.join("schema", "input_schema_mapping.csv")
input_schema = pd.read_csv(schema_path)

# Build structured mapping
schema_dict = {
    row.metric: {
        "cell": row.survey_mapping,
        "type": row.types,
        "default": row.default_value if "default_value" in row else None
    }
    for _, row in input_schema.iterrows()
}

# Extract columns
input_columns = list(schema_dict.keys())

# Init empty df to hold ingested data
survey_loader = pd.DataFrame()

feed_conversion_mapping = {
    "fwi_select": "C61",
    "dmi_select": "D61",
    "feed_per_animal": "C64",
    "feed_per_herd": "D64",
    "feed_period_day_single": "C67",
    "feed_period_day_custom": "D67"
}

# Loop and ingest each survey
for survey in survey_dump:
    # read each notebook into a pandas df, ensuring correct values and mapping when they go in

    wb = load_workbook(survey, data_only=True)
    ws = wb.active

    row_data = {}

    for metric, info in schema_dict.items():
        try:
            value = ws[info["cell"]].value

            # if value is None in (None, "", " ") use default
            if value in (None, "", " ") and info["default"] not in (None, "", " "):
                value = info["default"]
            # cast to correct type
            if info["type"] == "int":
                value = int(value)
            elif info["type"] == "float":
                value = float(value)
            elif info["type"] == "string":
                value = str(value)


            # fwi/dmi indicator
            if ws[feed_conversion_mapping["dmi_select"]].value not in (None, "", " "):
                dmi_conversion = False
            elif ws[feed_conversion_mapping["fwi_select"]].value not in (None, "", " "):
                dmi_conversion = True
            else:
                st.error("One or more surveys have an no indication of whether feed data is provided in FWI or DMI")
                st.stop() 

            # feed by animal or herd
            if ws[feed_conversion_mapping["feed_per_animal"]].value not in (None, "", " "):
                herd_feed_inicator = False
            elif ws[feed_conversion_mapping["feed_per_herd"]].value not in (None, "", " "):
                herd_feed_inicator = True
            else:
                st.error("One or more surveys have an no indication of whether feed data is provided at a single cow or herd level")
                st.stop() 

            # feed by animal or herd
            if ws[feed_conversion_mapping["feed_period_day_single"]].value not in (None, "", " "):
                multiday_feed_inicator = 1
            elif ws[feed_conversion_mapping["feed_period_day_custom"]].value not in (None, "", " "):

                if isinstance(ws[feed_conversion_mapping["feed_period_day_custom"]].value, int):
                    multiday_feed_indicator = ws[feed_conversion_mapping["feed_period_day_custom"]].value
                else:
                    st.error("Feeding period for multiple days must be an integer.")
                    st.stop()
            else:
                st.error("One or more surveys have an no indication of whether feed data is provided at a single cow or herd level")
                st.stop() 

            if metric.startswith("feed."):
                if dmi_conversion is False:
                    # value * conversion
                    pass
                if herd_feed_inicator:
                    # value / herd size
                    pass
                if multiday_feed_indicator > 1:
                    value = value / multiday_feed_indicator

        except:
            value = None

        row_data[metric] = value

    # TODO also ensure that the fwi dmi data is done with the dates etc

    survey_loader = pd.concat([survey_loader, pd.DataFrame([row_data])], ignore_index=True)


feed_items = load_toml("feed.toml")["feed"]
herd_sections = load_toml("herd.toml")["herd_section"]
fertilizers = load_toml("fertilizer.toml")["fertilzier"]
herd_varieties = load_toml("herd.toml")["herd_variety"]


def validation_rules():
    return {
        "herd_sections": [s["display_name"] for s in herd_sections],
        "herd_varieties": [s["cft_name"] for s in herd_varieties]
    }



## before sending make sure all display names converted to api names



# -----------------------------
# Streamlit UI for Corrections
# -----------------------------
def display_error_correction_ui(error_report, df):
    """Display interactive UI for correcting errors"""
    
    if not error_report:
        st.success("✅ All data passed validation!")
        return df, True
    
    st.warning(f"⚠️ Found {len(error_report)} rows with data quality issues")
    
    # Initialize session state for tracking corrections
    if 'current_error_idx' not in st.session_state:
        st.session_state.current_error_idx = 0
    if 'corrected_df' not in st.session_state:
        st.session_state.corrected_df = df.copy()
    
    # Get current error
    current_idx = st.session_state.current_error_idx
    
    if current_idx >= len(error_report):
        st.success("✅ All errors reviewed!")
        return st.session_state.corrected_df, True
    
    current_error = error_report[current_idx]
    row_idx = current_error["row_index"]
    
    # Display progress
    st.progress((current_idx + 1) / len(error_report))
    st.write(f"**Error {current_idx + 1} of {len(error_report)}**")
    
    # Show row identifier
    identifier = current_error["row_data"].get("farm_name", f"Row {row_idx}")
    st.error(f"### ❌ {identifier} has {len(current_error['errors'])} error(s)")
    
    # Display each error with correction input
    corrections = {}
    
    for col_name, error_info in current_error["errors"].items():
        with st.container():
            st.markdown(f"**Column: `{col_name}`**")
            
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.write("**Current value:**")
                st.code(str(error_info["current_value"]))
                
                st.write("**Issues:**")
                for err in error_info["errors"]:
                    st.write(f"- {err}")
            
            with col2:
                st.write("**Corrected value:**")
                
                # Determine input type based on rules
                rules = error_info["rules"]
                
                if rules.get("type") == "categorical":
                    corrected = st.selectbox(
                        f"Fix {col_name}",
                        options=rules["allowed_values"],
                        key=f"fix_{row_idx}_{col_name}",
                        label_visibility="collapsed"
                    )
                elif rules.get("type") in ["numeric", "integer"]:
                    corrected = st.number_input(
                        f"Fix {col_name}",
                        value=float(error_info["current_value"]) if pd.notna(error_info["current_value"]) else 0.0,
                        min_value=rules.get("min", None),
                        max_value=rules.get("max", None),
                        key=f"fix_{row_idx}_{col_name}",
                        label_visibility="collapsed"
                    )
                else:
                    corrected = st.text_input(
                        f"Fix {col_name}",
                        value=str(error_info["current_value"]) if pd.notna(error_info["current_value"]) else "",
                        key=f"fix_{row_idx}_{col_name}",
                        label_visibility="collapsed"
                    )
                
                corrections[col_name] = corrected
            
            st.divider()
    
    # Action buttons
    col1, col2, col3 = st.columns([1, 1, 1])
    
    with col1:
        # Only show back button if not on first error
        if current_idx > 0:
            if st.button("⬅️ Previous", use_container_width=True):
                st.session_state.current_error_idx -= 1
                st.rerun()
    
    with col2:
        if st.button("✅ Apply & Continue", use_container_width=True, type="primary"):
            # Apply corrections to dataframe
            for col_name, value in corrections.items():
                st.session_state.corrected_df.at[row_idx, col_name] = value
            
            # Move to next error
            st.session_state.current_error_idx += 1
            st.rerun()
    
    with col3:
        if st.button("🔄 Reset All", use_container_width=True):
            st.session_state.current_error_idx = 0
            st.session_state.corrected_df = df.copy()
            st.rerun()
    
    return st.session_state.corrected_df, False





# -----------------------------
# Integration with your existing code
# -----------------------------
if not survey_loader.empty:
    survey_loader = survey_loader.drop_duplicates()
    st.write("Unique surveys", survey_loader)
    
    # Step 1: Check for duplicates in database
    duplicate_rows, cleaned_df = check_duplicates_in_database(survey_loader, df, id_column="farm_id")
    resolved_df, duplicates_resolved = display_duplicate_resolution_ui(duplicate_rows, cleaned_df, df)
    
    # Step 2: Only proceed to validation if duplicates are resolved
    if duplicates_resolved:
        st.divider()
        st.subheader("📋 Data Quality Validation")
        
        # Run validation
        validation_rules = define_validation_rules()
        error_report = validate_dataframe(resolved_df, validation_rules)
        
        # Display correction UI
        corrected_df, all_valid = display_error_correction_ui(error_report, resolved_df)

        # Ensure numeric columns are never null
        numeric_cols = corrected_df.select_dtypes(include=["number"]).columns.tolist()
        corrected_df[numeric_cols] = corrected_df[numeric_cols].fillna(0)
        
        # Only show submit button when all valid
        if all_valid:
            with st.form("data_quality_form"):
                st.write("✅ Data validated successfully!")
                st.dataframe(corrected_df)
                
                if st.form_submit_button("Upload to Database and Run CFT API"):
                     # Get overwrites from duplicate decisions
                    overwrite_ids = []
                    if 'duplicate_decisions' in st.session_state:
                        overwrite_ids = [
                            farm_id for farm_id, decision 
                            in st.session_state.duplicate_decisions.items() 
                            if decision == "overwrite"
                        ]
                    
                    st.info(f"Uploading {len(corrected_df)} record(s)... ({len(overwrite_ids)} overwrites)")
                    
                    # Upload progress
                    progress_bar = st.progress(0)
                    success_count = 0
                    error_count = 0
                    errors = []
                    
                    for idx, (i, row) in enumerate(corrected_df.iterrows()):
                        new_row = row.to_dict()
                        
                        # Check if this is an overwrite
                        farm_id = new_row.get("farm_id")
                        is_overwrite = farm_id in overwrite_ids
                        
                        try:
                            if is_overwrite:
                                # For overwrites, use PATCH with filter
                                patch_url = f"{url}?farm_id=eq.{farm_id}"
                                resp = requests.patch(
                                    patch_url, 
                                    headers=headers, 
                                    json=new_row, 
                                    verify=False
                                )
                            else:
                                # For new records, use POST
                                resp = requests.post(
                                    url, 
                                    headers=headers, 
                                    json=new_row, 
                                    verify=False
                                )
                            
                            resp.raise_for_status()

                            success_count += 1
                            
                        except requests.exceptions.RequestException as e:
                            error_count += 1

                            errors.append({
                                "row": i,
                                "farm_id": farm_id,
                                "error": str(e)
                            })
                        
                        # Update progress
                        progress_bar.progress((idx + 1) / len(corrected_df))
                    
                    # Show results
                    if error_count == 0:
                        stn.success(f"🎉 All {success_count} record(s) uploaded successfully!")

                        api_results = submit_new_surveys(corrected_df)
                        st.write("CFT API Results")
                        st.json(api_results)

                        # assuming api_results is your JSON list



                        # Apply to your list of JSON objects
                        flat_data = [flatten_json(item) for item in api_results]

                        df = pd.DataFrame(flat_data)
                        st.dataframe(df)
                        
                        # 🔥 FULL RESET
                        # new_key = st.session_state.uploader_key + 1 # to drop uploaded files
                        # st.session_state.clear()
                        # st.session_state.uploader_key = new_key
                        # stn.success(f"{success_count} Surveys Uploaded and Validated! Application state reset.", icon="🚀")
                        # st.rerun()


                    else:
                        st.warning(f"⚠️ Uploaded {success_count} record(s), but {error_count} failed")
                        
                        # Show errors
                        with st.expander("View Errors"):
                            for err in errors:
                                st.error(f"Row {err['row']} (Farm ID: {err['farm_id']}): {err['error']}")


# ----- get into columns
# def flatten_json(y, prefix=''):
#     """
#     Flatten a nested JSON object into a single-level dictionary with dot-separated keys.
#     List indices are included in the keys.
#     """
#     out = {}

#     if isinstance(y, dict):
#         for k, v in y.items():
#             new_key = f"{prefix}.{k}" if prefix else k
#             out.update(flatten_json(v, new_key))
#     elif isinstance(y, list):
#         for i, item in enumerate(y):
#             new_key = f"{prefix}.{i}" if prefix else str(i)
#             out.update(flatten_json(item, new_key))
#     else:
#         out[prefix] = y

#     return out
