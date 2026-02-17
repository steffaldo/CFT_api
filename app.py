import streamlit as st


upload_page = st.Page("upload.py", title="CFT API Upload", icon=":material/arrow_upload_ready:")
impact_page = st.Page("farm_impact.py", title="Farm Environmental Impact", icon=":material/analytics:")

pg = st.navigation([upload_page, impact_page])
st.set_page_config(page_title="Pol Survey CFT API", page_icon="🐄", layout="wide")
pg.run()


