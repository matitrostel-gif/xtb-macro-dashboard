import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
from datetime import timedelta
import base64
import os
import google.generativeai as genai

# --- 1. CONFIGURACIÓN VISUAL ---
st.set_page_config(layout="wide", page_title="XTB Research Macro Dashboard")

st.markdown("""
<style>
    .block-container {padding-top: 1rem; padding-bottom: 3rem;}
    h1, h2, h3, h4, p, div {font-family: 'Arial', sans-serif;}
    
    /* SE ELIMINÓ LA LÍNEA QUE OCULTABA LA BARRA DE HERRAMIENTAS */
    
    .stSelectbox label, .stNumberInput label, .stCheckbox label, .stTextInput label, .stTextArea label, .stColorPicker label, .stSlider label {
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
        margin-bottom: 15px;
    }
    
    .stTabs [data-baseweb="tab-list"] { gap: 2px; }
    .stTabs [data-baseweb="tab"] {
        padding: 6px 10px;
        font-size: 12px;
        background-color: #262730;
        color: #ffffff;
        border-radius: 4px 4px 0px 0px;
        flex-grow: 1;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ff4b4b;
        color: white;
    }
    
    hr { margin-top: 5px; margin-bottom: 10px; border-color: #444; }
</style>
""", unsafe_allow_html=True)

# --- 2. CREDENCIALES ---
FRED_API_KEY = "a913b86d145620f86b690a7e4fe4538e"

