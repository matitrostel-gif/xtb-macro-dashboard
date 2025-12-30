import streamlit as st
import pandas as pd
from fredapi import Fred
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime
from datetime import timedelta
import base64
import os
import requests 
import google.generativeai as genai

# --- 1. CONFIGURACIÓN VISUAL ---
st.set_page_config(layout="wide", page_title="XTB Research Macro Dashboard")

st.markdown("""
<style>
    .block-container {padding-top: 1rem; padding-bottom: 3rem;}
    h1, h2, h3, h4, p, div {font-family: 'Arial', sans-serif;}
    .stSelectbox label, .stNumberInput label, .stCheckbox label, .stTextInput label, .stTextArea label, .stColorPicker label, .stSlider label {
        color: #EAEAEA !important; font-weight: bold; font-size: 13px;
    }
    div[data-testid="stCheckbox"] { margin-top: 5px; }
    [data-testid="stDataFrame"] { font-family: 'Arial', sans-serif; }
    [data-testid="stFileUploader"] { padding: 10px; border: 1px dashed #4a4a4a; border-radius: 5px; margin-bottom: 15px; }
    .stTabs [data-baseweb="tab-list"] { gap: 2px; }
    .stTabs [data-baseweb="tab"] { padding: 6px 10px; font-size: 12px; background-color: #262730; color: #ffffff; border-radius: 4px 4px 0px 0px; flex-grow: 1; }
    .stTabs [aria-selected="true"] { background-color: #ff4b4b; color: white; }
    hr { margin-top: 5px; margin-bottom: 10px; border-color: #444; }
</style>
""", unsafe_allow_html=True)

# --- 2. CONFIGURACIÓN MAESTRA ---
INDICATOR_CONFIG = {
    # --- EE.UU (FRED) ---
    "US Tasa Desempleo": {"id": "UNRATE", "src": "fred", "type": "macro", "is_percent": True, "units": "lin"},
    "US Nóminas NFP (YoY%)": {"id": "PAYEMS", "src": "fred", "type": "macro", "is_percent": True, "units": "pc1"},
    "US Initial Claims (YoY%)": {"id": "ICSA", "src": "fred", "type": "macro", "is_percent": True, "units": "pc1"},
    "US PCE Price Index (YoY%)": {"id": "PCEPI", "src": "fred", "type": "macro", "is_percent": True, "units": "pc1"},
    "US CPI Core (YoY%)": {"id": "CPIAUCSL", "src": "fred", "type": "macro", "is_percent": True, "units": "pc1"},
    "US Tasa FED": {"id": "FEDFUNDS", "src": "fred", "type": "market", "is_percent": True, "units": "lin"},
    "US Bono 10Y": {"id": "DGS10", "src": "fred", "type": "market", "is_percent": True, "units": "lin"},
    "US VIX": {"id": "VIXCLS", "src": "fred", "type": "market", "is_percent": False, "units": "lin"},
    
    # --- CHILE (BCCh) ---
    "CL Dólar Observado": {"ids": ["F073.TCO.PRE.Z.D", "F073.TCO.PRE.Z.M"], "src": "bcch", "type": "market", "is_percent": False},
    "CL UF": {"ids": ["F073.UFF.PRE.Z.D", "F073.UFF.PRE.Z.M"], "src": "bcch", "type": "market", "is_percent": False},
    "CL Tasa Política Monetaria (TPM)": {"ids": ["F021.TMP.TPM.D", "F021.TPM.TAS.Z.D", "F022.TPM.TIN.D001.NO.Z.D"], "src": "bcch", "type": "market", "is_percent": True},
    
    # Macro Chile
    "CL IMACEC (Var 12m)": {"ids": ["F019.IMC.IND.Z.Z", "F019.IEC.P.VAR.Z.Z"], "src": "bcch", "type": "macro", "is_percent": True, "calc_yoy_if_index": True},
    "CL PIB (Var 12m)": {"ids": ["F032.PIB.CLP.VR.Z.T", "F032.PIB.VAR.Z.Z"], "src": "bcch", "type": "macro", "is_percent": True}, 
    "CL IPC (Var 12m)": {"ids": ["F074.IPC.IND.Z.Z", "G073.IPC.IND.2018.M"], "src": "bcch", "type": "macro", "is_percent": True, "calc_yoy_if_index": True},
}

