import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import base64
import os

# --- 1. CONFIGURACIÓN VISUAL ---
st.set_page_config(layout="wide", page_title="XTB Research Macro Dashboard")

st.markdown("""
<style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem;}
    h1, h2, h3, h4, p, div {font-family: 'Arial', sans-serif;}
    .modebar {display: none !important;}
    
    .stSelectbox label, .stNumberInput label, .stCheckbox label {
        color: #EAEAEA !important; 
        font-weight: bold;
        font-size: 14px;
    }
    div[data-testid="stCheckbox"] { margin-top: 5px; }
    
    /* Ajuste para tabla con scroll */
    [data-testid="stDataFrame"] { font-family: 'Arial', sans-serif; }
</style>
""", unsafe_allow_html=True)

# --- 2. CREDENCIALES ---
FRED_API_KEY = "a913b86d145620f86b690a7e4fe4538e"

# --- 3. CONFIGURACIÓN MAESTRA ---
# 'units': 'lin' (Niveles), 'pc1' (Variación % Anual)
INDICATOR_CONFIG = {
    # --- MERCADO LABORAL ---
    "Tasa Desempleo": {
        "fred_id": "UNRATE", "source": "U.S. BLS", "type": "macro", 
        "is_percent": True, "units": "lin"
    },
    "Tasa Participación Laboral": {
        "fred_id": "CIVPART", "source": "U.S. BLS", "type": "macro", 
        "is_percent": True, "units": "lin"
    },
    "Nóminas NFP (YoY%)": {
        "fred_id": "PAYEMS", "source": "U.S. BLS", "type": "macro", 
        "is_percent": True, "units": "pc1" 
    },
    "Initial Jobless Claims (YoY%)": {
        "fred_id": "ICSA", "source": "U.S. ETA", "type": "macro", 
        "is_percent": True, "units": "pc1"
    },
    
    # --- INFLACIÓN ---
    "PCE Price Index (YoY%)": { # Simplificado también para consistencia
        "fred_id": "PCEPI", "source": "U.S. BEA", "type": "macro", 
        "is_percent": True, "units": "pc1"
    },
    # CAMBIO REALIZADO AQUÍ: Abreviado a CPI Core
    "CPI Core (YoY%)": {
        "fred_id": "CPIAUCSL", "source": "U.S. BLS", "type": "macro", 
        "is_percent": True, "units": "pc1"
    },
    
    # --- DINERO Y ACTIVIDAD ---
    "Liquidez FED (YoY%)": {
        "fred_id": "WALCL", "source": "Federal Reserve", "type": "macro", 
        "is_percent": True, "units": "pc1"
    },
    "Oferta Monetaria M2 (YoY%)": {
        "fred_id": "M2SL", "source": "Federal Reserve", "type": "macro", 
        "is_percent": True, "units": "pc1"
    },
    "Producción Industrial (YoY%)": {
        "fred_id": "INDPRO", "source": "Federal Reserve", "type": "macro", 
        "is_percent": True, "units": "pc1"
    },
    
    # --- MERCADO FINANCIERO ---
    "Bono US 10Y": {
        "fred_id": "DGS10", "source": "Board of Governors", "type": "market", 
        "is_percent": True, "units": "lin"
    },
    "Bono US 2Y": {
        "fred_id": "DGS2", "source": "Board of Governors", "type": "market", 
        "is_percent": True, "units": "lin"
    },
    "Curva Tipos (10Y-2Y)": {
        "fred_id": "DGS10, DGS2", "source": "Board of Governors", "type": "market", 
        "is_percent": True, "units": "lin"
    },
    "Tasa FED": {
        "fred_id": "FEDFUNDS", "source": "Board of Governors", "type": "market", 
        "is_percent": True, "units": "lin"
    },
    "Volatilidad VIX": {
        "fred_id": "VIXCLS", "source": "CBOE", "type": "market", 
        "is_percent": False, "units": "lin"
    },
}

