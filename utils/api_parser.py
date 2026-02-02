from config.config_loader import load_toml
import streamlit as st
import urllib3
import requests
import json

# ---- Load Global Configurations ---- #

FEED_ITEMS = load_toml("feed.toml")["feed"]
HERD_SECTIONS = load_toml("herd.toml")["herd_section"]
FERTILIZERS = load_toml("fertilizer.toml")["fertilzier"]
HERD_VARIETIES = load_toml("herd.toml")["herd_variety"]

ID_MAPPINGS = {
    "grazing_quality": {
        "HIGH": 1,
        "LOW": 2,
        None: 1
    }
}

UNITS = {
    "fertilizer_application_rate": 12, # t/ha
    "feed_weight": 7, # kg
    "milk_volume": 15, # litres
    "temperature": 5 # °C
}


# ---- API FUNCTIONS ---- #

def build_farm_input(row):
    """Builds the farm input section of the CFT API payload."""
    return {
        "country": "Poland", 
        "territory": None,
        "climate": "Cool Temperate Moist",
        "average_temperature": {"value": 10, "unit": 5},
        "latitude": 52.679,
        "longitude": 20.030,
        "soil_characteristics": "Sandy Soils",
        "farm_identifier": row["farm_id"] + str("_") + str(row["milk_year"])
    }

def build_general_input(row):
    """Builds the general input section of the CFT API payload."""
    return {
        "grazing_area": {
            "value": row["general.grazing_area_ha"],
            "unit": "ha"
        },
        "feed_approach": 1, # 1 = dmi
        "fertilizer_approach": 2, # 2 = Grazing, grass silage and hay area combined
    }

def build_milk_production_input(row):
    """Builds the milk production input section of the CFT API payload."""
    return {
        "variety": row["main_breed_variety"],
        "reporting_year": row["milk_year"],
        "date_time": "start",
        "date_month": 1, # Season always starts in Jan
        "name": row["farm_id"] + str("_") + str(row["milk_year"]),
        "product_dry": {"value": row["total_milk_production_litres"], "unit": UNITS["milk_volume"]},
        "fat_content": row["milk_fat_content_percent"],
        "protein_content": row["milk_protein_content_percent"],
        "protein_measure": 1 # 1 = true protein
    }

def build_herd_sections_input(row):
    """Builds the herd sections input section of the CFT API payload."""
    
    herd_sections_input = []

    for herd in HERD_SECTIONS:
        herd_sections_input.append({
            "phase": herd["cft_name"],
            "animals": row[f"{herd['cft_name']}.herd_count"],
            "live_weight": {
                "value": row[f"{herd['cft_name']}.herd_weight_kg"],
                "unit": "kg"
            },
            "sold_animals": row[f"{herd['cft_name']}.sold_count"],
            "sold_weight": {
                "value": row[f"{herd['cft_name']}.sold_weight_kg"],
                "unit": "kg"
            },
            "purchased_animals": row[f"{herd['cft_name']}.purchased_count"],
            "purchased_weight": {
                "value": row[f"{herd['cft_name']}.purchased_weight_kg"],
                "unit": "kg"
            }
        })

    return herd_sections_input

def build_grazing_input(row):
    """Builds the grazing input section of the CFT API payload."""

    grazing_input = []

    for herd in HERD_SECTIONS:

        quality_selection = row.get(f"{herd['cft_name']}.grazing_quality", None)

        if quality_selection is not None and not quality_selection.isupper():
            quality_selection = quality_selection.upper()

        grazing_input.append({
            "herd_section": herd["cft_name"],
            "days": row[f"{herd['cft_name']}.grazing_days"],
            "hours": row[f"{herd['cft_name']}.grazing_hours_per_day"],
            "category": 2, # 2 = Confined pasture 
            "quality": ID_MAPPINGS["grazing_quality"][quality_selection] # has to be int  1 =  high, 2 = low
        })
    return grazing_input