# --- 3. UTILIDADES ---
def get_local_logo_base64():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    possible_names = ["logo.png.png", "logo.png", "logo.jpg", "logo.jpeg"]
    for filename in possible_names:
        full_path = os.path.join(script_dir, filename)
        if os.path.exists(full_path):
            try:
                with open(full_path, "rb") as f:
                    return f"data:image/{'png' if 'png' in filename else 'jpeg'};base64,{base64.b64encode(f.read()).decode()}"
            except: continue
    return "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/XTB_logo_2022.svg/512px-XTB_logo_2022.svg.png"

logo_b64 = get_local_logo_base64()

def get_month_name(month_num):
    meses = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}
    return meses.get(month_num, '')

def get_format_settings(indicator_name):
    config = INDICATOR_CONFIG.get(indicator_name, {})
    is_pct = config.get("is_percent", False)
    if indicator_name not in INDICATOR_CONFIG:
        if "%" in indicator_name: is_pct = True
        else: is_pct = False
    if is_pct: return "%", ".2f"
    else: return "", ",.2f"

# --- 4. MOTOR DE DATOS ---
@st.cache_data(ttl=3600)
def get_fred_data(api_key):
    start_date = "1990-01-01" 
    df = pd.DataFrame()
    if not api_key: return df
    try:
        fred = Fred(api_key=api_key)
        fred_indicators = {k: v for k, v in INDICATOR_CONFIG.items() if v.get("src") == "fred"}
        for name, config in fred_indicators.items():
            try:
                units = config.get("units", "lin")
                series = fred.get_series(config["id"], observation_start=start_date, units=units)
                temp = series.to_frame(name=name)
                if df.empty: df = temp
                else: df = df.join(temp, how='outer')
            except: continue
    except: pass
    return df

@st.cache_data(ttl=3600)
def get_bcch_data(user, password):
    if not user or not password: return pd.DataFrame()
    df_bcch = pd.DataFrame()
    yr_start = "2000" 
    yr_end = str(datetime.datetime.now().year)
    
    bcch_indicators = {k: v for k, v in INDICATOR_CONFIG.items() if v.get("src") == "bcch"}
    
    for name, config in bcch_indicators.items():
        codes = config.get("ids", [])
        for code in codes:
            try:
                url = f"https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx?user={user}&pass={password}&firstdate={yr_start}-01-01&lastdate={yr_end}-12-31&timeseries={code}&function=GetSeries"
                res = requests.get(url, timeout=10)
                
                if res.status_code == 200:
                    data = res.json()
                    if 'Series' in data and 'Obs' in data['Series']:
                        obs = data['Series']['Obs']
                        if obs:
                            temp = pd.DataFrame(obs)
                            temp['indexDateString'] = pd.to_datetime(temp['indexDateString'], dayfirst=True, errors='coerce')
                            temp['value'] = temp['value'].astype(str).str.replace(',', '.', regex=False)
                            temp['value'] = pd.to_numeric(temp['value'], errors='coerce')
                            temp = temp.dropna().set_index('indexDateString')[['value']].rename(columns={'value': name})
                            
                            if config.get("calc_yoy_if_index", False) and "IND" in code:
                                temp = temp.pct_change(12) * 100
                                temp = temp.dropna()

                            temp = temp[~temp.index.duplicated(keep='last')]
                            
                            if df_bcch.empty: df_bcch = temp
                            else: df_bcch = df_bcch.join(temp, how='outer')
                            break 
            except: continue
    return df_bcch

