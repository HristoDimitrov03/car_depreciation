import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client

from config import PAGE_SIZE, require_env

st.set_page_config(page_title="Skoda Market Tracker", layout="wide")

# --- HIDE STREAMLIT BRANDING & MENUS ---
custom_css = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            .stDeployButton {display: none;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(custom_css, unsafe_allow_html=True)

# --- FETCH DATA ---
@st.cache_data(ttl=300)
def load_data():
    url = require_env("SUPABASE_URL")
    key = require_env("SUPABASE_ANON_KEY")
    supabase: Client = create_client(url, key)
    rows = []
    start = 0
    while True:
        response = (
            supabase.table("car_listings")
            .select("*")
            .order("id", desc=False)
            .range(start, start + PAGE_SIZE - 1)
            .execute()
        )
        batch = response.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return pd.DataFrame(rows)

df = load_data()

if df.empty:
    st.error("No data found in Supabase. Check your uploader.")
else:
    # --- SIDEBAR FILTERS ---
    st.sidebar.header("🔍 Filters")
    
    # 1. Brand (Typing disabled via filter_mode=None)
    available_brands = df['make'].unique().tolist()
    default_brand_idx = available_brands.index("Skoda") if "Skoda" in available_brands else 0
    selected_brand = st.sidebar.selectbox("Car Brand", available_brands, index=default_brand_idx, filter_mode=None)
    
    # 2. Model (Typing disabled)
    available_models = df[df['make'] == selected_brand]['model'].unique().tolist()
    default_model_idx = available_models.index("Octavia") if "Octavia" in available_models else 0
    selected_model = st.sidebar.selectbox("Car Model", available_models, index=default_model_idx, filter_mode=None)
    
    # 3. Year From (Typing disabled)
    years_from = list(range(1990, 2027))
    selected_year_from = st.sidebar.selectbox("Year From", years_from, index=0, filter_mode=None)
    
    # 4. Year To (dynamically locked to not be lower than Year From, Typing disabled)
    years_to = list(range(selected_year_from, 2027))
    selected_year_to = st.sidebar.selectbox("Year To", years_to, index=len(years_to)-1, filter_mode=None)
    
    # 5. Fuel Type
    fuel_options = ["Diesel", "Petrol", "Electric", "Hybrid", "Gas/LPG"]
    selected_fuel = st.sidebar.multiselect("Fuel Type", fuel_options, default=fuel_options)
    
    # 6. Transmission
    trans_options = ["Automatic", "Manual"]
    selected_trans = st.sidebar.multiselect("Transmission", trans_options, default=trans_options)
    
    # 7 & 8. Horsepower From / To (Text/Number Boxes)
    col_hp1, col_hp2 = st.sidebar.columns(2)
    with col_hp1:
        hp_from = st.number_input("HP From", min_value=0, value=0, step=10)
    with col_hp2:
        hp_to = st.number_input("HP To", min_value=int(hp_from), value=1000, step=10)
        
    # 9. Max Mileage (Typing disabled)
    mileage_options = [i * 10000 for i in range(1, 16)] + [200000, 250000, 300000, "Over 300000"]
    def format_mileage(x):
        return x if x == "Over 300000" else f"{x:,} km"
    selected_mileage = st.sidebar.selectbox("Max Mileage", mileage_options, index=len(mileage_options)-1, format_func=format_mileage, filter_mode=None)

    # --- APPLY FILTERS LOGIC ---
    active_fuels = selected_fuel if selected_fuel else fuel_options
    active_trans = selected_trans if selected_trans else trans_options

    filtered_df = df[
        (df['make'] == selected_brand) &
        (df['model'] == selected_model) &
        (df['year'] >= selected_year_from) &
        (df['year'] <= selected_year_to) &
        (df['fuel_type'].isin(active_fuels)) &
        (df['transmission'].isin(active_trans)) &
        (df['horsepower'] >= hp_from) &
        (df['horsepower'] <= hp_to)
    ]
    
    if selected_mileage != "Over 300000":
        filtered_df = filtered_df[filtered_df['mileage_km'] <= int(selected_mileage)]

    # --- MAIN DASHBOARD RENDERING ---
    st.title("🚗 Bulgarian Used Car Market: Skoda")
    st.markdown("Live depreciation tracking and deal scoring for Skoda listings from mobile.bg.")

    if filtered_df.empty:
        st.warning("No listings match the current filters. Please adjust your criteria in the sidebar.")
    else:
        # --- TOP METRICS (Exactly 3 cards) ---
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Listings", len(filtered_df))
        col2.metric("Average Price", f"€{filtered_df['price_eur'].mean():,.0f}")
        col3.metric("Average Mileage", f"{filtered_df['mileage_km'].mean():,.0f} km")

        st.divider()

        # --- DEPRECIATION CURVES ---
        st.subheader("📉 Depreciation Curves")
        st.caption("Click any circle in the chart below to open its mobile.bg offer.")
        
        tab1, tab2 = st.tabs(["Price vs. Year", "Price vs. Mileage"])
        
        with tab1:
            fig_year = px.scatter(
                filtered_df, x="year", y="price_eur", 
                color="fuel_type", size="horsepower",
                hover_data=["transmission", "mileage_km", "price_eur"],
                custom_data=["link"],
                trendline="ols", 
                title="Price vs. Manufacturing Year (Depreciation by Age)",
                labels={"year": "Manufacturing Year", "price_eur": "Price (€)"}
            )
            event_year = st.plotly_chart(
                fig_year, 
                use_container_width=True, 
                on_select="rerun", 
                selection_mode="points",
                key="scatter_year"
            )
            
            if event_year and event_year.get("selection") and event_year["selection"].get("points"):
                pts = event_year["selection"]["points"]
                if pts and "customdata" in pts[0] and pts[0]["customdata"]:
                    target_url = pts[0]["customdata"][0]
                    if target_url:
                        st.link_button(f"🔗 Open Offer on mobile.bg", target_url, type="primary")

        with tab2:
            fig_mileage = px.scatter(
                filtered_df, x="mileage_km", y="price_eur", 
                color="fuel_type", size="horsepower",
                hover_data=["year", "transmission", "price_eur"],
                custom_data=["link"],
                trendline="ols",
                title="Price vs. Mileage (Depreciation by Wear)",
                labels={"mileage_km": "Mileage (km)", "price_eur": "Price (€)"}
            )
            event_mileage = st.plotly_chart(
                fig_mileage, 
                use_container_width=True, 
                on_select="rerun", 
                selection_mode="points",
                key="scatter_mileage"
            )
            
            if event_mileage and event_mileage.get("selection") and event_mileage["selection"].get("points"):
                pts = event_mileage["selection"]["points"]
                if pts and "customdata" in pts[0] and pts[0]["customdata"]:
                    target_url = pts[0]["customdata"][0]
                    if target_url:
                        st.link_button(f"🔗 Open Offer on mobile.bg", target_url, type="primary")

        st.divider()

        # --- DEAL FINDER ---
        st.subheader("🎯 Deal Finder")
        st.markdown("Sorted by newest year and lowest price.")
        
        table_df = filtered_df.sort_values(by=['year', 'price_eur'], ascending=[False, True]).copy()
        
        table_df = table_df[['year', 'make', 'model', 'price_eur', 'mileage_km', 'horsepower', 'fuel_type', 'transmission', 'link']]
        table_df.columns = ['Year', 'Brand', 'Model', 'Price', 'Mileage (km)', 'Horsepower', 'Fuel', 'Transmission', 'Offer Link']

        st.dataframe(
            table_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Price": st.column_config.NumberColumn("Price", format="€%.0f"),
                "Mileage (km)": st.column_config.NumberColumn("Mileage (km)", format="%d km"),
                "Offer Link": st.column_config.LinkColumn("Offer Link", display_text="Open Offer")
            }
        )