# --- 3. CONFIGURACIÓN MAESTRA ---
INDICATOR_CONFIG = {
    "Tasa Desempleo": {"fred_id": "UNRATE", "type": "macro", "is_percent": True, "units": "lin"},
    "Tasa Participación": {"fred_id": "CIVPART", "type": "macro", "is_percent": True, "units": "lin"},
    "Nóminas NFP (YoY%)": {"fred_id": "PAYEMS", "type": "macro", "is_percent": True, "units": "pc1"},
    "Initial Claims": {"fred_id": "ICSA", "type": "macro", "is_percent": True, "units": "pc1"},
    "PCE Price Index": {"fred_id": "PCEPI", "type": "macro", "is_percent": True, "units": "pc1"},
    "CPI Core": {"fred_id": "CPIAUCSL", "type": "macro", "is_percent": True, "units": "pc1"},
    "Liquidez FED": {"fred_id": "WALCL", "type": "macro", "is_percent": True, "units": "pc1"},
    "M2 Money Supply": {"fred_id": "M2SL", "type": "macro", "is_percent": True, "units": "pc1"},
    "Producción Ind.": {"fred_id": "INDPRO", "type": "macro", "is_percent": True, "units": "pc1"},
    "Bono US 10Y": {"fred_id": "DGS10", "type": "market", "is_percent": True, "units": "lin"},
    "Bono US 2Y": {"fred_id": "DGS2", "type": "market", "is_percent": True, "units": "lin"},
    "Tasa FED": {"fred_id": "FEDFUNDS", "type": "market", "is_percent": True, "units": "lin"},
    "Volatilidad VIX": {"fred_id": "VIXCLS", "type": "market", "is_percent": False, "units": "lin"},
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
                    return f"data:image/{'png' if 'png' in filename else 'jpeg'};base64,{base64.b64encode(f.read()).decode()}"
            except: continue
    return ""

logo_b64 = get_local_logo_base64()

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
    start_date = "1920-01-01" 
    df_master = pd.DataFrame()
    try:
        fred = Fred(api_key=FRED_API_KEY)
    except: return pd.DataFrame()

    with st.empty(): 
        series_to_fetch = {k: v for k, v in INDICATOR_CONFIG.items() if "," not in v["fred_id"]}
        for name, config in series_to_fetch.items():
            try:
                units = config.get("units", "lin")
                series = fred.get_series(config["fred_id"], observation_start=start_date, units=units)
                temp = series.to_frame(name=name)
                if df_master.empty: df_master = temp
                else: df_master = df_master.join(temp, how='outer')
            except Exception: continue
    
    if not df_master.empty:
        df_master.index = pd.to_datetime(df_master.index)
        df_calc = df_master.ffill() 
    return df_master

# --- 6. FÁBRICA DE GRÁFICOS ---
def create_pro_chart(df, col1, col2=None, invert_y2=False, logo_data="", config_format=None, custom_source_label="Proprietary Data"):
    if config_format is None:
        config_format = {"color": "#002b49", "width": 2.5, "type": "Línea", "rec": True, "color_l2": "#5ca6e5", "width_l2": 2.0, "dash_l2": "dash"}

    COLOR_Y1 = config_format.get("color", "#002b49")
    WIDTH_Y1 = config_format.get("width", 2.5)
    
    COLOR_Y2 = config_format.get("color_l2", "#5ca6e5")
    WIDTH_Y2 = config_format.get("width_l2", 2.0)
    DASH_Y2 = config_format.get("dash_l2", "dash")

    has_secondary = col2 is not None and col2 != "Ninguno"
    suffix1, fmt1 = get_format_settings(col1)
    
    hoy_real = datetime.datetime.now()
    if not df.empty:
        df = df[df.index <= hoy_real] 
    
    fig = make_subplots(specs=[[{"secondary_y": has_secondary}]])
    hover_fmt = "%{x|%A, %b %d, %Y}"

    first_valid_date = None

    # EJE 1
    try:
        s1 = df[col1].dropna()
        if not s1.empty:
            first_valid_date = s1.index[0]
            last_v1 = s1.iloc[-1]
            
            if config_format["type"] == "Línea":
                fig.add_trace(go.Scatter(x=s1.index, y=s1, name=col1, line=dict(color=COLOR_Y1, width=WIDTH_Y1), mode='lines', hovertemplate=f"<b>{col1}</b><br>{hover_fmt}: %{{y:,.2f}}{suffix1}<extra></extra>"), secondary_y=False)
            elif config_format["type"] == "Barra":
                 fig.add_trace(go.Bar(x=s1.index, y=s1, name=col1, marker=dict(color=COLOR_Y1), hovertemplate=f"<b>{col1}</b><br>{hover_fmt}: %{{y:,.2f}}{suffix1}<extra></extra>"), secondary_y=False)
            elif config_format["type"] == "Área":
                 fig.add_trace(go.Scatter(x=s1.index, y=s1, name=col1, line=dict(color=COLOR_Y1, width=WIDTH_Y1), fill='tozeroy', mode='lines', hovertemplate=f"<b>{col1}</b><br>{hover_fmt}: %{{y:,.2f}}{suffix1}<extra></extra>"), secondary_y=False)
            
            txt_val = f"{last_v1:,.2f}{suffix1}" if suffix1 == "%" else f"{last_v1:,.2f}"
            fig.add_annotation(x=s1.index[-1], y=last_v1, text=f" {txt_val}", xref="x", yref="y1", xanchor="left", showarrow=False, font=dict(color="white", size=11, weight="bold"), bgcolor=COLOR_Y1, borderpad=4, opacity=0.9)
    except: pass

    # EJE 2
    if has_secondary:
        suffix2, fmt2 = get_format_settings(col2)
        try:
            s2 = df[col2].dropna()
            if not s2.empty:
                start_2 = s2.index[0]
                if first_valid_date is None or start_2 < first_valid_date: first_valid_date = start_2
                last_v2 = s2.iloc[-1]
                
                fig.add_trace(go.Scatter(
                    x=s2.index, y=s2, name=col2, 
                    line=dict(color=COLOR_Y2, width=WIDTH_Y2, dash=DASH_Y2), 
                    mode='lines', 
                    hovertemplate=f"<b>{col2}</b><br>{hover_fmt}: %{{y:,.2f}}{suffix2}<extra></extra>"
                ), secondary_y=True)
                
                txt_val2 = f"{last_v2:,.2f}{suffix2}" if suffix2 == "%" else f"{last_v2:,.2f}"
                fig.add_annotation(x=s2.index[-1], y=last_v2, text=f" {txt_val2}", xref="x", yref="y2", xanchor="left", showarrow=False, font=dict(color="white", size=11, weight="bold"), bgcolor=COLOR_Y2, borderpad=4, opacity=0.9)
        except: pass

    title_text = f"<b>{col1}</b>"
    if has_secondary: title_text += f" vs <b>{col2}</b>"

    fig.update_layout(
        title=dict(text=title_text, x=0.5, y=0.98, xanchor='center', font=dict(family="Arial", size=20, color="black")),
        plot_bgcolor="white", paper_bgcolor="white", height=650,
        margin=dict(t=120, r=80, l=80, b=100), showlegend=True,
        legend=dict(orientation="h", y=1.15, x=0, xanchor='left', bgcolor="rgba(0,0,0,0)", font=dict(color="#333")),
        images=[dict(source=logo_data, xref="paper", yref="paper", x=1, y=1.22, sizex=0.12, sizey=0.12, xanchor="right", yanchor="top")]
    )

    if first_valid_date is None: first_valid_date = pd.Timestamp("2000-01-01")
    
    fig.update_xaxes(
        range=[first_valid_date, hoy_real], 
        showgrid=False, linecolor="#333", linewidth=2, tickfont=dict(color="#333", size=12), ticks="outside",
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=365, label="1Y", step="day", stepmode="backward"), 
                dict(count=5, label="5Y", step="year", stepmode="backward"),
                dict(count=10, label="10Y", step="year", stepmode="backward"),
                dict(step="all", label="Max")
            ]),
            bgcolor="white", activecolor="#e6e6e6", x=0, y=1, xanchor='left', yanchor='bottom',
            font=dict(size=11, color="#333333") 
        )
    )
    
    fig.update_yaxes(title=f"<b>{col1}</b>", title_font=dict(color=COLOR_Y1), showgrid=True, gridcolor="#f0f0f0", gridwidth=1, linecolor="white", tickfont=dict(color=COLOR_Y1, weight="bold"), ticksuffix=suffix1, tickformat=fmt1, zeroline=False, secondary_y=False)
    
    if has_secondary:
        y2_title = f"<b>{col2} - Invertido</b>" if invert_y2 else f"<b>{col2}</b>"
        fig.update_yaxes(title=y2_title, title_font=dict(color=COLOR_Y2), showgrid=False, tickfont=dict(color=COLOR_Y2), ticksuffix=suffix2, tickformat=fmt2, autorange="reversed" if invert_y2 else True, secondary_y=True)

    if config_format["rec"]:
        recessions = [("1948-11-01", "1949-10-01"), ("1953-07-01", "1954-05-01"), ("1957-08-01", "1958-04-01"), ("1960-04-01", "1961-02-01"), ("1969-12-01", "1970-11-01"), ("1973-11-01", "1975-03-01"), ("1980-01-01", "1980-07-01"), ("1981-07-01", "1982-11-01"), ("1990-07-01", "1991-03-01"), ("2001-03-01", "2001-11-01"), ("2007-12-01", "2009-06-01"), ("2020-02-01", "2020-04-01")]
        if not df.empty:
            for start, end in recessions:
                try:
                    s_dt = pd.Timestamp(start)
                    e_dt = pd.Timestamp(end)
                    if e_dt > first_valid_date:
                        v_s = max(s_dt, first_valid_date)
                        v_e = min(e_dt, hoy_real)
                        fig.add_vrect(x0=v_s, x1=v_e, fillcolor="#e6e6e6", opacity=0.5, layer="below", line_width=0, yref="paper", y0=0, y1=1)
                except: pass
    
    def get_source_label(c):
        if c in INDICATOR_CONFIG: return f"FRED {INDICATOR_CONFIG[c]['fred_id']}"
        else: return custom_source_label

    lbl1 = get_source_label(col1)
    db_text = lbl1
    if has_secondary:
        lbl2 = get_source_label(col2)
        if lbl1 != lbl2: db_text += f", {lbl2}"

    fig.add_annotation(x=0, y=-0.14, text=f"Database: {db_text}", xref="paper", yref="paper", showarrow=False, font=dict(size=11, color="gray"), xanchor="left")
    fig.add_annotation(x=1, y=-0.14, text="Source: <b>XTB Research</b>", xref="paper", yref="paper", showarrow=False, font=dict(size=11, color="black"), xanchor="right")

    return fig