# --- 5. FÁBRICA DE GRÁFICOS ---
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

    first_valid_date = pd.Timestamp("2000-01-01") 

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
                if start_2 < first_valid_date:
                    first_valid_date = start_2
                
                last_v2 = s2.iloc[-1]
                fig.add_trace(go.Scatter(x=s2.index, y=s2, name=col2, line=dict(color=COLOR_Y2, width=WIDTH_Y2, dash=DASH_Y2), mode='lines', hovertemplate=f"<b>{col2}</b><br>{hover_fmt}: %{{y:,.2f}}{suffix2}<extra></extra>"), secondary_y=True)
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
        images=[dict(source=logo_data, xref="paper", yref="paper", x=1, y=1.18, sizex=0.15, sizey=0.15, xanchor="right", yanchor="top")]
    )
    
    # --- RANGOS 1M Y 10Y ---
    fig.update_xaxes(
        range=[first_valid_date, hoy_real], 
        showgrid=False, linecolor="#333", linewidth=2, tickfont=dict(color="#333", size=12), ticks="outside",
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="1Y", step="year", stepmode="backward"), 
                dict(count=5, label="5Y", step="year", stepmode="backward"),
                dict(count=10, label="10Y", step="year", stepmode="backward"),
                dict(step="all", label="Max")
            ]),
            bgcolor="white", activecolor="#e6e6e6", x=0, y=1, xanchor='left', yanchor='bottom', font=dict(size=11, color="#333333") 
        )
    )
    
    fig.update_yaxes(title=f"<b>{col1}</b>", title_font=dict(color=COLOR_Y1), showgrid=True, gridcolor="#f0f0f0", gridwidth=1, linecolor="white", tickfont=dict(color=COLOR_Y1, weight="bold"), ticksuffix=suffix1, tickformat=fmt1, zeroline=False, secondary_y=False)
    if has_secondary:
        y2_title = f"<b>{col2} - Invertido</b>" if invert_y2 else f"<b>{col2}</b>"
        fig.update_yaxes(title=y2_title, title_font=dict(color=COLOR_Y2), showgrid=False, tickfont=dict(color=COLOR_Y2), ticksuffix=suffix2, tickformat=fmt2, autorange="reversed" if invert_y2 else True, secondary_y=True)

    if config_format["rec"]:
        recessions = [("2008-01-01", "2009-06-01"), ("2020-02-01", "2020-04-01")]
        for start, end in recessions:
            try:
                if pd.Timestamp(end) > first_valid_date:
                    v_s = max(pd.Timestamp(start), first_valid_date)
                    v_e = min(pd.Timestamp(end), hoy_real)
                    fig.add_vrect(x0=v_s, x1=v_e, fillcolor="#e6e6e6", opacity=0.5, layer="below", line_width=0, yref="paper", y0=0, y1=1)
            except: pass
    
    def get_source_label(c):
        if c in INDICATOR_CONFIG:
            src = INDICATOR_CONFIG[c]["src"]
            if src == "fred": return f"FRED {INDICATOR_CONFIG[c]['id']}"
            if src == "bcch": return f"BCCh {INDICATOR_CONFIG[c]['ids'][0]}"
        return custom_source_label

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

