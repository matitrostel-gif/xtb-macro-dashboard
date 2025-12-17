import streamlit as st
import pandas as pd
from openbb import obb
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
    [data-testid="stDataFrame"] { font-family: 'Arial', sans-serif; }
</style>
""", unsafe_allow_html=True)

# --- 2. CREDENCIALES ---
obb.user.credentials.fred_api_key = "a913b86d145620f86b690a7e4fe4538e"

# --- 3. CONFIGURACIÓN MAESTRA ---
INDICATOR_CONFIG = {
    "Tasa Desempleo": {"fred_id": "UNRATE", "source": "U.S. BLS", "type": "macro"},
    "Tasa Participación Laboral": {"fred_id": "CIVPART", "source": "U.S. BLS", "type": "macro"},
    "Nóminas NFP": {"fred_id": "PAYEMS", "source": "U.S. BLS", "type": "macro"},
    "Initial Jobless Claims": {"fred_id": "ICSA", "source": "U.S. ETA", "type": "macro"},
    "Inflación PCE": {"fred_id": "PCEPI", "source": "U.S. BEA", "type": "macro"},
    "IPC Core": {"fred_id": "CPIAUCSL", "source": "U.S. BLS", "type": "macro"},
    "Liquidez FED": {"fred_id": "WALCL", "source": "Federal Reserve", "type": "macro"},
    "Oferta Monetaria M2": {"fred_id": "M2SL", "source": "Federal Reserve", "type": "macro"},
    "Producción Industrial": {"fred_id": "INDPRO", "source": "Federal Reserve", "type": "macro"},
    
    # Datos de Mercado (Sin Tabla)
    "Bono US 10Y": {"fred_id": "DGS10", "source": "Board of Governors", "type": "market"},
    "Bono US 2Y": {"fred_id": "DGS2", "source": "Board of Governors", "type": "market"},
    "Tasa FED": {"fred_id": "FEDFUNDS", "source": "Board of Governors", "type": "market"},
    "Volatilidad VIX": {"fred_id": "VIXCLS", "source": "CBOE", "type": "market"},
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

# --- 5. MOTOR DE DATOS ---
@st.cache_data(ttl=3600) 
def get_all_macro_data_long_history():
    start_date = "1980-01-01"
    df_master = pd.DataFrame()
    
    with st.empty(): 
        for name, config in INDICATOR_CONFIG.items():
            try:
                temp = obb.economy.fred_series(config["fred_id"], start_date=start_date).to_df()
                temp.columns = [name]
                if df_master.empty: df_master = temp
                else: df_master = df_master.join(temp, how='outer')
            except: continue
    
    if not df_master.empty:
        df_master.index = pd.to_datetime(df_master.index)
        df_calc = df_master.ffill() 
        
        # Inflación Calculada
        if 'Inflación PCE' in df_calc.columns:
            name_inf = 'Inflación PCE (YoY%)'
            df_master[name_inf] = df_calc['Inflación PCE'].pct_change(12) * 100
            INDICATOR_CONFIG[name_inf] = {"source": "U.S. BEA", "type": "macro"}
            
        # Curva Tipos
        if 'Bono US 10Y' in df_calc.columns and 'Bono US 2Y' in df_calc.columns:
            name_curve = 'Curva Tipos (10Y-2Y)'
            df_master[name_curve] = df_calc['Bono US 10Y'] - df_calc['Bono US 2Y']
            INDICATOR_CONFIG[name_curve] = {"source": "Board of Governors", "type": "market"}
            
    return df_master

# --- 6. FÁBRICA DE GRÁFICOS ---
def create_pro_chart(df, col1, col2=None, invert_y2=False, logo_data=""):
    COLOR_Y1 = "#002b49" 
    COLOR_Y2 = "#5ca6e5" 
    has_secondary = col2 is not None and col2 != "Ninguno"
    
    # Smart Trim
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

    # Serie 1
    try:
        s1 = df[col1].dropna()
        if not s1.empty:
            last_v1 = s1.iloc[-1]
            fig.add_trace(go.Scatter(x=s1.index, y=s1, name=col1, line=dict(color=COLOR_Y1, width=2.5), mode='lines'), secondary_y=False)
            fig.add_annotation(
                x=s1.index[-1], y=last_v1, text=f" {last_v1:.2f}%",
                xref="x", yref="y1", xanchor="left", showarrow=False,
                font=dict(color="white", size=11, weight="bold"),
                bgcolor=COLOR_Y1, borderpad=4, opacity=0.9
            )
    except: pass

    # Serie 2
    if has_secondary:
        try:
            s2 = df[col2].dropna()
            if not s2.empty:
                last_v2 = s2.iloc[-1]
                fig.add_trace(go.Scatter(x=s2.index, y=s2, name=col2, line=dict(color=COLOR_Y2, width=2, dash='dash'), mode='lines'), secondary_y=True)
                fig.add_annotation(
                    x=s2.index[-1], y=last_v2, text=f" {last_v2:.2f}%",
                    xref="x", yref="y2", xanchor="left", showarrow=False,
                    font=dict(color="white", size=11, weight="bold"),
                    bgcolor=COLOR_Y2, borderpad=4, opacity=0.9
                )
        except: pass

    # Título y Layout
    title_clean_1 = f"{col1} EE.UU" if "Desempleo" in col1 else col1
    title_text = f"<b>{title_clean_1}</b>"
    if has_secondary: title_text += f" vs <b>{col2}</b>"

    fig.update_layout(
        title=dict(text=title_text, x=0.5, y=0.95, xanchor='center', font=dict(family="Arial", size=20, color="black")),
        plot_bgcolor="white", paper_bgcolor="white", height=650,
        margin=dict(t=120, r=80, l=80, b=100),
        showlegend=True,
        legend=dict(orientation="h", y=1.05, x=0, xanchor='left', bgcolor="rgba(0,0,0,0)", font=dict(color="#333")),
        images=[dict(source=logo_data, xref="paper", yref="paper", x=1, y=1.22, sizex=0.18, sizey=0.18, xanchor="right", yanchor="top")]
    )

    fig.update_xaxes(showgrid=False, linecolor="#333", linewidth=2, tickfont=dict(color="#333", size=12), ticks="outside")
    fig.update_yaxes(title=f"<b>{col1}</b>", title_font=dict(color=COLOR_Y1), showgrid=True, gridcolor="#f0f0f0", gridwidth=1, linecolor="white", tickfont=dict(color=COLOR_Y1, weight="bold"), ticksuffix="%", zeroline=False, secondary_y=False)
    
    if has_secondary:
        y2_title = f"<b>{col2} - Invertido</b>" if invert_y2 else f"<b>{col2}</b>"
        fig.update_yaxes(title=y2_title, title_font=dict(color=COLOR_Y2), showgrid=False, tickfont=dict(color=COLOR_Y2), ticksuffix="%", autorange="reversed" if invert_y2 else True, secondary_y=True)

    recessions = [("1990-07-01", "1991-03-01"), ("2001-03-01", "2001-11-01"), ("2007-12-01", "2009-06-01"), ("2020-02-01", "2020-04-01")]
    df_start_date = df.index.min()
    for start, end in recessions:
        try:
            if pd.Timestamp(end) > df_start_date:
                v_start = max(pd.Timestamp(start), df_start_date)
                fig.add_vrect(x0=v_start, x1=end, fillcolor="#e6e6e6", opacity=0.5, layer="below", line_width=0)
        except: pass
        
    meta1 = INDICATOR_CONFIG.get(col1, {"source": "FRED"})
    source1 = meta1.get("source", "FRED")
    sources_text = source1
    if has_secondary:
        meta2 = INDICATOR_CONFIG.get(col2, {"source": "FRED"})
        source2 = meta2.get("source", "FRED")
        if source2 != source1: sources_text = f"{source1}, {source2}"

    fig.add_annotation(x=0, y=-0.14, text=f"Database: {sources_text}", xref="paper", yref="paper", showarrow=False, font=dict(size=11, color="gray"), xanchor="left")
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
    
    # --- CALENDARIO HISTÓRICO (CORREGIDO) ---
    meta_info = INDICATOR_CONFIG.get(y1, {"type": "market"})
    
    if meta_info.get("type") == "macro":
        st.divider()
        st.subheader(f"Histórico: {y1}")
        
        # 1. Obtener datos y preparar
        df_cal = df_plot[[y1]].dropna().sort_index(ascending=False).head(12)
        df_cal['Anterior'] = df_cal[y1].shift(-1)
        
        # --- AQUÍ ESTÁ EL ARREGLO DEL ERROR ---
        # Asignamos nombre explícito al índice antes de resetear
        df_cal.index.name = 'Fecha_Base'
        df_cal = df_cal.reset_index()
        
        # Ahora usamos 'Fecha_Base' con seguridad
        df_cal['Mes_Ref'] = df_cal['Fecha_Base'].dt.month
        df_cal['Referencia'] = df_cal['Mes_Ref'].apply(get_month_name) + " " + df_cal['Fecha_Base'].dt.year.astype(str)
        
        # Estimación de Publicación (Mes siguiente)
        df_cal['Fecha_Pub'] = df_cal['Fecha_Base'] + pd.DateOffset(months=1)
        df_cal['Mes_Pub'] = df_cal['Fecha_Pub'].dt.month
        df_cal['Publicación (Est.)'] = df_cal['Mes_Pub'].apply(get_month_name) + " " + df_cal['Fecha_Pub'].dt.year.astype(str)
        
        df_cal = df_cal.rename(columns={y1: 'Actual'})
        
        # Formateo
        def fmt_num(x):
            if pd.isna(x): return ""
            if "Nóminas" in y1 or "Claims" in y1 or "Liquidez" in y1: return f"{x:,.0f}"
            return f"{x:.2f}%"

        df_cal['Actual'] = df_cal['Actual'].apply(fmt_num)
        df_cal['Anterior'] = df_cal['Anterior'].apply(fmt_num)
        
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
        st.caption(f"Nota: 'Referencia' es el mes medido. 'Publicación' es el mes estimado de salida del reporte.")
    else:
        st.caption(f"ℹ️ Tabla no disponible para datos de alta frecuencia ({y1}).")

else:
    st.error("Error al cargar los datos.")