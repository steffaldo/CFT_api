import streamlit as st
from data.supabase import get_dairy_inputs, get_impact_summary
import pandas as pd
import plotly.express as px
from typing import Optional
from utils.api_parser import HERD_SECTIONS, build_dairy_input

# debug
if st.sidebar.checkbox("Debug mode (show extra info)", value=st.session_state.debug):
    st.session_state.debug = True

# Chart colors matching .streamlit/config.toml chartCategoricalColors
CHART_COLORS = [
    "#2a9df4",  # primary blue
    "#14b8a6",  # teal accent
    "#0ea5e9",  # light blue
    "#22c55e",  # green
    "#6366f1",  # indigo
    "#0f766e",  # dark teal
    "#4b5563",  # gray
]

st.set_page_config(layout="wide", page_title="View Impact Report")

st.title("Farm Impact Dashboard")
st.caption(
    "Emissions and production performance for your selected farm over time. "
    "Use the sidebar to pick a farm and explore its impact."
)

# --- Data Loading ---


def load_farms() -> pd.DataFrame:
    """Load all farm input data."""
    return pd.DataFrame(get_dairy_inputs())

def load_results(farm_id: Optional[str] = None) -> pd.DataFrame:
    """Load impact summary results for a given farm."""
    return pd.DataFrame(get_impact_summary(farm_id))

def get_selected_farm_id(farms: pd.DataFrame, pre_selected_index: int = 0) -> Optional[str]:
    """Get the selected farm_id from the sidebar."""
    if farms.empty:
        return None
    return st.sidebar.selectbox(
        "Select a Farm",
        farms["farm_id"].unique(),
        index=pre_selected_index,
        help="Choose a farm to view its detailed impact analysis."
    )

# --- Data Transformation ---

# Shared source labels for intensity (per_fpcm) and absolute (_total_CO2e) columns
SOURCE_LABEL_MAP_INTENSITY = {
    "energy_total_CO2e_per_fpcm": "Energy",
    "feed_total_CO2e_per_fpcm": "Feed",
    "grazing_total_CO2e_per_fpcm": "Grazing",
    "manure_total_CO2e_per_fpcm": "Manure",
    "enteric_total_CO2e_per_fpcm": "Enteric",
    "fertiliser_total_CO2e_per_fpcm": "Fertiliser",
    "transport_total_CO2e_per_fpcm": "Transport",
}
SOURCE_LABEL_MAP_ABSOLUTE = {
    "energy_total_CO2e": "Energy",
    "feed_total_CO2e": "Feed",
    "grazing_total_CO2e": "Grazing",
    "manure_total_CO2e": "Manure",
    "enteric_total_CO2e": "Enteric",
    "fertiliser_total_CO2e": "Fertiliser",
    "transport_total_CO2e": "Transport",
}

def melt_and_label_summary(summary: pd.DataFrame) -> pd.DataFrame:
    """Melt the summary DataFrame for easier plotting and apply readable labels (intensity, per FPCM)."""
    value_vars = [c for c in SOURCE_LABEL_MAP_INTENSITY if c in summary.columns]
    melted = summary.melt(
        id_vars=["milk_year"],
        value_vars=value_vars,
        value_name="intensity_tco2e_per_fpcm",
        var_name="emission_source",
    )
    melted["emission_source"] = melted["emission_source"].map(SOURCE_LABEL_MAP_INTENSITY)
    return melted

def melt_summary_absolute(summary: pd.DataFrame) -> pd.DataFrame:
    """Melt the summary DataFrame to absolute emissions by source (tonnes CO₂e)."""
    value_vars = [c for c in SOURCE_LABEL_MAP_ABSOLUTE if c in summary.columns]
    melted = summary.melt(
        id_vars=["milk_year"],
        value_vars=value_vars,
        value_name="tco2e",
        var_name="emission_source",
    )
    melted["emission_source"] = melted["emission_source"].map(SOURCE_LABEL_MAP_ABSOLUTE)
    return melted

