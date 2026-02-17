import streamlit as st
from data.supabase import get_dairy_inputs, get_impact_summary
import pandas as pd
import plotly.express as px
from typing import Optional, Dict
from utils.api_parser import HERD_SECTIONS

st.set_page_config(layout="wide")

st.title("🚜 Farm Impact Dashboard")

# --- Data Loading ---

@st.cache_data
def load_farms() -> pd.DataFrame:
    """Load all farm input data."""
    return pd.DataFrame(get_dairy_inputs())

@st.cache_data
def load_results(farm_id: Optional[str] = None) -> pd.DataFrame:
    """Load impact summary results for a given farm."""
    return pd.DataFrame(get_impact_summary(farm_id))

def get_selected_farm_id(farms: pd.DataFrame) -> Optional[str]:
    """Get the selected farm_id from the sidebar."""
    if farms.empty:
        return None
    return st.sidebar.selectbox(
        "Select a Farm",
        farms["farm_id"].unique(),
        help="Choose a farm to view its detailed impact analysis."
    )

# --- Data Transformation ---

def melt_and_label_summary(summary: pd.DataFrame) -> pd.DataFrame:
    """Melt the summary DataFrame for easier plotting and apply readable labels."""
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

# --- Plotting Functions ---

def build_emissions_figure(summary_melted: pd.DataFrame, mode: str):
    """Builds the historical emissions bar chart."""
    plot_df = summary_melted.copy()
    
    if mode == "Emission Source Share":
        # Calculate percentage share
        total_emissions = plot_df.groupby("milk_year")["intensity_tco2e_per_fpcm"].transform("sum")
        plot_df["y"] = (plot_df["intensity_tco2e_per_fpcm"] / total_emissions)
        y_label, tick_format, title = "Share of Total Emissions", ".0%", "Emission Source Share Over Years"
    else:
        plot_df["y"] = plot_df["intensity_tco2e_per_fpcm"]
        y_label, tick_format, title = "tCO₂e / FPCM", None, "Emissions Intensity Over Years"

    fig = px.bar(
        plot_df,
        x="milk_year",
        y="y",
        color="emission_source",
        title=title,
        labels={"milk_year": "Milk Year", "y": y_label, "emission_source": "Source"},
        template="plotly_white"
    )
    fig.update_layout(barmode="stack", legend_title="Source")
    if tick_format:
        fig.update_yaxes(tickformat=tick_format)
    return fig

def build_emissions_pie_chart(summary_melted: pd.DataFrame):
    """Builds a pie chart for the most recent year's emission sources."""
    latest_year = summary_melted["milk_year"].max()
    pie_data = summary_melted[summary_melted["milk_year"] == latest_year]

    fig = px.pie(
        pie_data,
        names="emission_source",
        values="intensity_tco2e_per_fpcm",
        title=f"Emission Sources in {latest_year}",
        hole=0.3,
    )
    fig.update_traces(textposition='inside', textinfo='percent+label')
    return fig

def build_cow_breakdown_figure(farm_inputs: pd.DataFrame):
    """Builds a bar chart for cow breakdown by herd section."""
    cow_columns = [f"{herd['cft_name']}.herd_count" for herd in HERD_SECTIONS]
    cow_breakdown = farm_inputs[cow_columns].T
    cow_breakdown.columns = ["cow_count"]
    cow_breakdown["herd_section"] = [s['display_name'] for s in HERD_SECTIONS]
    
    fig = px.bar(
        cow_breakdown,
        x="herd_section",
        y="cow_count",
        title="Cow Breakdown by Herd Section",
        labels={"herd_section": "Herd Section", "cow_count": "Number of Cows"},
        template="plotly_white"
    )
    return fig

# --- UI Display Functions ---



def get_all_impact_summary_csv() -> str:
    """Fetches all impact summary data and returns it as a CSV string."""
    all_summary_df = pd.DataFrame(get_impact_summary())
    return all_summary_df.to_csv(index=False)

def display_kpi_metrics(summary: pd.DataFrame, farm_inputs: pd.DataFrame):
    """Display key performance indicators in metric cards."""
    latest_year = summary["milk_year"].max()
    latest_summary = summary[summary["milk_year"] == latest_year]
    
    if latest_summary.empty:
        st.warning("No data for the latest year to display KPIs.")
        return

    total_emissions_intensity = latest_summary["emissions_per_fpcm"].iloc[0]
    total_cows = farm_inputs[[f"{herd['cft_name']}.herd_count" for herd in HERD_SECTIONS]].sum(axis=1).iloc[0]
    milk_production = farm_inputs["total_milk_production_litres"].iloc[0]

    # Calculate trends if there's more than one year
    delta = None
    if len(summary) > 1:
        previous_year = summary["milk_year"].nlargest(2).iloc[-1]
        previous_summary = summary[summary["milk_year"] == previous_year]
        previous_emissions_intensity = previous_summary["emissions_per_fpcm"].iloc[0]
        delta = total_emissions_intensity - previous_emissions_intensity

    col1, col2, col3 = st.columns(3)
    col1.metric(
        label="Total Emission Intensity",
        value=f"{total_emissions_intensity:.3f} tCO₂e/FPCM",
        delta=f"{delta:.3f}" if delta is not None else None,
        help="Tonnes of CO2 equivalent per unit of Fat and Protein Corrected Milk. Delta shows change from previous year."
    )
    col2.metric(label="Total Cows", value=int(total_cows))
    col3.metric(label="Total Milk Production", value=f"{int(milk_production):,} Litres")

# --- Main UI ---

farms = load_farms()
st.sidebar.header("Farm Selection")
selected_farm_id = get_selected_farm_id(farms)

if not selected_farm_id:
    st.info("Select a farm from the sidebar to view its impact summary.")
    st.stop()

st.header(f"Impact Summary for: `{selected_farm_id}`")
summary = load_results(selected_farm_id)
farm_inputs = farms[farms["farm_id"] == selected_farm_id]

if summary.empty:
    st.warning("No impact summary data found for the selected farm.")
    st.stop()

# --- Download Button ---
st.sidebar.download_button(
    label="Download All Data (CSV)",
    data=load_results().to_csv(index=False),
    file_name=f"{selected_farm_id}_farm_impact_data.csv",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    help="Download raw input data and impact summary for the selected farm."
)

# --- Display KPIs ---
display_kpi_metrics(summary, farm_inputs)
st.divider()

# --- Create Tabs ---
tab1, tab2, tab3 = st.tabs(["📊 Impact Summary", "🐄 Herd & Feed", "📄 Input Data"])

with tab1:
    st.subheader("Emission Analysis")
    summary_melted = melt_and_label_summary(summary)
    
    col1, col2 = st.columns([2, 1])
    with col1:
        mode = st.radio(
            "Select Visualization Mode:",
            ["Absolute Emissions", "Emission Source Share"],
            horizontal=True,
            key="viz_mode"
        )
        fig_emissions = build_emissions_figure(summary_melted, mode)
        st.plotly_chart(fig_emissions, use_container_width=True)
    with col2:
        fig_pie = build_emissions_pie_chart(summary_melted)
        st.plotly_chart(fig_pie, use_container_width=True)

with tab2:
    st.subheader("Herd Composition")
    fig_cow_breakdown = build_cow_breakdown_figure(farm_inputs)
    st.plotly_chart(fig_cow_breakdown, use_container_width=True)
    # Placeholder for more feed-related info
    st.info("More feed analysis coming soon.")

with tab3:
    st.subheader("Raw Input Data")
    st.dataframe(farm_inputs. T)