# --- 7. INTERFAZ PRINCIPAL ---
st.title("XTB Research Macro Dashboard")

# 1. CARGA DATOS
df_fred = get_all_macro_data_long_history()

# 2. GESTIÓN DE SESIÓN
if 'user_databases' not in st.session_state:
    st.session_state['user_databases'] = {}

# 3. SIDEBAR
with st.sidebar:
    st.header("📂 Datos Propios")
    uploaded_file = st.file_uploader("Subir Excel (.xlsx)", type=["xlsx"])
    
    if uploaded_file is not None:
        file_key = uploaded_file.name
        if file_key not in st.session_state['user_databases']:
            try:
                uploaded_file.seek(0)
                df_temp = pd.read_excel(uploaded_file)
                date_col = df_temp.columns[0]
                df_temp[date_col] = pd.to_datetime(df_temp[date_col], errors='coerce')
                df_temp = df_temp.dropna(subset=[date_col]).set_index(date_col).sort_index()
                for c in df_temp.columns:
                    df_temp[c] = pd.to_numeric(df_temp[c], errors='coerce')
                df_temp = df_temp.select_dtypes(include=['number'])
                
                st.session_state['user_databases'][file_key] = df_temp
                st.success(f"Agregado: {file_key}")
            except Exception as e:
                st.error(f"Error: {e}")

    if st.session_state['user_databases']:
        st.caption("📚 Archivos activos:")
        for name in st.session_state['user_databases']:
            st.text(f"- {name}")
        if st.button("🗑️ Limpiar Todo"):
            st.session_state['user_databases'] = {}
            st.rerun()

    # --- FUSIÓN Y RENOMBRADO ---
    df_full = df_fred.copy()
    user_cols_list = []
    
    for filename, df_u in st.session_state['user_databases'].items():
        df_to_merge = df_u.copy()
        cols_map = {}
        for c in df_to_merge.columns:
            if c in df_full.columns or "Unnamed" in str(c):
                cols_map[c] = f"{c} ({filename})"
        if cols_map: df_to_merge.rename(columns=cols_map, inplace=True)
        
        if not df_full.empty:
            df_full = df_full.join(df_to_merge, how='outer').sort_index()
        else:
            df_full = df_to_merge
        user_cols_list.extend(df_to_merge.columns.tolist())

    # --- VISIBLE: OPCIONES EXCEL ---
    custom_db_label = "Proprietary Data"
    
    if user_cols_list:
        st.markdown("---")
        st.markdown("### 📝 Opciones de Excel")
        custom_db_label = st.text_input("🏷️ Nombre de la Fuente (Pie de página):", value="Datos Propios", help="Cambia el texto 'Database: ...'")
        
        with st.expander("Renombrar Columnas"):
            rename_map = {}
            for col in user_cols_list:
                new_n = st.text_input(f"Renombrar '{col}':", value=col, key=f"ren_{col}")
                if new_n != col: rename_map[col] = new_n
            if rename_map: df_full = df_full.rename(columns=rename_map)

    st.divider()
    st.header("🛠️ Configuración")
    
    all_options = sorted(df_full.columns.tolist()) if not df_full.empty else sorted(INDICATOR_CONFIG.keys())
    
    tab_edit, tab_add, tab_fmt = st.tabs(["EDIT LINE", "ADD LINE", "FORMAT"])
    
    with tab_edit:
        st.caption("Eje Principal (Izq)")
        if all_options:
            y1_sel = st.selectbox("Indicador", options=all_options, index=0, key="sel_y1")
        else: y1_sel = "Sin Datos"
            
    with tab_add:
        st.caption("Eje Secundario (Der)")
        if all_options:
            y2_sel = st.selectbox("Indicador", options=["Ninguno"] + all_options, index=0, key="sel_y2")
        else: y2_sel = "Ninguno"
        invert_y2 = st.checkbox("Invertir Eje Der.", value=True)
        
    with tab_fmt:
        st.markdown("**Línea 1 (Principal)**")
        c1_1, c1_2 = st.columns(2)
        with c1_1:
            chart_type = st.selectbox("Tipo", ["Línea", "Barra", "Área"])
            chart_color = st.color_picker("Color L1", "#002b49")
        with c1_2:
            chart_width = st.slider("Grosor L1", 0.5, 5.0, 2.5)
        
        st.markdown("---")
        st.markdown("**Línea 2 (Secundaria)**")
        c2_1, c2_2 = st.columns(2)
        with c2_1:
            color_l2 = st.color_picker("Color L2", "#5ca6e5")
            style_l2_opt = st.selectbox("Estilo L2", ["Guiones", "Sólida", "Puntos"], index=0)
        with c2_2:
            width_l2 = st.slider("Grosor L2", 0.5, 5.0, 2.0)
            
        dash_map = {"Sólida": "solid", "Guiones": "dash", "Puntos": "dot"}
        dash_l2 = dash_map[style_l2_opt]
        
        st.markdown("---")
        chart_rec = st.checkbox("Recesiones", value=True)
        
        config_visual = {
            "type": chart_type, "color": chart_color, "width": chart_width, "rec": chart_rec,
            "color_l2": color_l2, "width_l2": width_l2, "dash_l2": dash_l2
        }

    st.divider()
    st.header("🤖 Analista IA")
    gemini_key = st.text_input("Gemini API Key:", type="password")
    
    if gemini_key:
        genai.configure(api_key=gemini_key)
        st.success("Conectado")
        with st.expander("Instrucción"):
            system_prompt = st.text_area("Rol:", value="Eres un estratega macro senior de XTB. Sé breve, directo y asertivo. Usa datos + contexto externo.", height=100)