# === SIDEBAR ===
with st.sidebar:
    
    # 1. DATOS PROPIOS
    with st.expander("📂 Datos Propios (Excel)", expanded=True):
        uploaded_file = st.file_uploader("Subir archivo .xlsx", type=["xlsx"])
        if 'user_databases' not in st.session_state: st.session_state['user_databases'] = {}
        
        if uploaded_file:
            file_key = uploaded_file.name
            if file_key not in st.session_state['user_databases']:
                try:
                    uploaded_file.seek(0)
                    df_temp = pd.read_excel(uploaded_file)
                    date_col = df_temp.columns[0]
                    df_temp[date_col] = pd.to_datetime(df_temp[date_col], errors='coerce')
                    df_temp = df_temp.dropna(subset=[date_col]).set_index(date_col).sort_index()
                    for c in df_temp.columns: df_temp[c] = pd.to_numeric(df_temp[c], errors='coerce')
                    df_temp = df_temp.select_dtypes(include=['number'])
                    st.session_state['user_databases'][file_key] = df_temp
                    st.success(f"Cargado: {file_key}")
                except Exception as e: st.error(f"Error: {e}")
        
        if st.session_state['user_databases']:
            if st.button("Limpiar Todo"):
                st.session_state['user_databases'] = {}
                st.rerun()

    # 2. CONEXIONES API
    with st.expander("🔑 Conexiones API", expanded=False):
        fred_key = st.text_input("FRED Key:", value="a913b86d145620f86b690a7e4fe4538e", type="password")
        st.markdown("---")
        st.caption("Banco Central de Chile")
        bcch_user = st.text_input("Usuario:", help="Rut/Correo")
        bcch_pass = st.text_input("Password:", type="password")

    # 3. DATO MANUAL
    st.divider()
    with st.expander("✍️ Dato Manual (Dólar Hoy)", expanded=True):
        st.caption("Si el BCCh no actualiza, ingresa el precio aquí:")
        manual_usd = st.number_input("Precio Cierre Hoy:", min_value=0.0, value=0.0, step=0.1, format="%.2f", help="Deja en 0 para usar dato automático.")

    # 4. ANALISTA IA
    with st.expander("🤖 Analista IA", expanded=False):
        gemini_key = st.text_input("Gemini Key:", type="password")
        system_prompt = st.text_area("Rol:", value="Eres un estratega macro senior de XTB. Sé breve y directo.", height=100)
        user_question = st.text_area("Pregunta:", placeholder="¿Qué ves?")
        run_ai = st.button("Analizar")

# --- CARGA DATOS ---
df_fred = get_fred_data(fred_key)
df_bcch = get_bcch_data(bcch_user, bcch_pass) 

df_repo = pd.DataFrame()
if not df_fred.empty: df_repo = df_fred
if not df_bcch.empty:
    if df_repo.empty: df_repo = df_bcch
    else: df_repo = df_repo.join(df_bcch, how='outer')

df_full = df_repo.copy()
user_cols_list = []
for filename, df_u in st.session_state['user_databases'].items():
    df_to_merge = df_u.copy()
    new_cols = {}
    for c in df_to_merge.columns:
        if c in df_full.columns: new_cols[c] = f"{c} ({filename})"
    if new_cols: df_to_merge.rename(columns=new_cols, inplace=True)
    if not df_full.empty: df_full = df_full.join(df_to_merge, how='outer').sort_index()
    else: df_full = df_to_merge
    user_cols_list.extend(df_to_merge.columns.tolist())

# --- OPCIONES EXCEL ---
custom_db_label = "Proprietary Data"
if user_cols_list:
    st.sidebar.markdown("---")
    with st.sidebar.expander("📝 Editar Excel", expanded=True):
        custom_db_label = st.text_input("Fuente Pie Pagina:", value="Datos Propios")
        for col in user_cols_list:
            new_n = st.text_input(f"Renombrar {col}:", value=col, key=f"ren_{col}")
            if new_n != col: df_full = df_full.rename(columns={col: new_n})

# --- CONFIGURACION GRAFICO ---
all_opts = sorted(list(set(list(INDICATOR_CONFIG.keys()) + list(df_full.columns))))

with st.sidebar:
    st.divider()
    with st.expander("🛠️ Config. Gráfico", expanded=True):
        tab1, tab2, tab3 = st.tabs(["EJE 1", "EJE 2", "ESTILO"])
        with tab1: y1_sel = st.selectbox("Principal", options=all_opts, index=0)
        with tab2: 
            y2_sel = st.selectbox("Secundario", options=["Ninguno"] + all_opts, index=0)
            invert_y2 = st.checkbox("Invertir", value=True)
        with tab3:
            col1 = st.color_picker("Color 1", "#002b49")
            typ1 = st.selectbox("Tipo 1", ["Línea", "Barra", "Área"])
            col2 = st.color_picker("Color 2", "#5ca6e5")
            stl2 = st.selectbox("Estilo 2", ["Guiones", "Sólida", "Puntos"])
            rec = st.checkbox("Recesiones", True)
            
            dash_map = {"Sólida": "solid", "Guiones": "dash", "Puntos": "dot"}
            config_visual = {"type": typ1, "color": col1, "width": 2.5, "rec": rec, "color_l2": col2, "width_l2": 2.0, "dash_l2": dash_map[stl2]}

