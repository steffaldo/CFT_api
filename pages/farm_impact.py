import streamlit as st
from data.supabase import get_dairy_inputs, get_impact_summary, get_dairy_outputs
import pandas as pd
import plotly.express as px
from typing import Optional

from utils.api_parser import HERD_SECTIONS

st.set_page_config(layout="wide")
st.title("Farm Impact Page")


# -----------------------------
# Data helpers
# -----------------------------

def load_farms() -> pd.DataFrame:
    return pd.DataFrame(get_dairy_inputs())


def get_selected_farm_id(farms: pd.DataFrame) -> str | None:
    rows = st.session_state.farm_table.selection.get("rows", [])
    if not rows:
        return None
    return farms.iloc[rows[0]]["farm_id"]


def load_results(farm_id: Optional[str] = None) -> pd.DataFrame:
    return pd.DataFrame(get_impact_summary(farm_id))


def melt_and_label_summary(summary: pd.DataFrame) -> pd.DataFrame:
    label_map = {
        "energy_total_CO2e_per_fpcm": "Energy",
        "feed_total_CO2e_per_fpcm": "Feed",
        "grazing_total_CO2e_per_fpcm": "Grazing",
        "manure_total_CO2e_per_fpcm": "Manure",
        "enteric_total_CO2e_per_fpcm": "Enteric",
        "fertiliser_total_CO2e_per_fpcm": "Fertiliser",
        "transport_total_CO2e_per_fpcm": "Transport",
    }

    value_vars = [c for c in label_map if c in summary.columns]

    melted = summary.melt(
        id_vars=["milk_year"],
        value_vars=value_vars,
        value_name="intensity_tco2e_per_fpcm",
        var_name="emission_source",
    )

    melted["emission_source"] = melted["emission_source"].map(label_map)

    return melted


# -----------------------------
# Plot helpers
# -----------------------------

def build_emissions_figure(summary_melted: pd.DataFrame, mode: str):
    plot_df = summary_melted.copy()

    if mode == "Emission Source Share":
        plot_df["y"] = (
            plot_df["intensity_tco2e_per_fpcm"]
            / plot_df.groupby("milk_year")["intensity_tco2e_per_fpcm"].transform("sum")
        )
        y_col = "y"
        y_label = "Share of Total Emissions"
        tickformat = ".0%"
        title = "Emission Source Share Over Years"
    else:
        y_col = "intensity_tco2e_per_fpcm"
        y_label = "tCO₂e / FPCM"
        tickformat = None
        title = "Total Emissions Over Years"

    fig = px.bar(
        plot_df,
        x="milk_year",
        y=y_col,
        color="emission_source",
        title=title,
        labels={
            "milk_year": "Milk Year",
            y_col: y_label,
            "emission_source": "Emission Source",
        },
    )

    fig.update_layout(barmode="stack")

    if tickformat:
        fig.update_yaxes(tickformat=tickformat)


    return fig


# -----------------------------
# UI
# -----------------------------

farms = load_farms()

st.dataframe(
    farms[["farm_id", "milk_year", "main_breed_variety", "total_milk_production_litres"]],
    selection_mode="single-row",
    on_select="rerun",
    key="farm_table",
)

selected_farm_id = get_selected_farm_id(farms)

st.header("Impact Summary for Selected Farm")

if not selected_farm_id:
    st.info("Select a farm to view impact summary.")
    st.stop()

summary = load_results(selected_farm_id)

if summary.empty:
    st.warning("No impact summary data found for the selected farm.")
    st.stop()

summary_melted = melt_and_label_summary(summary)

mode = st.radio(
    "Select Visualization Mode:",
    ["Absolute Emissions", "Emission Source Share"],
    horizontal=True,
)

fig = build_emissions_figure(summary_melted, mode)
st.plotly_chart(fig, use_container_width=True)

# show some of the inputs of selected farm
st.header("Input Data for Selected Farm")
selected_farm_inputs = farms[farms["farm_id"] == selected_farm_id]
selected_farm_inputs['total_cows'] = selected_farm_inputs[[f"{herd['cft_name']}.herd_count" for herd in HERD_SECTIONS]].sum(axis=1)



# cow breakdown
st.subheader("Cow Breakdown by Herd Section")
cow_columns = []
for herd in HERD_SECTIONS:
    cow_columns.append(f"{herd['cft_name']}.herd_count")
cow_breakdown = selected_farm_inputs[cow_columns].T
cow_breakdown.columns = ["cow_count"]
cow_breakdown["herd_section"] = cow_breakdown.index.str.split(".").str[0]
cow_breakdown = cow_breakdown[["herd_section", "cow_count"]]    
fig_cow = px.bar(
    cow_breakdown,
    x="herd_section",
    y="cow_count",
    title="Cow Breakdown by Herd Section",
    labels={
        "herd_section": "Herd Section",
        "cow_count": "Number of Cows",
    },
)
st.plotly_chart(fig_cow, use_container_width=True)