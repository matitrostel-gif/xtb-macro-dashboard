import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
import base64
import os
import google.generativeai as genai

# --- 1. CONFIGURACIÓN VISUAL ---
st.set_page_config(layout="wide", page_title="XTB Research Macro Dashboard")

st.markdown("""
<style>
    .block-container {padding-top: 1rem; padding-bottom: 3rem;}
    h1, h2, h3, h4, p, div {font-family: 'Arial', sans-serif;}
    .modebar {display: none !important;}
    
    .stSelectbox label, .stNumberInput label, .stCheckbox label, .stTextInput label {
        color: #EAEAEA !important; 
        font-weight: bold;
        font-size: 13px;
    }
    div[data-testid="stCheckbox"] { margin-top: 5px; }
    [data-testid="stDataFrame"] { font-family: 'Arial', sans-serif; }
    
    [data-testid="stFileUploader"] {
        padding: 10px;
        border: 1px dashed #4a4a4a;
        border-radius: 5px;
        margin-bottom: 20px;
    }
    
    /* Estilos TABS en Sidebar */
    .stTabs [data-baseweb="tab-list"] { gap: 2px; }
    .stTabs [data-baseweb="tab"] {
        padding: 4px 8px;
        font-size: 11px;
        background-color: #262730;
        color: #ffffff;
        border-radius: 4px 4px 0px 0px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ff4b4b;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. CREDENCIALES ---
FRED_API_KEY = "a913b86d145620f86b690a7e4fe4538e"

# --- 3. CONFIGURACIÓN MAESTRA ---
INDICATOR_CONFIG = {
    # --- MERCADO LABORAL ---
    "Tasa Desempleo": {"fred_id": "UNRATE", "source": "U.S. BLS", "type": "macro", "is_percent": True, "units": "lin"},
    "Tasa Participación Laboral": {"fred_id": "CIVPART", "source": "U.S. BLS", "type": "macro", "is_percent": True, "units": "lin"},
    "Nóminas NFP (YoY%)": {"fred_id": "PAYEMS", "source": "U.S. BLS", "type": "macro", "is_percent": True, "units": "pc1"},
    "Initial Jobless Claims (YoY%)": {"fred_id": "ICSA", "source": "U.S. ETA", "type": "macro", "is_percent": True, "units": "pc1"},
    
    # --- INFLACIÓN ---
    "PCE Price Index (YoY%)": {"fred_id": "PCEPI", "source": "U.S. BEA", "type": "macro", "is_percent": True, "units": "pc1"},
    "CPI Core (YoY%)": {"fred_id": "CPIAUCSL", "source": "U.S. BLS", "type": "macro", "is_percent": True, "units": "pc1"},
    
    # --- DINERO Y ACTIVIDAD ---
    "Liquidez FED (YoY%)": {"fred_id": "WALCL", "source": "Federal Reserve", "type": "macro", "is_percent": True, "units": "pc1"},
    "Oferta Monetaria M2 (YoY%)": {"fred_id": "M2SL", "source": "Federal Reserve", "type": "macro", "is_percent": True, "units": "pc1"},
    "Producción Industrial (YoY%)": {"fred_id": "INDPRO", "source": "Federal Reserve", "type": "macro", "is_percent": True, "units": "pc1"},
    
    # --- MERCADO FINANCIERO ---
    "Bono US 10Y": {"fred_id": "DGS10", "source": "Board of Governors", "type": "market", "is_percent": True, "units": "lin"},
    "Bono US 2Y": {"fred_id": "DGS2", "source": "Board of Governors", "type": "market", "is_percent": True, "units": "lin"},
    "Curva Tipos (10Y-2Y)": {"fred_id": "DGS10, DGS2", "source": "Board of Governors", "type": "market", "is_percent": True, "units": "lin"},
    "Tasa FED": {"fred_id": "FEDFUNDS", "source": "Board of Governors", "type": "market", "is_percent": True, "units": "lin"},
    "Volatilidad VIX": {"fred_id": "VIXCLS", "source": "CBOE", "type": "market", "is_percent": False, "units": "lin"},
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
    if indicator_name not in INDICATOR_CONFIG:
        if "%" in indicator_name: is_pct = True
        else: is_pct = False
    if is_pct: return "%", ".2f"
    else: return "", ",.2f"

# --- 5. MOTOR DE DATOS ---
@st.cache_data(ttl=60) 
def get_all_macro_data_long_history():
    start_date = "1970-01-01" 
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
        if 'Bono US 10Y' in df_calc.columns and 'Bono US 2Y' in df_calc.columns:
            df_master['Curva Tipos (10Y-2Y)'] = df_calc['Bono US 10Y'] - df_calc['Bono US 2Y']
            
    return df_master

# --- 6. FÁBRICA DE GRÁFICOS (CONFIGURABLE) ---
def create_pro_chart(df, col1, col2=None, invert_y2=False, logo_data="", config_format=None):
    
    if config_format is None:
        config_format = {"color": "#002b49", "width": 2.5, "type": "Línea", "rec": True}

    COLOR_Y1 = config_format["color"]
    COLOR_Y2 = "#5ca6e5" 
    has_secondary = col2 is not None and col2 != "Ninguno"
    
    suffix1, fmt1 = get_format_settings(col1)
    
    # 1. FILTRADO DE DATOS (ELIMINAR FUTURO)
    # Cortamos el DF para que no tenga nada posterior a HOY
    df = df[df.index <= datetime.datetime.now()]
    
    fig = make_subplots(specs=[[{"secondary_y": has_secondary}]])
    hover_fmt = "%{x|%A, %b %d, %Y}"

    # EJE 1
    try:
        s1 = df[col1].dropna()
        if not s1.empty:
            last_v1 = s1.iloc[-1]
            
            if config_format["type"] == "Línea":
                fig.add_trace(go.Scatter(
                    x=s1.index, y=s1, name=col1, 
                    line=dict(color=COLOR_Y1, width=config_format["width"]), 
                    mode='lines',
                    hovertemplate=f"<b>{col1}</b><br>{hover_fmt}: %{{y:,.2f}}{suffix1}<extra></extra>"
                ), secondary_y=False)
            elif config_format["type"] == "Barra":
                 fig.add_trace(go.Bar(
                    x=s1.index, y=s1, name=col1, 
                    marker=dict(color=COLOR_Y1),
                    hovertemplate=f"<b>{col1}</b><br>{hover_fmt}: %{{y:,.2f}}{suffix1}<extra></extra>"
                ), secondary_y=False)
            elif config_format["type"] == "Área":
                 fig.add_trace(go.Scatter(
                    x=s1.index, y=s1, name=col1, 
                    line=dict(color=COLOR_Y1, width=config_format["width"]), 
                    fill='tozeroy', mode='lines',
                    hovertemplate=f"<b>{col1}</b><br>{hover_fmt}: %{{y:,.2f}}{suffix1}<extra></extra>"
                ), secondary_y=False)
            
            txt_val = f"{last_v1:,.2f}{suffix1}" if suffix1 == "%" else f"{last_v1:,.2f}"
            fig.add_annotation(
                x=s1.index[-1], y=last_v1, text=f" {txt_val}",
                xref="x", yref="y1", xanchor="left", showarrow=False,
                font=dict(color="white", size=11, weight="bold"),
                bgcolor=COLOR_Y1, borderpad=4, opacity=0.9
            )
    except: pass

    # EJE 2
    if has_secondary:
        suffix2, fmt2 = get_format_settings(col2)
        try:
            s2 = df[col2].dropna()
            if not s2.empty:
                last_v2 = s2.iloc[-1]
                fig.add_trace(go.Scatter(
                    x=s2.index, y=s2, name=col2, 
                    line=dict(color=COLOR_Y2, width=2, dash='dash'), 
                    mode='lines',
                    hovertemplate=f"<b>{col2}</b><br>{hover_fmt}: %{{y:,.2f}}{suffix2}<extra></extra>"
                ), secondary_y=True)
                
                txt_val2 = f"{last_v2:,.2f}{suffix2}" if suffix2 == "%" else f"{last_v2:,.2f}"
                fig.add_annotation(
                    x=s2.index[-1], y=last_v2, text=f" {txt_val2}",
                    xref="x", yref="y2", xanchor="left", showarrow=False,
                    font=dict(color="white", size=11, weight="bold"),
                    bgcolor=COLOR_Y2, borderpad=4, opacity=0.9
                )
        except: pass

    title_clean_1 = f"{col1} EE.UU" if "Desempleo" in col1 else col1
    if col1 not in INDICATOR_CONFIG: title_clean_1 = col1 
    
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

    # 2. DEFINICIÓN DEL RANGO INICIAL EXACTO (1 AÑO)
    # Esto evita que Plotly muestre 2026. Forzamos la vista a [Hoy-365, Hoy]
    fin_rango = datetime.datetime.now()
    inicio_rango = fin_rango - datetime.timedelta(days=365)

    # BOTONES DE RANGO (CON FIX DE FECHAS)
    fig.update_xaxes(
        range=[inicio_rango, fin_rango], # <--- AQUÍ ESTÁ EL ARREGLO VISUAL INICIAL
        showgrid=False, linecolor="#333", linewidth=2, tickfont=dict(color="#333", size=12), ticks="outside",
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=365, label="1Y", step="day", stepmode="backward"), # Usamos días para precisión
                dict(count=365*5, label="5Y", step="day", stepmode="backward"),
                dict(step="all", label="Max")
            ]),
            bgcolor="white", activecolor="#e6e6e6", x=0, y=1, xanchor='left', yanchor='bottom',
            font=dict(size=11, color="#333333") 
        )
    )
    
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

    if config_format["rec"]:
        recessions = [("1990-07-01", "1991-03-01"), ("2001-03-01", "2001-11-01"), ("2007-12-01", "2009-06-01"), ("2020-02-01", "2020-04-01")]
        if not df.empty:
            df_start = df.index.min()
            df_end = df.index.max()
            for start, end in recessions:
                try:
                    s_dt = pd.Timestamp(start)
                    e_dt = pd.Timestamp(end)
                    if e_dt > df_start and s_dt < df_end:
                        v_s = max(s_dt, df_start)
                        v_e = min(e_dt, df_end)
                        fig.add_vrect(
                            x0=v_s, x1=v_e, 
                            fillcolor="#e6e6e6", opacity=0.5, layer="below", line_width=0,
                            yref="paper", y0=0, y1=1
                        )
                except: pass
        
    meta1 = INDICATOR_CONFIG.get(col1, {})
    fred_id1 = meta1.get("fred_id", "External Data" if col1 not in INDICATOR_CONFIG else "N/A")
    db_text = f"{fred_id1}" if col1 in INDICATOR_CONFIG else "Proprietary Data"
    
    if has_secondary:
        meta2 = INDICATOR_CONFIG.get(col2, {})
        fred_id2 = meta2.get("fred_id", "External Data" if col2 not in INDICATOR_CONFIG else "N/A")
        if fred_id2 != fred_id1: db_text += f", {fred_id2}"
    
    if "UNRATE" in db_text or "DGS" in db_text: db_text = "FRED " + db_text

    fig.add_annotation(x=0, y=-0.14, text=f"Database: {db_text}", xref="paper", yref="paper", showarrow=False, font=dict(size=11, color="gray"), xanchor="left")
    fig.add_annotation(x=1, y=-0.14, text="Source: <b>XTB Research</b>", xref="paper", yref="paper", showarrow=False, font=dict(size=11, color="black"), xanchor="right")

    return fig

# --- 7. INTERFAZ PRINCIPAL ---
st.title("XTB Research Macro Dashboard")

# --- SIDEBAR COLAPSABLE ---
with st.sidebar:
    st.header("📂 Datos Propios")
    # RESTAURADO: El buzón de Excel vuelve a estar aquí arriba, visible siempre
    uploaded_file = st.file_uploader("Subir Excel (.xlsx)", type=["xlsx"])
    
    st.divider()
    
    st.header("🛠️ Configuración & Edición")
    
    # Panel de Edición (Tabs)
    tab_edit, tab_add, tab_fmt = st.tabs(["EDIT LINE", "ADD LINE", "FORMAT"])
    
    with tab_edit:
        st.caption("Configurar Ejes")
        y1_sel = st.selectbox("Eje Principal (Izq)", options=sorted(INDICATOR_CONFIG.keys()), index=0)
        y2_sel = st.selectbox("Eje Secundario (Der)", options=["Ninguno"] + sorted(INDICATOR_CONFIG.keys()), index=0)
        invert_y2 = st.checkbox("Invertir Eje Der.", value=True)
        
    with tab_add:
        st.caption("Configuración Extra")
        st.info("Para subir datos, usa el cargador 'Datos Propios' arriba.")
        
    with tab_fmt:
        st.caption("Estilo Visual")
        chart_type = st.selectbox("Tipo", ["Línea", "Barra", "Área"])
        chart_color = st.color_picker("Color Principal", "#002b49")
        chart_width = st.slider("Grosor", 1.0, 5.0, 2.5)
        chart_rec = st.checkbox("Recesiones", value=True)
        config_visual = {"type": chart_type, "color": chart_color, "width": chart_width, "rec": chart_rec}

    st.divider()
    
    st.header("🤖 Analista IA")
    gemini_key = st.text_input("Gemini API Key:", type="password")
    if gemini_key:
        genai.configure(api_key=gemini_key)
        st.success("Conectado")

logo_b64 = get_local_logo_base64()
df_fred = get_all_macro_data_long_history()

# --- FUSIÓN DE DATOS ---
if uploaded_file is not None:
    try:
        df_user = pd.read_excel(uploaded_file)
        date_col = df_user.columns[0]
        df_user[date_col] = pd.to_datetime(df_user[date_col])
        df_user = df_user.set_index(date_col)
        df_user = df_user.select_dtypes(include=['number'])
        if not df_fred.empty: df_full = df_fred.join(df_user, how='outer')
        else: df_full = df_user
        st.sidebar.success(f"Excel: {len(df_user.columns)} series.")
    except Exception as e:
        st.sidebar.error(f"Error Excel: {e}")
        df_full = df_fred
else:
    df_full = df_fred

if not df_full.empty:
    fred_cols = sorted([c for c in df_full.columns if c in INDICATOR_CONFIG])
    user_cols = sorted([c for c in df_full.columns if c not in INDICATOR_CONFIG])
    available_indicators = fred_cols + user_cols
    
    # --- GEMINI CHAT ---
    if gemini_key:
        with st.sidebar:
            user_question = st.text_area("Preguntar a IA:", placeholder="¿Qué ves en el gráfico?")
            if st.button("Analizar"):
                if user_question:
                    with st.spinner("Pensando..."):
                        try:
                            model = genai.GenerativeModel('gemini-pro') 
                            prompt = f"Analiza: {user_question}. Datos recientes: {df_full.tail(20).to_csv()}"
                            response = model.generate_content(prompt)
                            st.info(response.text)
                        except: st.error("Error IA")

    # --- ZONA PRINCIPAL (GRÁFICO GIGANTE) ---
    fig = create_pro_chart(df_full, y1_sel, y2_sel, invert_y2, logo_b64, config_visual)
    st.plotly_chart(fig, use_container_width=True)
    
    # --- TABLA HISTÓRICA (LIMPIA Y CONDICIONAL) ---
    st.divider()

    meta_info = INDICATOR_CONFIG.get(y1_sel, {"type": "market"}) 
    
    # Si viene del Excel del usuario o es tipo 'macro', mostramos tabla
    is_user_data = y1_sel not in INDICATOR_CONFIG
    is_macro_data = (meta_info.get("type") == "macro")
    show_full_table = is_macro_data or is_user_data

    if show_full_table:
        st.subheader(f"📅 Histórico: {y1_sel}")
        
        start_dt_table = pd.to_datetime("2020-01-01")
        df_table_view = df_full[df_full.index >= start_dt_table]
        
        df_cal = df_table_view[[y1_sel]].dropna().sort_index(ascending=False)
        df_cal['Anterior'] = df_cal[y1_sel].shift(-1)
        
        df_cal.index.name = 'Fecha_Base'
        df_cal = df_cal.reset_index()
        
        df_cal['Mes_Ref'] = df_cal['Fecha_Base'].dt.month
        df_cal['Referencia'] = df_cal['Mes_Ref'].apply(get_month_name) + " " + df_cal['Fecha_Base'].dt.year.astype(str)
        
        df_cal['Fecha_Pub'] = df_cal['Fecha_Base'] + pd.DateOffset(months=1)
        df_cal['Mes_Pub'] = df_cal['Fecha_Pub'].dt.month
        df_cal['Publicación (Est.)'] = df_cal['Mes_Pub'].apply(get_month_name) + " " + df_cal['Fecha_Pub'].dt.year.astype(str)
        
        df_cal = df_cal.rename(columns={y1_sel: 'Actual'})
        
        is_pct_table = meta_info.get("is_percent", False)
        def fmt_num_table(x):
            if pd.isna(x): return ""
            if is_pct_table: return f"{x:.4f}%" 
            else: return f"{x:,.4f}"

        df_cal['Actual'] = df_cal['Actual'].apply(fmt_num_table)
        df_cal['Anterior'] = df_cal['Anterior'].apply(fmt_num_table)
        
        df_display = df_cal[['Referencia', 'Publicación (Est.)', 'Actual', 'Anterior']].dropna(subset=['Anterior'])

        st.dataframe(
            df_display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Referencia": st.column_config.TextColumn("Referencia", width="medium"),
                "Publicación (Est.)": st.column_config.TextColumn("Publicación", width="medium"),
                "Actual": st.column_config.TextColumn("Dato Actual", width="small"),
                "Anterior": st.column_config.TextColumn("Dato Anterior", width="small"),
            }
        )
    else:
        st.caption(f"ℹ️ Tabla no disponible para datos de alta frecuencia ({y1_sel}).")

else:
    st.error("Error al cargar los datos.")