# --- 8. VISUALIZACIÓN ---
if not df_full.empty and y1_sel != "Sin Datos":
    
    if gemini_key:
        with st.sidebar:
            user_question = st.text_area("Preguntar a IA:", placeholder="¿Qué ves en el gráfico?")
            if st.button("Analizar"):
                if user_question:
                    with st.spinner("Analizando..."):
                        try:
                            avail = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                            t_model = next((m for m in avail if 'flash' in m), next((m for m in avail if 'pro' in m), None))
                            if t_model:
                                data_csv = df_full[[y1_sel]].dropna().tail(30).to_csv()
                                model = genai.GenerativeModel(t_model)
                                prompt = f"SISTEMA: {system_prompt}\nDATOS: {data_csv}\nPREGUNTA: {user_question}"
                                res = model.generate_content(prompt)
                                st.info(res.text)
                            else: st.error("No hay modelos.")
                        except Exception as e: st.error(f"Error: {e}")

    # --- CONFIGURACIÓN DE DESCARGA JPG (VISIBILIDAD BARRA RESTAURADA) ---
    fig = create_pro_chart(df_full, y1_sel, y2_sel, invert_y2, logo_b64, config_visual, custom_source_label=custom_db_label)
    
    st.plotly_chart(fig, use_container_width=True, config={
        'displayModeBar': True, # Asegura que se vea
        'displaylogo': False,
        'modeBarButtonsToRemove': ['zoom', 'pan', 'select', 'lasso2d'],
        'toImageButtonOptions': {
            'format': 'jpeg',
            'filename': f'grafico_xtb_{y1_sel}',
            'height': 720,
            'width': 1280,
            'scale': 2
        }
    })
    
    st.caption("📸 Tip: Usa el icono de cámara en la esquina del gráfico para descargar en JPG alta calidad.")
    
    st.divider()
    # TABLA
    meta_info = INDICATOR_CONFIG.get(y1_sel, {"type": "market"}) 
    is_macro = (meta_info.get("type") == "macro") or (y1_sel not in INDICATOR_CONFIG)
    
    if is_macro:
        st.subheader(f"📅 Histórico: {y1_sel}")
        start_dt_table = pd.to_datetime("2020-01-01")
        df_view = df_full[df_full.index >= start_dt_table].copy()
        
        df_cal = df_view[[y1_sel]].dropna().sort_index(ascending=False)
        df_cal['Anterior'] = df_cal[y1_sel].shift(-1)
        df_cal = df_cal.reset_index()
        df_cal['Referencia'] = df_cal.iloc[:,0].dt.month.apply(get_month_name) + " " + df_cal.iloc[:,0].dt.year.astype(str)
        df_cal['Publicación'] = (df_cal.iloc[:,0] + pd.DateOffset(months=1)).dt.month.apply(get_month_name) + " " + (df_cal.iloc[:,0] + pd.DateOffset(months=1)).dt.year.astype(str)
        
        df_cal = df_cal.rename(columns={y1_sel: 'Actual'})
        
        is_pct = meta_info.get("is_percent", False)
        def fmt(x):
            if pd.isna(x): return ""
            txt = f"{x:.2f}"
            if txt.endswith(".00"): txt = txt[:-3]
            return f"{txt}%" if is_pct else txt

        df_cal['Actual'] = df_cal['Actual'].apply(fmt)
        df_cal['Anterior'] = df_cal['Anterior'].apply(fmt)
        
        st.dataframe(
            df_cal[['Referencia', 'Publicación', 'Actual', 'Anterior']].dropna(subset=['Anterior']),
            hide_index=True, use_container_width=True
        )
    else:
        st.caption(f"ℹ️ Tabla no disponible para datos de alta frecuencia ({y1_sel}).")

else:
    st.warning("Cargando datos...")