# --- 4. UTILIDADES ---
def get_local_logo_base64():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    possible_names = ["logo.png", "logo.jpg", "logo.jpeg", "logo.png.png"]
    for filename in possible_names:
        full_path = os.path.join(script_dir, filename)
        if os.path.exists(full_path):
            try:
                with open(full_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode()
                ext = "jpeg" if "jpg" in filename else "png"
                return f"data:image/{ext};base64,{encoded}"
            except: continue
    return ""

def get_month_name(month_num):
    meses = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 
             7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}
    return meses.get(month_num, '')

def get_format_settings(indicator_name):
    config = INDICATOR_CONFIG.get(indicator_name, {})
    is_pct = config.get("is_percent", False)
    # En gráfico usamos 2 decimales para limpieza visual
    if is_pct: return "%", ".2f"
    else: return "", ",.2f"

# --- 5. MOTOR DE DATOS ---
@st.cache_data(ttl=3600) 
def get_all_macro_data_long_history():
    start_date = "1980-01-01"
    df_master = pd.DataFrame()
    try:
        fred = Fred(api_key=FRED_API_KEY)
    except: return pd.DataFrame()

    with st.empty(): 
        series_to_fetch = {k: v for k, v in INDICATOR_CONFIG.items() if "," not in v["fred_id"]}
        
        for name, config in series_to_fetch.items():
            try:
                series = fred.get_series(config["fred_id"], observation_start=start_date, units=config["units"])
                temp = series.to_frame(name=name)
                if df_master.empty: df_master = temp
                else: df_master = df_master.join(temp, how='outer')
            except Exception: continue
    
    if not df_master.empty:
        df_master.index = pd.to_datetime(df_master.index)
        df_calc = df_master.ffill() 
        
        # Curva Tipos
        if 'Bono US 10Y' in df_calc.columns and 'Bono US 2Y' in df_calc.columns:
            df_master['Curva Tipos (10Y-2Y)'] = df_calc['Bono US 10Y'] - df_calc['Bono US 2Y']
            
    return df_master