def build_fertilizers_input(row):
    """Build fertilizers section input"""
    fertilizers_input = []
    
    for fertilizer in FERTILIZERS:
        base_fertilizer = {
            "type": fertilizer["cft_id"], 
            "production": 8,  # 8 = Europe 2014
            "application_rate": {
                "value": row[f"fertilizers.{fertilizer['key']}.t_per_ha"],
                "unit": UNITS["fertilizer_application_rate"]
            },
            "application_date": "unknown",
            "rate_measure": "product",
            "inhibition": fertilizer["inhibition"]
        }
        
        # Add custom NPK ingredients if applicable
        if fertilizer["cft_id"] == 44:
            base_fertilizer["custom_ingredients"] = {
                "n_total_percentage": 6,
                "n_ammonia_percentage": 6,
                "n_nitric_percentage": 0,
                "n_urea_percentage": 0,
                "p2o5_percentage": 20,
                "p2o5_percentage_type_id": 4,  # 4 = P2O5
                "k2o_percentage": 30,
                "k2o_percentage_type_id": 5  # 5 = K2O 
            }
        
        fertilizers_input.append(base_fertilizer)
    
    return fertilizers_input


def build_feed_components_input(row):
    """Build feed components section input"""
    feed_components_input = []
    
    for feed in FEED_ITEMS:
        for hs in HERD_SECTIONS:
            feed_components_input.append({
                "item": feed["cft_id"],
                "region": feed["region_name"],
                "herd_section": hs["cft_name"],
                "dry_matter": {
                    "value": row[f"feed.{feed['cft_name']}.{hs['cft_name']}.kgDMI_head_day"],
                    "unit": UNITS["feed_weight"]
                },
                "certified": False
            })
    
    return feed_components_input

def build_feed_additives_input(row):
    """Build feed additives section input"""
    return []  # Currently not implemented

def build_manure_input(row):
    """Build manure section input"""
    manure_inputs = []
    herd_sections = ["calf_dairy", "heifer", "cow_milk", "cow_dry"]
    
    for herd in herd_sections:
        manure_type = row[f"manure_type.{herd}"]
        
        if manure_type != "PIT STORAGE AND SOLID STORAGE":
            manure_inputs.extend([
                {"herd_section": herd, "type": 6, "allocation": 50},  # Pit Storage
                {"herd_section": herd, "type": 1, "allocation": 50},  # Solid Storage
            ])
        else:
            manure_inputs.append({
                "herd_section": herd,
                "type": manure_type,
                "allocation": 100
            })
    
    return manure_inputs

def build_bedding_input(row):
    """Build bedding section input"""
    return []  # Currently not implemented

def build_direct_energy_input(row):
    return []  # Currently not implemented

def build_transport_input(row):
    return []  # Currently not implemented


def build_dairy_input(row):
    return {
        "farm": build_farm_input(row),
        "general": build_general_input(row),
        "milk_production": build_milk_production_input(row),
        "herd_sections": build_herd_sections_input(row),
        "grazing": build_grazing_input(row),
        "fertilisers": build_fertilizers_input(row),
        "feed_components": build_feed_components_input(row),
        "feed_additives": build_feed_additives_input(row),
        "manure": build_manure_input(row),
        "bedding": build_bedding_input(row),
        "direct_energy": build_direct_energy_input(row),
        "transport": build_transport_input(row)
    }

def process_single_row(row):
    try:
        return build_dairy_input(row)
    except Exception as e:
        st.warning(f"Error processing farm_id {row.get('farm_id')}: {e}")
        raise


HEADERS = {
    "Content-Type": "application/json",
    "X-Api-App-Authorization": st.secrets["cft_api"]["app_key"],
    "X-Api-Authorization": st.secrets["cft_api"]["api_key"]
}

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def call_cft_api(row):
    payload = process_single_row(row)

    
    try:
        response = requests.post(
            st.secrets["cft_api"]["api_url"],
            json=payload,
            headers=HEADERS,
            verify=False,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        st.error(f"API error for farm_id {row.get('farm_id')}: {response.text}")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Request failed for farm_id {row.get('farm_id')}: {e}")
        return None
    

def submit_new_surveys(df):
    results = []
    for _, row in df.iterrows():
        api_result = call_cft_api(row)
        results.append(api_result)
    return results


# ---- UTILITIES ---- #
def flatten_json(obj, parent_key='', sep='.'):
    """Recursively flattens nested dicts and lists into dot-separated keys."""
    items = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            items.extend(flatten_json(v, new_key, sep=sep).items())
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            new_key = f"{parent_key}{sep}{i}" if parent_key else str(i)
            items.extend(flatten_json(v, new_key, sep=sep).items())
    else:
        items.append((parent_key, obj))
    return dict(items)