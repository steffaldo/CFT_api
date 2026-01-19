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
from utils.api_parser import submit_new_surveys
from data.supabase import (
    get_dairy_inputs,
    upsert_dairy_inputs,
    upsert_outputs_from_df,
)

# -- TEMP - identify zscalar for my dev laptop ---
os.environ["SSL_CERT_FILE"] = r"C:\certs\zscaler_root_ca.pem"
os.environ["REQUESTS_CA_BUNDLE"] = r"C:\certs\zscaler_root_ca.pem"


st.set_page_config(layout="wide")

st.title("CFT Dairy Data Upload")   

stn.notify()



data = get_dairy_inputs()
df = pd.DataFrame(data)

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


# ----- get into columns
def flatten_cft_response(response: list) -> pd.DataFrame:
    """
    Flattens a CFT API response into a single wide table.
    One row per farm, with category-level emissions expanded into columns.
    Splits farm_identifier into farm_name and farm_year.
    """

    rows = []

    for record in response:

        farm_identifier = record["farm"]["farm_identifier"]


        if "_" in farm_identifier:
            farm_name, milk_year = farm_identifier.rsplit("_", 1)
        else:
            farm_name = farm_identifier
            milk_year = None
            st.warning("Farm identifier missing year suffix. Contact administrator.")

        summary = record["summary"]
        disagg = summary["disaggregation_totals"][0]

        row = {
            "farm_identifier": farm_identifier,
            "farm_name": farm_name,
            "milk_year": pd.to_numeric(milk_year, errors="coerce"),

            # Overall summary
            "emissions_total": float(summary["emissions_total"][0]),
            "emissions_total_unit": summary["emissions_total"][1],
            "emissions_per_fpcm": float(summary["emissions_per_fpcm"][0]),
            "emissions_per_fpcm_unit": summary["emissions_per_fpcm"][1],

            # Disaggregation totals
            "CO2_tonnes": float(disagg["CO2"]["metric_tonnes_CO2"][0]),
            "CO2e_from_CO2_tonnes": float(disagg["CO2"]["metric_tonnes_CO2e"][0]),

            "N2O_tonnes": float(disagg["N2O"]["metric_tonnes_N2O"][0]),
            "CO2e_from_N2O_tonnes": float(disagg["N2O"]["metric_tonnes_CO2e"][0]),

            "CH4_tonnes": float(disagg["CH4"]["metric_tonnes_CH4"][0]),
            "CO2e_from_CH4_tonnes": float(disagg["CH4"]["metric_tonnes_CO2e"][0]),

            # Metadata
            "cft_version": record["information"]["cft_version"]
        }

        # Flatten category-level emissions into wide columns
        for item in record["total_emissions"]:
            name = item["name"]

            row[f"{name}_CO2"] = float(item["CO2"])
            row[f"{name}_N2O"] = float(item["N2O"])
            row[f"{name}_CH4"] = float(item["CH4"])
            row[f"{name}_total_CO2e"] = float(item["total_CO2e"])
            row[f"{name}_total_CO2e_per_fpcm"] = float(item["total_CO2e_per_fpcm"])

        rows.append(row)

    df_wide = pd.DataFrame(rows)

    return df_wide


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

                    # -------------------------------------------------
                    # Get overwrites from duplicate decisions
                    # -------------------------------------------------
                    overwrite_ids = []
                    if 'duplicate_decisions' in st.session_state:
                        overwrite_ids = [
                            farm_id for farm_id, decision 
                            in st.session_state.duplicate_decisions.items() 
                            if decision == "overwrite"
                        ]

                    st.info(f"Uploading {len(corrected_df)} record(s)... ({len(overwrite_ids)} overwrites)")

                    progress_bar = st.progress(0)

                    # -------------------------------------------------
                    # Build payloads
                    # -------------------------------------------------
                    records = corrected_df.to_dict(orient="records")

                    # If you want true upsert semantics for *all* rows:
                    # upsert_dairy_inputs(records)

                    # If you want overwrite to mean "hard replace":
                    new_rows = []
                    overwrite_rows = []

                    for r in records:
                        farm_id = r.get("farm_id")
                        if farm_id in overwrite_ids:
                            overwrite_rows.append(r)
                        else:
                            new_rows.append(r)

                    try:
                        # -------------------------------------------------
                        # Insert new rows
                        # -------------------------------------------------
                        if new_rows:
                            upsert_dairy_inputs(new_rows)

                        progress_bar.progress(0.5)

                        # -------------------------------------------------
                        # Overwrite existing rows (hard replace semantics)
                        # -------------------------------------------------
                        if overwrite_rows:
                            # Easiest: upsert still works because farm_id is unique
                            upsert_dairy_inputs(overwrite_rows)

                        progress_bar.progress(1.0)

                        stn.success(f"🎉 All {len(records)} record(s) uploaded successfully!")

                        # -------------------------------------------------
                        # Run CFT API
                        # -------------------------------------------------
                        api_results = submit_new_surveys(corrected_df)
                        st.write("CFT API Results")

                        # Flatten
                        df_wide = flatten_cft_response(api_results)
                        st.write(df_wide)

                        # -------------------------------------------------
                        # Write outputs to Supabase
                        # -------------------------------------------------
                        upsert_outputs_from_df(df_wide)

                    except Exception as e:
                        st.error("❌ Failed to upload records to Supabase")
                        st.exception(e)