# --- 6. FÁBRICA DE GRÁFICOS ---
def create_pro_chart(df, col1, col2=None, invert_y2=False, logo_data=""):
    COLOR_Y1 = "#002b49" 
    COLOR_Y2 = "#5ca6e5" 
    has_secondary = col2 is not None and col2 != "Ninguno"
    
    suffix1, fmt1 = get_format_settings(col1)
    
    valid_s1 = df[col1].dropna()
    start_date_plot = valid_s1.first_valid_index()
    if has_secondary:
        valid_s2 = df[col2].dropna()
        idx2 = valid_s2.first_valid_index()
        if start_date_plot and idx2: start_date_plot = min(start_date_plot, idx2)
        elif idx2: start_date_plot = idx2
    if start_date_plot:
        df = df[df.index >= start_date_plot]

    fig = make_subplots(specs=[[{"secondary_y": has_secondary}]])

    try:
        s1 = df[col1].dropna()
        if not s1.empty:
            last_v1 = s1.iloc[-1]
            fig.add_trace(go.Scatter(x=s1.index, y=s1, name=col1, line=dict(color=COLOR_Y1, width=2.5), mode='lines'), secondary_y=False)
            txt_val = f"{last_v1:,.2f}{suffix1}" if suffix1 == "%" else f"{last_v1:,.2f}"
            fig.add_annotation(
                x=s1.index[-1], y=last_v1, text=f" {txt_val}",
                xref="x", yref="y1", xanchor="left", showarrow=False,
                font=dict(color="white", size=11, weight="bold"),
                bgcolor=COLOR_Y1, borderpad=4, opacity=0.9
            )
    except: pass

    if has_secondary:
        suffix2, fmt2 = get_format_settings(col2)
        try:
            s2 = df[col2].dropna()
            if not s2.empty:
                last_v2 = s2.iloc[-1]
                fig.add_trace(go.Scatter(x=s2.index, y=s2, name=col2, line=dict(color=COLOR_Y2, width=2, dash='dash'), mode='lines'), secondary_y=True)
                txt_val2 = f"{last_v2:,.2f}{suffix2}" if suffix2 == "%" else f"{last_v2:,.2f}"
                fig.add_annotation(
                    x=s2.index[-1], y=last_v2, text=f" {txt_val2}",
                    xref="x", yref="y2", xanchor="left", showarrow=False,
                    font=dict(color="white", size=11, weight="bold"),
                    bgcolor=COLOR_Y2, borderpad=4, opacity=0.9
                )
        except: pass

    title_clean_1 = f"{col1} EE.UU" if "Desempleo" in col1 else col1
    title_text = f"<b>{title_clean_1}</b>"
    if has_secondary: title_text += f" vs <b>{col2}</b>"

    fig.update_layout(
        title=dict(text=title_text, x=0.5, y=0.98, xanchor='center', font=dict(family="Arial", size=20, color="black")),
        plot_bgcolor="white", paper_bgcolor="white", height=650,
        margin=dict(t=120, r=80, l=80, b=100),
        showlegend=True,
        legend=dict(orientation="h", y=1.15, x=0, xanchor='left', bgcolor="rgba(0,0,0,0)", font=dict(color="#333")),
        images=[dict(source=logo_data, xref="paper", yref="paper", x=1, y=1.22, sizex=0.12, sizey=0.12, xanchor="right", yanchor="top")]
    )

    fig.update_xaxes(showgrid=False, linecolor="#333", linewidth=2, tickfont=dict(color="#333", size=12), ticks="outside")
    fig.update_yaxes(
        title=f"<b>{col1}</b>", title_font=dict(color=COLOR_Y1), 
        showgrid=True, gridcolor="#f0f0f0", gridwidth=1, 
        linecolor="white", tickfont=dict(color=COLOR_Y1, weight="bold"),
        ticksuffix=suffix1, tickformat=fmt1,
        zeroline=False, secondary_y=False
    )
    
    if has_secondary:
        y2_title = f"<b>{col2} - Invertido</b>" if invert_y2 else f"<b>{col2}</b>"
        fig.update_yaxes(
            title=y2_title, title_font=dict(color=COLOR_Y2), 
            showgrid=False, tickfont=dict(color=COLOR_Y2),
            ticksuffix=suffix2, tickformat=fmt2,
            autorange="reversed" if invert_y2 else True, secondary_y=True
        )

    recessions = [("1990-07-01", "1991-03-01"), ("2001-03-01", "2001-11-01"), ("2007-12-01", "2009-06-01"), ("2020-02-01", "2020-04-01")]
    df_start_date = df.index.min()
    for start, end in recessions:
        try:
            if pd.Timestamp(end) > df_start_date:
                v_start = max(pd.Timestamp(start), df_start_date)
                fig.add_vrect(
                    x0=v_start, x1=end, 
                    fillcolor="#e6e6e6", opacity=0.5, layer="below", line_width=0,
                    yref="paper", y0=0, y1=1
                )
        except: pass
        
    meta1 = INDICATOR_CONFIG.get(col1, {})
    fred_id1 = meta1.get("fred_id", "N/A")
    db_text = f"FRED {fred_id1}"
    if has_secondary:
        meta2 = INDICATOR_CONFIG.get(col2, {})
        fred_id2 = meta2.get("fred_id", "N/A")
        if fred_id2 != fred_id1: db_text += f", FRED {fred_id2}"

    fig.add_annotation(x=0, y=-0.14, text=f"Database: {db_text}", xref="paper", yref="paper", showarrow=False, font=dict(size=11, color="gray"), xanchor="left")
    fig.add_annotation(x=1, y=-0.14, text="Source: <b>XTB Research</b>", xref="paper", yref="paper", showarrow=False, font=dict(size=11, color="black"), xanchor="right")

    return fig

