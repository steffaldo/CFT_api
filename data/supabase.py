import streamlit as st
from supabase import create_client
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

# ------------------------------------------------------------------
# Client
# ------------------------------------------------------------------

SUPABASE_URL = st.secrets["supabase-public"]["url"]
SUPABASE_KEY = st.secrets["supabase-public"]["key"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


# ------------------------------------------------------------------
# Tables
# ------------------------------------------------------------------

TABLE_INPUTS = "dairy_farm_inputs"
TABLE_OUTPUTS = "dairy_farm_outputs"
TABLE_SUMMARY = "dairy_imact_summary"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _replace_rows(table: str, id_column: str, id_value: Any, rows: List[Dict]):
    """
    Hard replace all rows for a given identifier.
    """
    supabase.table(table).delete().eq(id_column, id_value).execute()

    if rows:
        supabase.table(table).insert(rows).execute()


# ------------------------------------------------------------------
# Dairy farm inputs (parent)
# ------------------------------------------------------------------

def get_dairy_inputs(
    survey_id: Optional[str] = None,
    limit: Optional[int] = None,
):
    query = supabase.table(TABLE_INPUTS).select("*")

    if survey_id is not None:
        query = query.eq("survey_id", survey_id)

    if limit is not None:
        query = query.limit(limit)

    res = query.execute()
    return res.data


def insert_dairy_input(row: Dict):
    payload = {
        **row,
        "last_updated": _now(),
    }

    res = supabase.table(TABLE_INPUTS).insert(payload).execute()
    return res.data


def update_dairy_input(survey_id: str, updates: Dict):
    updates = {
        **updates,
        "last_updated": _now(),
    }

    supabase.table(TABLE_INPUTS) \
        .update(updates) \
        .eq("survey_id", survey_id) \
        .execute()


def delete_dairy_input(survey_id: str):
    supabase.table(TABLE_INPUTS).delete().eq("survey_id", survey_id).execute()


def upsert_dairy_inputs(rows: List[Dict]):
    """
    Upsert multiple dairy input rows.

    Assumes:
      - survey_id is a unique or primary key
    """

    if not rows:
        return

    payload = []
    for r in rows:
        payload.append({
            **r,
            "last_updated": _now(),
        })

    supabase.table(TABLE_INPUTS).upsert(
        payload,
        on_conflict="survey_id",
    ).execute()


# ------------------------------------------------------------------
# Dairy farm outputs (CFT results)
# ------------------------------------------------------------------

def get_dairy_outputs(
    farm_id: Optional[str] = None,
    survey_id: Optional[str] = None,
    limit: Optional[int] = None,
):
    query = supabase.table(TABLE_OUTPUTS).select("*")

    if farm_id is not None:
        query = query.eq("farm_id", farm_id)

    if survey_id is not None:
        query = query.eq("survey_id", survey_id)

    if limit is not None:
        query = query.limit(limit)

    res = query.execute()
    return res.data


def replace_dairy_outputs(
    survey_id: str,
    rows: List[Dict],
):
    """
    Hard replace all output rows for a given survey_id.
    """

    if not rows:
        return

    payload = []
    for r in rows:
        payload.append({
            **r,
            "survey_id": survey_id,
            "last_updated": _now(),
        })

    # delete everything for this survey
    supabase.table(TABLE_OUTPUTS) \
        .delete() \
        .eq("survey_id", survey_id) \
        .execute()

    # insert fresh state
    supabase.table(TABLE_OUTPUTS).insert(payload).execute()


def upsert_dairy_outputs(rows: List[Dict]):
    """
    Upsert flattened CFT output rows.

    Assumes:
      - survey_id is unique or part of a unique constraint
    """

    if not rows:
        return

    payload = []
    for r in rows:
        payload.append({
            **r,
            "last_updated": _now(),
        })

    supabase.table(TABLE_OUTPUTS).upsert(
        payload,
        on_conflict="survey_id",
    ).execute()


# ------------------------------------------------------------------
# Convenience helpers for DataFrames
# ------------------------------------------------------------------

def upsert_inputs_from_df(df):
    """
    Convert a DataFrame to records and upsert into dairy_farm_inputs.
    """
    records = df.to_dict(orient="records")
    upsert_dairy_inputs(records)


def upsert_outputs_from_df(df):
    """
    Convert a DataFrame to records and upsert into dairy_farm_outputs.
    """
    records = df.to_dict(orient="records")
    upsert_dairy_outputs(records)


# ------------------------------------------------------------------
# Final View
# ------------------------------------------------------------------

def get_impact_summary(farm_id: Optional[str] = None):
    
    query = supabase.table(TABLE_SUMMARY).select("*")

    if farm_id is not None:
        query = query.eq("farm_id", farm_id)

    res = query.execute()
    return res.data