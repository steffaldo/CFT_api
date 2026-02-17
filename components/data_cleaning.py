import pandas as pd
from config.config_loader import load_toml
import streamlit as st

herd_varieties = load_toml("herd.toml")["herd_variety"]

def define_validation_rules():
    """Define validation rules for each column"""
    return {
        "farm_id": {
            "type": "string",
            "required": True,
            "min_length": 4,
            "max_length": 100
        },
        # "farm_size": {
        #     "type": "numeric",
        #     "required": True,
        #     "min": 0,
        #     "max": 10000
        # },
        # "herd_size": {
        #     "type": "integer",
        #     "required": True,
        #     "min": 1,
        #     "max": 10000
        # },
        "main_breed_variety": {
            "type": "categorical",
            "required": True,
            "allowed_values": [s["cft_name"] for s in herd_varieties]
        },
        "bedding.type": {
            "type": "categorical",
            "required": False,
            "allowed_values": ["straw", "sand", "newspaper", "sawdust"]
        },
        # Add more rules here ....
    }

# -----------------------------
# Validation Functions
# -----------------------------
def validate_value(value, column_name, rules):
    """Validate a single value against rules"""
    errors = []
    
    # Check if required
    if rules.get("required", False):
        if pd.isna(value) or value == "" or value is None:
            errors.append(f"Required field is empty")
            return errors
    
    # If value is empty and not required, skip other checks
    if pd.isna(value) or value == "" or value is None:
        return errors
    
    # Type-specific validation
    if rules.get("type") == "numeric":
        try:
            num_val = float(value)
            if "min" in rules and num_val < rules["min"]:
                errors.append(f"Value {num_val} is below minimum {rules['min']}")
            if "max" in rules and num_val > rules["max"]:
                errors.append(f"Value {num_val} exceeds maximum {rules['max']}")
        except (ValueError, TypeError):
            errors.append(f"Must be a number, got '{value}'")
    
    elif rules.get("type") == "integer":
        try:
            int_val = int(float(value))
            if float(value) != int_val:
                errors.append(f"Must be a whole number, got '{value}'")
            if "min" in rules and int_val < rules["min"]:
                errors.append(f"Value {int_val} is below minimum {rules['min']}")
            if "max" in rules and int_val > rules["max"]:
                errors.append(f"Value {int_val} exceeds maximum {rules['max']}")
        except (ValueError, TypeError):
            errors.append(f"Must be an integer, got '{value}'")
    
    elif rules.get("type") == "string":
        str_val = str(value)
        if "min_length" in rules and len(str_val) < rules["min_length"]:
            errors.append(f"Text too short (min {rules['min_length']} chars)")
        if "max_length" in rules and len(str_val) > rules["max_length"]:
            errors.append(f"Text too long (max {rules['max_length']} chars)")
    
    elif rules.get("type") == "categorical":
        if value not in rules.get("allowed_values", []):
            errors.append(f"Must be one of: {', '.join(rules['allowed_values'])}")
    
    return errors

def validate_dataframe(df, validation_rules):
    """Validate entire dataframe and return error report"""
    error_report = []
    
    for _, row in df.iterrows():
        row_errors = {}
        
        for col_name, rules in validation_rules.items():
            if col_name not in df.columns:
                continue
            
            value = row[col_name]
            errors = validate_value(value, col_name, rules)
            
            if errors:
                row_errors[col_name] = {
                    "current_value": value,
                    "errors": errors,
                    "rules": rules
                }
        
        if row_errors:
            error_report.append({
                "survey_id": row.get("survey_id"),
                "row_data": row.to_dict(),
                "errors": row_errors
            })
    
    return error_report


# -----------------------------
# Duplicate Check Functions
# -----------------------------
def check_duplicates_in_database(df, existing_df, id_column="farm_id"):
    """Check if any farm_ids in new data already exist in database"""
    if id_column not in df.columns:
        st.warning(f"Column '{id_column}' not found in uploaded data")
        return [], df
    
    if existing_df.empty or id_column not in existing_df.columns:
        return [], df
    
    # Find duplicates
    new_ids = set(df[id_column].dropna())
    existing_ids = set(existing_df[id_column].dropna())
    duplicate_ids = new_ids.intersection(existing_ids)
    
    if not duplicate_ids:
        return [], df
    
    # Get rows with duplicate IDs and check for differences
    duplicate_rows = []
    rows_to_drop = []
    
    for farm_id in duplicate_ids:
        new_row_idx = df[df[id_column] == farm_id].index[0]
        new_row_data = df.loc[new_row_idx].to_dict()
        existing_row_data = existing_df[existing_df[id_column] == farm_id].iloc[0].to_dict()
        
        # Compare rows to find differences
        differences = {}
        for col in new_row_data.keys():
            if col in existing_row_data:
                new_val = new_row_data[col]
                existing_val = existing_row_data[col]
                
                # Handle NaN comparison
                new_is_na = pd.isna(new_val)
                existing_is_na = pd.isna(existing_val)
                
                if new_is_na and existing_is_na:
                    continue  # Both are NaN, consider them equal
                elif new_is_na != existing_is_na:
                    differences[col] = {
                        "new": new_val,
                        "existing": existing_val
                    }
                elif new_val != existing_val:
                    differences[col] = {
                        "new": new_val,
                        "existing": existing_val
                    }
        
        # If no differences, automatically drop this row
        if not differences:
            rows_to_drop.append(new_row_idx)
        else:
            duplicate_rows.append({
                "farm_id": farm_id,
                "row_index": new_row_idx,
                "row_data": new_row_data,
                "existing_data": existing_row_data,
                "differences": differences
            })
    
    # Drop exact matches silently
    cleaned_df = df.drop(rows_to_drop)
    
    # Only show message if there are some exact duplicates but also some unique records
    # (If all are duplicates, app.py will handle the message)
    if rows_to_drop and not cleaned_df.empty:
        st.info(f"Automatically skipped {len(rows_to_drop)} exact duplicate(s) already in database")
    
    return duplicate_rows, cleaned_df

