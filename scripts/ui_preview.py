"""A page that shows every component of the visual layer, with the real Streamlit widgets beside them: streamlit run scripts/ui_preview.py"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import streamlit as st
from dawa_buddy import ui

st.set_page_config(page_title="Dawa Buddy UI preview", page_icon="💊", layout="centered", initial_sidebar_state="collapsed")
st.markdown(ui.css(), unsafe_allow_html=True)

st.markdown(ui.header(), unsafe_allow_html=True)
st.title("Was your medicine bill fair?")
st.markdown("<p class='db-sub'>Photograph your bill. We compare it with government price lists and your prescription, and tell you what to ask.</p>", unsafe_allow_html=True)
st.file_uploader("Photo of your bill", type=["png", "jpg"], key="p_up")
st.button("Check my bill", type="primary", width="stretch", key="p_b1")
c1, c2 = st.columns(2)
c1.button("Pharmacy bill", width="stretch", key="p_s1"); c2.button("Hospital bill", width="stretch", key="p_s2")

st.markdown(ui.header(2), unsafe_allow_html=True)
st.subheader("Check the numbers")
with st.container(border=True):
    st.markdown("**SHELCAL 500MG TAB**  \n30 × ₹9.81 = ₹294.21")
    st.segmented_control("Sold", ["per tablet", "per strip"], default="per tablet", key="p_seg", label_visibility="collapsed")
    st.markdown(ui.found_badge("Found on PharmEasy, Truemeds"), unsafe_allow_html=True)
    st.number_input("Tablets per strip", min_value=0.0, value=15.0, step=1.0, key="p_n")
    with st.popover("Fix a number", width="stretch"):
        st.text_input("Item", value="SHELCAL 500MG TAB", key="p_t")

st.markdown(ui.header(3, "Result"), unsafe_allow_html=True)
st.markdown(ui.verdict("red", "3 things to ask about", "Two lines are above a legal limit and one medicine may not be the one prescribed. Ask the seller to explain.",
                       [("₹26", "above legal limits", "red"), ("₹120", "possible generic saving", "amber"), ("100%", "of the bill checked", "green")]), unsafe_allow_html=True)
st.markdown(ui.section_label("Ask about these", 4), unsafe_allow_html=True)
st.markdown(ui.card("red", "SHELCAL 500MG TAB", "Check before taking", visual=ui.diff("Shelcal-XT", "Shelcal 500"), why="Same brand name, different product."), unsafe_allow_html=True)
st.markdown(ui.card("red", "AMLONG 5 TAB", "Above the printed MRP", total="₹90 total", visual=ui.meter(9, 8, "red", "You paid ₹9 per tablet", "MRP ₹8"), why="Ask for the pack."), unsafe_allow_html=True)
st.markdown(ui.card("red", "TELMA 40 TAB", "Above the legal ceiling", total="₹372 total", visual=ui.meter(12.40, 6.92, "red", "You paid ₹12.40 per tablet", "Legal limit ₹6.92"), why="Ask the seller to explain."), unsafe_allow_html=True)
st.markdown(ui.card("amber", "ATORVA 10 TAB", "A cheaper generic exists. Ask your doctor.", total="₹147 total", visual=ui.meter(4.90, 0.91, "amber", "You paid ₹4.90 per tablet", "Generic ₹0.91"), why="Do not switch on your own."), unsafe_allow_html=True)
with st.expander("Within the limits (1)"):
    st.write("DOLO 650 TAB")
with st.expander("Not covered by a price list (2)"):
    st.write("Supplements and consumables")
st.markdown(ui.callout("<b>2 lines have no pack size or MRP.</b> Look them up on pharmacy websites."), unsafe_allow_html=True)
st.button("Download the questions to ask", type="primary", width="stretch", key="p_dl")
st.markdown(ui.footer("Information, not a finding of wrongdoing. Not medical advice."), unsafe_allow_html=True)

st.subheader("Your medicines")
st.segmented_control("Language", ["English", "हिन्दी", "ಕನ್ನಡ"], default="हिन्दी", key="p_lang", label_visibility="collapsed")
st.markdown(ui.dose_box("दिन में 2 बार: सुबह 1 गोली (650 mg), रात 1 गोली (650 mg), खाने के बाद, 5 दिन तक लें।"), unsafe_allow_html=True)
st.markdown(ui.dose_box("ದಿನಕ್ಕೆ 2 ಬಾರಿ: ಬೆಳಿಗ್ಗೆ 1 ಮಾತ್ರೆ (650 mg), ರಾತ್ರಿ 1 ಮಾತ್ರೆ (650 mg), ಊಟದ ನಂತರ, 5 ದಿನಗಳವರೆಗೆ ತೆಗೆದುಕೊಳ್ಳಿ."), unsafe_allow_html=True)