# --- 7. INTERFAZ PRINCIPAL ---
st.title("XTB Research Macro Dashboard")

logo_b64 = get_local_logo_base64()
df_full = get_all_macro_data_long_history()

if not df_full.empty:
    available_indicators = sorted(df_full.columns.tolist())
    
    st.markdown("#### ⚙️ Configuración del Análisis")
    c1, c2, c3, c4 = st.columns([3, 3, 1, 1])
    
    with c1:
        y1 = st.selectbox("Eje Principal", options=available_indicators, index=available_indicators.index("Tasa Desempleo") if "Tasa Desempleo" in available_indicators else 0)
    with c2:
        def_idx = available_indicators.index("Tasa Participación Laboral") if "Tasa Participación Laboral" in available_indicators else 0
        y2 = st.selectbox("Eje Secundario", options=["Ninguno"] + available_indicators, index=def_idx + 1)
    with c3:
        start_year = st.number_input("Año Mínimo", min_value=1980, max_value=2024, value=2000, step=1)
    with c4:
        st.write("") 
        st.write("")
        inv = st.checkbox("Invertir Eje Der.", value=True)

    start_dt_user = pd.to_datetime(f"{start_year}-01-01")
    df_plot = df_full[df_full.index >= start_dt_user]
    
    st.divider()
    
    fig = create_pro_chart(df_plot, y1, y2, inv, logo_b64)
    st.plotly_chart(fig, use_container_width=True)
    
    meta_info = INDICATOR_CONFIG.get(y1, {"type": "market"})
    
    if meta_info.get("type") == "macro":
        st.divider()
        st.subheader(f"📅 Histórico: {y1}")
        
        df_cal = df_plot[[y1]].dropna().sort_index(ascending=False)
        df_cal['Anterior'] = df_cal[y1].shift(-1)
        
        df_cal.index.name = 'Fecha_Base'
        df_cal = df_cal.reset_index()
        
        df_cal['Mes_Ref'] = df_cal['Fecha_Base'].dt.month
        df_cal['Referencia'] = df_cal['Mes_Ref'].apply(get_month_name) + " " + df_cal['Fecha_Base'].dt.year.astype(str)
        
        df_cal['Fecha_Pub'] = df_cal['Fecha_Base'] + pd.DateOffset(months=1)
        df_cal['Mes_Pub'] = df_cal['Fecha_Pub'].dt.month
        df_cal['Publicación (Est.)'] = df_cal['Mes_Pub'].apply(get_month_name) + " " + df_cal['Fecha_Pub'].dt.year.astype(str)
        
        df_cal = df_cal.rename(columns={y1: 'Actual'})
        
        is_pct_table = INDICATOR_CONFIG.get(y1, {}).get("is_percent", False)

        def fmt_num_table(x):
            if pd.isna(x): return ""
            if is_pct_table: return f"{x:.4f}%" # Alta precisión
            else: return f"{x:,.4f}"

        df_cal['Actual'] = df_cal['Actual'].apply(fmt_num_table)
        df_cal['Anterior'] = df_cal['Anterior'].apply(fmt_num_table)
        
        df_display = df_cal[['Referencia', 'Publicación (Est.)', 'Actual', 'Anterior']].dropna(subset=['Anterior'])

        st.dataframe(
            df_display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Referencia": st.column_config.TextColumn("Referencia (Periodo)", width="medium"),
                "Publicación (Est.)": st.column_config.TextColumn("Publicación (Aprox)", width="medium"),
                "Actual": st.column_config.TextColumn("Dato Actual", width="small"),
                "Anterior": st.column_config.TextColumn("Dato Anterior", width="small"),
            }
        )
        st.caption(f"Nota: Datos oficiales completos (sin redondeo). 'Referencia' es el mes medido.")
    else:
        st.caption(f"ℹ️ Tabla no disponible para datos de alta frecuencia ({y1}).")

else:
    st.error("Error al cargar los datos.")