def display_duplicate_resolution_ui(duplicate_rows, df, existing_df):
    """Display UI for resolving duplicate farm_ids"""
    
    if not duplicate_rows:
        return df, True  # No duplicates, proceed
    
    st.warning(f"⚠️ Found {len(duplicate_rows)} farm(s) with different data than what's in the database")
    
    # Initialize session state
    if 'duplicate_decisions' not in st.session_state:
        st.session_state.duplicate_decisions = {}
    if 'resolved_df' not in st.session_state:
        st.session_state.resolved_df = df.copy()
    
    # Track if all duplicates have been resolved
    all_resolved = len(st.session_state.duplicate_decisions) == len(duplicate_rows)
    
    # Display each duplicate
    for i, dup in enumerate(duplicate_rows):
        farm_id = dup["farm_id"]
        row_idx = dup["row_index"]
        differences = dup["differences"]
        
        # Check if this duplicate has been resolved
        decision = st.session_state.duplicate_decisions.get(farm_id)
        
        with st.expander(
            f"{'✅' if decision else '❌'} Farm ID: {farm_id} - {len(differences)} field(s) differ",
            expanded=(decision is None)
        ):
            st.error(f"**Farm ID `{farm_id}` exists with different data**")
            
            # Show only different fields
            st.write(f"**📊 {len(differences)} Difference(s):**")
            
            for col_name, values in differences.items():
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**📥 New: `{col_name}`**")
                    st.warning(f"**{values['new']}**")
                
                with col2:
                    st.write(f"**💾 Current: `{col_name}`**")
                    st.info(f"{values['existing']}")
            
            # Decision buttons
            if decision is None:
                st.divider()
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.button(
                        "🔄 Overwrite (Use new data)",
                        key=f"overwrite_{farm_id}",
                        use_container_width=True,
                        type="primary"
                    ):
                        st.session_state.duplicate_decisions[farm_id] = "overwrite"
                        st.rerun()
                
                with col2:
                    if st.button(
                        "🗑️ Drop (Keep current data)",
                        key=f"drop_{farm_id}",
                        use_container_width=True
                    ):
                        st.session_state.duplicate_decisions[farm_id] = "drop"
                        # Remove this row from the dataframe
                        st.session_state.resolved_df = st.session_state.resolved_df.drop(row_idx)
                        st.rerun()
            else:
                st.divider()
                # Show decision that was made
                if decision == "overwrite":
                    st.success("✅ Decision: Will **overwrite** with new data")
                else:
                    st.info("✅ Decision: Will **drop** new data and keep current")
                
                if st.button(
                    "↩️ Change Decision",
                    key=f"change_{farm_id}",
                    use_container_width=True
                ):
                    # Reset decision for this farm
                    del st.session_state.duplicate_decisions[farm_id]
                    # Restore row if it was dropped
                    if decision == "drop":
                        st.session_state.resolved_df = df.copy()
                        # Reapply other drop decisions
                        for fid, dec in st.session_state.duplicate_decisions.items():
                            if dec == "drop":
                                drop_idx = df[df["farm_id"] == fid].index[0]
                                st.session_state.resolved_df = st.session_state.resolved_df.drop(drop_idx)
                    st.rerun()
    
    # Summary and proceed button
    if all_resolved:
        st.divider()
        overwrite_count = sum(1 for d in st.session_state.duplicate_decisions.values() if d == "overwrite")
        drop_count = sum(1 for d in st.session_state.duplicate_decisions.values() if d == "drop")
        
        st.success(f"✅ All conflicts resolved: {overwrite_count} to overwrite, {drop_count} to drop")
        
    else:
        st.warning(f"⏳ Please resolve all {len(duplicate_rows)} conflict(s) before proceeding")
    
    return st.session_state.resolved_df, all_resolved