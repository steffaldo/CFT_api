import streamlit as st
import pandas as pd
import plotly.express as px
from data.supabase import get_impact_summary 
from typing import Optional

from farm_impact import load_results

# --- Page Config ---
st.set_page_config(layout="wide", page_title="Farm Comparison")

# --- Data Loading & Transformation ---

def load_all_results() -> pd.DataFrame:
    """Load all impact summary results."""
    return pd.DataFrame(get_impact_summary())


# Shared source labels for absolute (_total_CO2e) columns
SOURCE_LABEL_MAP_ABSOLUTE = {
    "energy_total_CO2e": "Energy",
    "feed_total_CO2e": "Feed",
    "grazing_total_CO2e": "Grazing",
    "manure_total_CO2e": "Manure",
    "enteric_total_CO2e": "Enteric",
    "fertiliser_total_CO2e": "Fertiliser",
    "transport_total_CO2e": "Transport",
}

def get_latest_year_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Filter the summary to include only the latest year for each farm."""
    if df.empty:
        return pd.DataFrame()
    latest_years = df.loc[df.groupby("farm_id")["milk_year"].idxmax()]
    return latest_years

def prepare_comparison_data(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare data for the comparison bar chart and table."""
    value_vars = [c for c in SOURCE_LABEL_MAP_ABSOLUTE if c in df.columns]
    melted = df.melt(
        id_vars=["farm_id", "milk_year", "emissions_total"],
        value_vars=value_vars,
        value_name="tco2e",
        var_name="emission_source",
    )
    melted["emission_source"] = melted["emission_source"].map(SOURCE_LABEL_MAP_ABSOLUTE)
    return melted.sort_values("emissions_total", ascending=False)

# --- Main UI ---

st.title("Farm-to-Farm Comparison")
st.caption("Compare emission performance across all farms for the most recent reporting year.")

# --- Download Button ---
st.sidebar.download_button(
    label="Download All Impact Data (CSV)",
    data=load_all_results().to_csv(index=False),
    file_name=f"all_farm_impact_data.csv",
    mime="text/csv",
    help=(
        "Download a CSV containing impact summary results for all farms. "
        "Use this if you want to analyse or archive results outside this dashboard."
    ),
)

all_summary = load_all_results()

if all_summary.empty:
    st.warning("No impact summary data available for comparison.")
    st.stop()

latest_summary = get_latest_year_summary(all_summary)
comparison_data = prepare_comparison_data(latest_summary)

st.header("Total Emissions Ranking")
st.caption("Bar chart showing total emissions (tonnes CO₂e), colored by source. The table below is ranked by total emissions.")

# --- Bar Chart ---
fig = px.bar(
    comparison_data,
    x="farm_id",
    y="tco2e",
    color="emission_source",
    title="Total Emissions by Farm (Latest Year)",
    labels={"farm_id": "Farm", "tco2e": "Total Emissions (tCO₂e)", "emission_source": "Source"},
    category_orders={"farm_id": comparison_data.drop_duplicates("farm_id")["farm_id"].tolist()}
)
fig.update_layout(barmode="stack", xaxis_title=None, xaxis_tickangle=45)

# Use on_select to capture clicks
selection = st.plotly_chart(
    fig,
    use_container_width=True,
    on_select="rerun",
    selection_mode="points"
)

# --- Ranked Table ---
st.header("Ranked Emissions Table")
ranked_df = latest_summary[["farm_id", "emissions_total", "emissions_per_fpcm", "milk_year"]].rename(columns={
    "farm_id": "Farm",
    "emissions_total": "Total Emissions (tCO₂e)",
    "emissions_per_fpcm": "Intensity (tCO₂e/FPCM)",
    "milk_year": "Year"
}).sort_values("Total Emissions (tCO₂e)", ascending=False).reset_index(drop=True)

table_selection = st.dataframe(
    ranked_df,
    on_select="rerun",
    selection_mode="single-row",
    use_container_width=True,
    hide_index=True
)


