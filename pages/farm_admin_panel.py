import streamlit as st
import pandas as pd
from data.supabase import get_dairy_inputs, update_dairy_input, delete_dairy_input
 
st.set_page_config(layout="wide")
st.title("Farms Admin Panel")

# Get all registered farms
def get_farms() -> pd.DataFrame:
    farms = pd.DataFrame(get_dairy_inputs())
    st.write(farms)

    return farms

@st.dialog("Add New Farm", width="medium")
def add_new_farm():
    st.text_input("Farm / Business Name", key="new_farm_name")
    st.text_input("Farmer Name", key="new_farmer_name")
    st.text_input("Region", key="new_region")
    st.selectbox("Programme", ["Mondelez Agolin"], key="new_programme")

    st.info(f"Create new farm with ID {st.session_state.get('new_farm_id', 'N/A')}")
    
    if st.button("Submit New Farm"):
        return

if st.button("Add New Farm"):
    add_new_farm()

get_farms()