def get_pie_data_absolute(summary: pd.DataFrame):
    """Return a DataFrame of emission_source and tco2e for the latest year (for pie: % of total farm emissions)."""
    if summary.empty or "milk_year" not in summary.columns:
        return pd.DataFrame(columns=["emission_source", "tco2e"])
    latest_year = summary["milk_year"].max()
    row = summary[summary["milk_year"] == latest_year].iloc[0]
    records = []
    for col, label in SOURCE_LABEL_MAP_ABSOLUTE.items():
        if col in row.index and pd.notna(row[col]) and float(row[col]) != 0:
            records.append({"emission_source": label, "tco2e": float(row[col])})
    return pd.DataFrame(records)

# Source keys for table (column prefixes in schema)
SOURCE_GAS_COLS = [
    ("energy", "Energy"),
    ("enteric", "Enteric"),
    ("feed", "Feed"),
    ("fertiliser", "Fertiliser"),
    ("grazing", "Grazing"),
    ("manure", "Manure"),
    ("transport", "Transport"),
]

def build_source_by_gas_table(summary_row: pd.Series) -> pd.DataFrame:
    """Build a table of emissions by source and gas type (CO2, N2O, CH4, Total CO2e) from one year's summary row."""
    rows = []
    for prefix, label in SOURCE_GAS_COLS:
        co2 = summary_row.get(f"{prefix}_CO2")
        n2o = summary_row.get(f"{prefix}_N2O")
        ch4 = summary_row.get(f"{prefix}_CH4")
        total_co2e = summary_row.get(f"{prefix}_total_CO2e")
        rows.append({
            "Source": label,
            "CO₂ (tonnes)": float(co2) if pd.notna(co2) else None,
            "N₂O (tonnes)": float(n2o) if pd.notna(n2o) else None,
            "CH₄ (tonnes)": float(ch4) if pd.notna(ch4) else None,
            "Total CO₂e (tonnes)": float(total_co2e) if pd.notna(total_co2e) else None,
        })
    # Total row
    co2_t = summary_row.get("CO2_tonnes")
    n2o_t = summary_row.get("N2O_tonnes")
    ch4_t = summary_row.get("CH4_tonnes")
    tot_t = summary_row.get("emissions_total")
    rows.append({
        "Source": "Total",
        "CO₂ (tonnes)": float(co2_t) if pd.notna(co2_t) else None,
        "N₂O (tonnes)": float(n2o_t) if pd.notna(n2o_t) else None,
        "CH₄ (tonnes)": float(ch4_t) if pd.notna(ch4_t) else None,
        "Total CO₂e (tonnes)": float(tot_t) if pd.notna(tot_t) else None,
    })
    df = pd.DataFrame(rows)
    return df

# --- Plotting Functions ---

def build_emissions_figure(
    summary_melted: pd.DataFrame,
    summary_absolute_melted: pd.DataFrame,
    mode: str,
):
    """Builds the historical emissions bar chart (intensity, absolute, or share of total)."""
    if mode == "Emissions intensity (tCO₂e/FPCM)":
        plot_df = summary_melted.copy()
        plot_df["y"] = plot_df["intensity_tco2e_per_fpcm"]
        y_label, tick_format, title = "tCO₂e / FPCM", None, "Emissions intensity over years"
    elif mode == "Absolute emissions":
        plot_df = summary_absolute_melted.copy()
        plot_df["y"] = plot_df["tco2e"]
        y_label, tick_format, title = "tCO₂e", None, "Absolute emissions over years"
    else:
        # Emission Source Share: % of total farm emissions (from absolute)
        plot_df = summary_absolute_melted.copy()
        total_per_year = plot_df.groupby("milk_year")["tco2e"].transform("sum")
        plot_df["y"] = plot_df["tco2e"] / total_per_year.replace(0, pd.NA)
        y_label, tick_format, title = "Share of total emissions", ".0%", "Emission source share over years"

    fig = px.bar(
        plot_df,
        x="milk_year",
        y="y",
        color="emission_source",
        title=title,
        labels={"milk_year": "Milk Year", "y": y_label, "emission_source": "Source"},
    )
    fig.update_layout(barmode="stack", legend_title="Source")
    if tick_format:
        fig.update_yaxes(tickformat=tick_format)
    return fig