# --- RENDER ---
if not df_full.empty and y1_sel != "Sin Datos":
    
    # IA RESPONSE
    if gemini_key and run_ai:
        with st.spinner("Pensando..."):
            try:
                avail = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                t_model = next((m for m in avail if 'flash' in m), next((m for m in avail if 'pro' in m), None))
                if t_model:
                    if y1_sel in df_full.columns:
                        d_csv = df_full[[y1_sel]].dropna().tail(30).to_csv()
                        mod = genai.GenerativeModel(t_model)
                        res = mod.generate_content(f"SISTEMA: {system_prompt}\nDATOS: {d_csv}\nPREGUNTA: {user_question}")
                        st.sidebar.info(res.text)
                    else: st.sidebar.warning("No hay datos para analizar.")
            except Exception as e: st.sidebar.error(f"Error IA: {e}")

    # CHART
    if y1_sel in df_full.columns or (y2_sel != "Ninguno" and y2_sel in df_full.columns):
        fig = create_pro_chart(df_full, y1_sel, y2_sel, invert_y2, logo_b64, config_visual, custom_source_label=custom_db_label)
        st.plotly_chart(fig, use_container_width=True, config={'toImageButtonOptions': {'format': 'jpeg', 'filename': 'grafico_xtb', 'scale': 2}})
    else:
        st.info("💡 Los datos están cargando o no están disponibles. Verifique sus claves.")

    st.divider()
    
    # --- LOGICA TABLA: MACRO vs MERCADO ---
    meta = INDICATOR_CONFIG.get(y1_sel, {"type": "market"}) 
    is_excel = y1_sel not in INDICATOR_CONFIG
    is_macro = (meta.get("type") == "macro") or is_excel
    
    # --- CALCULADORA DE VARIACIONES (CON OVERRIDE MANUAL) ---
    if "Dólar" in y1_sel and "CL Dólar Observado" in df_full.columns:
        st.subheader("🧮 Calculadora de Variaciones: Dólar")
        
        # 1. Crear copia para trabajar
        df_dollar_calc = df_full[["CL Dólar Observado"]].dropna().copy()
        
        # 2. APLICAR DATO MANUAL SI EXISTE
        if manual_usd > 0:
            today_date = pd.Timestamp.now().normalize()
            df_dollar_calc.loc[today_date] = manual_usd
            df_dollar_calc = df_dollar_calc.sort_index()
        
        # 3. Unir UF
        if "CL UF" in df_full.columns:
            df_uf = df_full[["CL UF"]].copy()
            if manual_usd > 0:
                last_uf = df_uf["CL UF"].dropna().iloc[-1]
                today_date = pd.Timestamp.now().normalize()
                if today_date not in df_uf.index:
                    df_uf.loc[today_date] = last_uf
            
            df_dollar_calc = df_dollar_calc.join(df_uf, how='left').ffill()
        
        available_years = sorted(df_dollar_calc.index.year.unique().tolist(), reverse=True)
        default_years = [y for y in [2025, 2017, 2009] if y in available_years]
        if not default_years and available_years: default_years = [available_years[0]]
        
        target_years = st.multiselect("Selecciona los años a analizar:", options=available_years, default=default_years)
        
        if target_years:
            stats = []
            for yr in sorted(target_years, reverse=True):
                yr_data = df_dollar_calc[df_dollar_calc.index.year == yr]
                prev_yr_data = df_dollar_calc[df_dollar_calc.index.year == (yr - 1)]
                
                if not yr_data.empty:
                    current_price = yr_data["CL Dólar Observado"].iloc[-1]
                    ref_date = yr_data.index[-1].strftime('%d-%m-%Y')
                    
                    current_uf = yr_data["CL UF"].iloc[-1] if "CL UF" in yr_data.columns else None
                    
                    nom_var = "N/A"
                    real_var = "N/A"
                    var_clp = "N/A"
                    
                    if not prev_yr_data.empty:
                        prev_price = prev_yr_data["CL Dólar Observado"].iloc[-1]
                        prev_uf = prev_yr_data["CL UF"].iloc[-1] if "CL UF" in prev_yr_data.columns else None
                        
                        nom_pct = ((current_price - prev_price) / prev_price) * 100
                        nom_var = f"{nom_pct:.2f}%"
                        
                        diff_price = current_price - prev_price
                        sign = "+" if diff_price > 0 else ""
                        var_clp = f"{sign}${diff_price:,.2f}"
                        
                        if current_uf and prev_uf:
                            real_pct = (((current_price / current_uf) - (prev_price / prev_uf)) / (prev_price / prev_uf)) * 100
                            real_var = f"{real_pct:.2f}%"
                    
                    stats.append({
                        "Año": yr,
                        "Fecha Ref.": ref_date,
                        "Cierre Nominal": f"${current_price:,.2f}", # AQUI QUITAMOS EL TEXTO (Manual)
                        "Var. $ (CLP)": var_clp,
                        "Var. Nominal %": nom_var,
                        "Var. Real (UF) %": real_var if "CL UF" in df_full.columns else "Requiere UF"
                    })
            
            st.table(pd.DataFrame(stats).set_index("Año"))
        else:
            st.info("Selecciona al menos un año para ver el cálculo.")

    # --- TABLA HISTÓRICA GENERAL ---
    if is_macro and y1_sel in df_full.columns:
        st.subheader(f"📅 Histórico: {y1_sel}")
        start_dt_table = pd.to_datetime("2020-01-01")
        df_view = df_full[df_full.index >= start_dt_table].copy()
        
        df_cal = df_view[[y1_sel]].dropna().sort_index(ascending=False)
        df_cal['Anterior'] = df_cal[y1_sel].shift(-1)
        
        df_cal.index.name = 'Fecha_Base'
        df_cal = df_cal.reset_index()
        
        df_cal['Mes_Ref'] = df_cal['Fecha_Base'].dt.month
        df_cal['Referencia'] = df_cal['Mes_Ref'].apply(get_month_name) + " " + df_cal['Fecha_Base'].dt.year.astype(str)
        df_cal['Fecha_Pub'] = df_cal['Fecha_Base'] + pd.DateOffset(months=1)
        df_cal['Mes_Pub'] = df_cal['Fecha_Pub'].dt.month
        df_cal['Publicación (Est.)'] = df_cal['Mes_Pub'].apply(get_month_name) + " " + df_cal['Fecha_Pub'].dt.year.astype(str)
        
        df_cal = df_cal.rename(columns={y1_sel: 'Actual'})
        
        is_pct = meta.get("is_percent", False)
        def fmt(x): 
            if pd.isna(x): return ""
            txt = f"{x:.2f}"
            if txt.endswith(".00"): txt = txt[:-3]
            return f"{txt}%" if is_pct else txt

        df_cal['Actual'] = df_cal['Actual'].apply(fmt)
        df_cal['Anterior'] = df_cal['Anterior'].apply(fmt)
        
        st.dataframe(
            df_cal[['Referencia', 'Publicación (Est.)', 'Actual', 'Anterior']].dropna(subset=['Anterior']),
            hide_index=True, 
            use_container_width=True,
            column_config={
                "Referencia": st.column_config.TextColumn("Referencia", width="medium"),
                "Publicación (Est.)": st.column_config.TextColumn("Publicación (Est.)", width="medium"),
                "Actual": st.column_config.TextColumn("Dato Actual", width="small"),
                "Anterior": st.column_config.TextColumn("Dato Anterior", width="small")
            }
        )
    else:
        st.caption(f"ℹ️ Tabla no disponible para datos de alta frecuencia ({y1_sel}).")

else:
    st.warning("Esperando datos... Ingrese sus claves API en el menú lateral.")