def build_emissions_pie_chart(summary: pd.DataFrame):
    """Builds a pie chart showing share of total farm emissions by source (latest year)."""
    pie_data = get_pie_data_absolute(summary)
    if pie_data.empty:
        return px.pie(names=[], values=[]).update_layout(title="Share of total farm emissions (no data)")
    latest_year = summary["milk_year"].max()
    fig = px.pie(
        pie_data,
        names="emission_source",
        values="tco2e",
        title=f"Share of total farm emissions by source ({latest_year})",
        hole=0.3,
        color_discrete_sequence=CHART_COLORS,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
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
    )
    return fig

# --- UI Display Functions ---

# --- Download Button ---
st.sidebar.download_button(
    label="Download All Impact Data (CSV)",
    data=load_results().to_csv(index=False),
    file_name=f"all_farm_impact_data.csv",
    mime="text/csv",
    help=(
        "Download a CSV containing impact summary results for all farms. "
        "Use this if you want to analyse or archive results outside this dashboard."
    ),
)


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

    total_emissions = latest_summary["emissions_total"].iloc[0] if "emissions_total" in latest_summary.columns else None
    total_emissions_intensity = latest_summary["emissions_per_fpcm"].iloc[0] if pd.notna(latest_summary["emissions_per_fpcm"].iloc[0]) else None
    total_cows = farm_inputs[[f"{herd['cft_name']}.herd_count" for herd in HERD_SECTIONS]].sum(axis=1).iloc[0]
    milk_production = farm_inputs["total_milk_production_litres"].iloc[0]

    # Deltas vs previous year
    delta_total = None
    delta_intensity = None
    if len(summary) > 1:
        previous_year = summary["milk_year"].nlargest(2).iloc[-1]
        previous_summary = summary[summary["milk_year"] == previous_year]
        if "emissions_total" in previous_summary.columns and pd.notna(previous_summary["emissions_total"].iloc[0]):
            delta_total = (total_emissions or 0) - float(previous_summary["emissions_total"].iloc[0])
        if pd.notna(previous_summary["emissions_per_fpcm"].iloc[0]):
            delta_intensity = (total_emissions_intensity or 0) - float(previous_summary["emissions_per_fpcm"].iloc[0])

    kpi_row = st.container(horizontal=True, horizontal_alignment="distribute", gap="medium")
    with kpi_row:
        if total_emissions is not None and pd.notna(total_emissions):
            st.metric(
                label="Total Emissions",
                value=f"{float(total_emissions):,.1f} tCO₂e",
                delta=f"{delta_total:,.1f}" if delta_total is not None else None,
                help="Total farm emissions in tonnes CO₂ equivalent. Delta shows change from previous year.",
            )
        else:
            st.metric(label="Total Emissions", value="—", help="Total farm emissions (tCO₂e). Not available.")
        if total_emissions_intensity is not None:
            st.metric(
                label="Emission Intensity",
                value=f"{total_emissions_intensity:.3f} tCO₂e/FPCM",
                delta=f"{delta_intensity:.3f}" if delta_intensity is not None else None,
                help="Tonnes of CO2 equivalent per unit of Fat and Protein Corrected Milk. Delta shows change from previous year.",
            )
        else:
            st.metric(label="Emission Intensity", value="—", help="tCO₂e per FPCM. Not available.")
        st.metric(label="Total Cows", value=int(total_cows))
        st.metric(label="Total Milk Production", value=f"{int(milk_production):,} Litres")

# --- Main UI ---

farms = load_farms()
st.sidebar.header("Farm Selection")
st.sidebar.caption(
    "The selected farm drives all metrics and charts on this dashboard."
)

# Check session state for a pre-selected farm from the comparison page
pre_selected_index = 0
if 'selected_farm_id' in st.session_state:
    farm_list = farms["farm_id"].unique().tolist()
    if st.session_state['selected_farm_id'] in farm_list:
        pre_selected_index = farm_list.index(st.session_state['selected_farm_id'])
    # Clear the session state so the selection is not sticky
    del st.session_state['selected_farm_id']

selected_farm_id = get_selected_farm_id(farms, pre_selected_index=pre_selected_index)

if not selected_farm_id:
    st.info("Select a farm from the sidebar to view its impact summary.")
    st.stop()

st.header(f"Impact Summary for: `{selected_farm_id}`")
st.caption(
    "Review high-level emissions intensity, herd size, and milk production before diving into detailed charts below."
)
summary = load_results(selected_farm_id)
farm_inputs = farms[farms["farm_id"] == selected_farm_id]

if summary.empty:
    st.warning("No impact summary data found for the selected farm.")
    st.stop()


# --- Display KPIs ---
st.divider()
display_kpi_metrics(summary, farm_inputs)
st.divider()

# --- Create Tabs ---
tab1, tab2, tab3 = st.tabs(["📊 Impact Summary", "🐄 Herd & Feed", "📄 Input Data"])

with tab1:
    st.subheader("Emission Analysis")
    st.caption(
        "Explore how total emissions are distributed across sources and how they change over milk years."
    )
    summary_melted = melt_and_label_summary(summary)
    summary_absolute_melted = melt_summary_absolute(summary)

    # Charts row: bar (wider) + pie, using columns for 2:1 ratio
    chart_col1, chart_col2 = st.columns([2, 1])
    with chart_col1:
        mode = st.radio(
            "Emissions view",
            ["Emissions intensity (tCO₂e/FPCM)", "Absolute emissions", "Emission Source Share"],
            help=(
                "Emissions intensity: tCO₂e per FPCM by source. "
                "Absolute emissions: total tCO₂e by source. "
                "Emission Source Share: % of total farm emissions by source (matches the pie chart)."
            ),
            horizontal=True,
            key="viz_mode",
        )
        fig_emissions = build_emissions_figure(summary_melted, summary_absolute_melted, mode)
        st.plotly_chart(fig_emissions, use_container_width=True, theme="streamlit")
    with chart_col2:
        fig_pie = build_emissions_pie_chart(summary)
        st.plotly_chart(fig_pie, use_container_width=True, theme="streamlit")

    st.subheader("Emissions by source and gas")
    st.caption("Breakdown per source by gas type (tonnes) for the selected milk year.")
    milk_years = sorted(summary["milk_year"].dropna().unique(), reverse=True)
    if milk_years:
        year_selector_row = st.container(horizontal=True, vertical_alignment="center", gap="small")
        with year_selector_row:
            st.markdown("**Milk year**")
            selected_year = st.selectbox(
                "Milk year",
                milk_years,
                index=0,
                key="source_gas_year",
                help="Select the milk year for the breakdown table below.",
                label_visibility="collapsed",
            )
        summary_row = summary[summary["milk_year"] == selected_year].iloc[0]
        source_gas_df = build_source_by_gas_table(summary_row)
        st.dataframe(
            source_gas_df.style.format(
                subset=["CO₂ (tonnes)", "N₂O (tonnes)", "CH₄ (tonnes)", "Total CO₂e (tonnes)"],
                formatter="{:.2f}",
                na_rep="—",
            ),
            use_container_width=True,
        )
    else:
        st.warning("No milk year data available for the breakdown table.")

with tab2:
    st.subheader("Herd Composition")
    st.caption(
        "See how cows are distributed across herd sections to understand the structure of the herd."
    )
    herd_row = st.container(horizontal=True, vertical_alignment="top", gap="medium")
    with herd_row:
        with st.container():
            fig_cow_breakdown = build_cow_breakdown_figure(farm_inputs)
            st.plotly_chart(fig_cow_breakdown, use_container_width=True, theme="streamlit")
        st.info("More feed analysis coming soon.")

with tab3:
    st.subheader("Raw Input Data")
    st.caption(
        "Snapshot of the input data used to generate results for this farm. "
        "This table may be wide and is best used for spot checks."
    )
    st.dataframe(farm_inputs.T)

    # run api parser using input data from supabase
    if st.session_state.debug:
        st.subheader("View Payload Data")
        # get_dairy_inputs(f"{selected_farm_id}_2025")
        st.json(build_dairy_input(farm_inputs.iloc[0]))




