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
    /* Aumentar ancho del sidebar */
    [data-testid="stSidebar"] {
        min-width: 350px;
        max-width: 400px;
    }
    [data-testid="stSidebar"] > div:first-child {
        width: 350px;
    }
    
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
    
    /* Estilos para el panel de metadatos estilo FRED */
    .fred-panel {
        background: #f8fbfd;
        border: 1px solid #e0e0e0;
        border-bottom: none;
        border-radius: 4px 4px 0 0;
        padding: 15px 20px 10px 20px;
        margin-bottom: 0;
    }
    .fred-header {
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .fred-title-text {
        font-size: 22px;
        font-weight: bold;
        color: #1a1a1a;
    }
    .fred-code {
        font-size: 14px;
        color: #666;
        font-weight: normal;
    }
    .fred-col-content {
        padding: 10px 0;
    }
    .fred-col-border {
        border-left: 1px solid #e0e0e0;
        padding-left: 15px;
    }
    .fred-label {
        color: #0066cc;
        font-size: 13px;
        margin-bottom: 4px;
    }
    .fred-value {
        font-size: 14px;
        color: #333;
    }
    .fred-sub {
        font-size: 12px;
        color: #666;
        margin-top: 2px;
    }
    .fred-link {
        color: #0066cc;
        font-size: 12px;
        margin-top: 4px;
    }
    .fred-source-badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 4px;
        font-size: 12px;
        font-weight: bold;
    }
    .fred-badge {
        background-color: #1e4a7a;
        color: white;
    }
    .bcch-badge {
        background-color: #006341;
        color: white;
    }
    .custom-badge {
        background-color: #6b4c9a;
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. CONFIGURACIÓN MAESTRA ---
INDICATOR_CONFIG = {
    # --- EE.UU (FRED) ---
    "US Tasa Desempleo": {
        "id": "UNRATE", "src": "fred", "type": "macro", "is_percent": True, "units": "lin",
        "meta": {"units": "Percent", "units_detail": "Seasonally Adjusted", "frequency": "Monthly", "title": "Unemployment Rate"}
    },
    "US Nóminas NFP (YoY%)": {
        "id": "PAYEMS", "src": "fred", "type": "macro", "is_percent": True, "units": "pc1",
        "meta": {"units": "Percent Change", "units_detail": "Year-over-Year", "frequency": "Monthly", "title": "Nonfarm Payrolls"}
    },
    "US Initial Claims (YoY%)": {
        "id": "ICSA", "src": "fred", "type": "macro", "is_percent": True, "units": "pc1",
        "meta": {"units": "Percent Change", "units_detail": "Year-over-Year", "frequency": "Weekly", "title": "Initial Jobless Claims"}
    },
    "US PCE Price Index (YoY%)": {
        "id": "PCEPI", "src": "fred", "type": "macro", "is_percent": True, "units": "pc1",
        "meta": {"units": "Percent Change", "units_detail": "Year-over-Year", "frequency": "Monthly", "title": "PCE Price Index"}
    },
    "US CPI Core (YoY%)": {
        "id": "CPIAUCSL", "src": "fred", "type": "macro", "is_percent": True, "units": "pc1",
        "meta": {"units": "Percent Change", "units_detail": "Year-over-Year", "frequency": "Monthly", "title": "Consumer Price Index"}
    },
    "US Tasa FED": {
        "id": "FEDFUNDS", "src": "fred", "type": "market", "is_percent": True, "units": "lin",
        "meta": {"units": "Percent", "units_detail": "Not Seasonally Adjusted", "frequency": "Monthly", "title": "Federal Funds Rate"}
    },
    "US Bono 10Y": {
        "id": "DGS10", "src": "fred", "type": "market", "is_percent": True, "units": "lin",
        "meta": {"units": "Percent", "units_detail": "Not Seasonally Adjusted", "frequency": "Daily", "title": "10-Year Treasury Rate"}
    },
    "US VIX": {
        "id": "VIXCLS", "src": "fred", "type": "market", "is_percent": False, "units": "lin",
        "meta": {"units": "Index", "units_detail": "Not Seasonally Adjusted", "frequency": "Daily", "title": "CBOE Volatility Index"}
    },
    
    # --- CHILE (BCCh) ---
    "CL Dólar Observado": {
        "ids": ["F073.TCO.PRE.Z.D", "F073.TCO.PRE.Z.M"], "src": "bcch", "type": "market", "is_percent": False,
        "meta": {"units": "Pesos Chilenos", "units_detail": "Tipo de Cambio Observado", "frequency": "Diaria", "title": "Dólar Observado"}
    },
    "CL UF": {
        "ids": ["F073.UFF.PRE.Z.D", "F073.UFF.PRE.Z.M"], "src": "bcch", "type": "market", "is_percent": False,
        "meta": {"units": "Pesos Chilenos", "units_detail": "Unidad de Fomento", "frequency": "Diaria", "title": "Unidad de Fomento (UF)"}
    },
    "CL Tasa Política Monetaria (TPM)": {
        "ids": ["F021.TMP.TPM.D", "F021.TPM.TAS.Z.D", "F022.TPM.TIN.D001.NO.Z.D"], "src": "bcch", "type": "market", "is_percent": True,
        "meta": {"units": "Porcentaje", "units_detail": "Tasa Anual", "frequency": "Diaria", "title": "Tasa de Política Monetaria"}
    },
    
    # Macro Chile
    "CL IMACEC (Var 12m)": {
        "ids": ["F019.IMC.IND.Z.Z", "F019.IEC.P.VAR.Z.Z"], "src": "bcch", "type": "macro", "is_percent": True, "calc_yoy_if_index": True,
        "meta": {"units": "Porcentaje", "units_detail": "Variación 12 meses", "frequency": "Mensual", "title": "IMACEC"}
    },
    "CL PIB (Var 12m)": {
        "ids": ["F032.PIB.CLP.VR.Z.T", "F032.PIB.VAR.Z.Z"], "src": "bcch", "type": "macro", "is_percent": True,
        "meta": {"units": "Porcentaje", "units_detail": "Variación 12 meses", "frequency": "Trimestral", "title": "Producto Interno Bruto"}
    }, 
    "CL IPC (Var 12m)": {
        "ids": ["F074.IPC.IND.Z.Z", "G073.IPC.IND.2018.M"], "src": "bcch", "type": "macro", "is_percent": True, "calc_yoy_if_index": True,
        "meta": {"units": "Porcentaje", "units_detail": "Variación 12 meses", "frequency": "Mensual", "title": "Índice de Precios al Consumidor"}
    },
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

def get_month_name_full(month_num):
    meses = {1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril', 5: 'Mayo', 6: 'Junio', 
             7: 'Julio', 8: 'Agosto', 9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'}
    return meses.get(month_num, '')

def get_format_settings(indicator_name):
    config = INDICATOR_CONFIG.get(indicator_name, {})
    is_pct = config.get("is_percent", False)
    if indicator_name not in INDICATOR_CONFIG:
        if "%" in indicator_name: is_pct = True
        else: is_pct = False
    if is_pct: return "%", ".2f"
    else: return "", ",.2f"

def estimate_next_release(last_date, frequency):
    """Estima la próxima fecha de publicación basada en la frecuencia (fallback)"""
    if frequency in ["Monthly", "Mensual"]:
        next_month = last_date + timedelta(days=35)
        return next_month.replace(day=15)
    elif frequency in ["Weekly", "Semanal"]:
        return last_date + timedelta(days=7)
    elif frequency in ["Daily", "Diaria"]:
        return last_date + timedelta(days=1)
    elif frequency in ["Quarterly", "Trimestral"]:
        return last_date + timedelta(days=95)
    return last_date + timedelta(days=30)

@st.cache_data(ttl=3600)
def get_fred_release_date(series_id, api_key):
    """Obtiene la próxima fecha de publicación real desde FRED API"""
    if not api_key or not series_id:
        return None
    try:
        url = f"https://api.stlouisfed.org/fred/series/release?series_id={series_id}&api_key={api_key}&file_type=json"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if 'releases' in data and len(data['releases']) > 0:
                release_id = data['releases'][0]['id']
                # Obtener próximas fechas de release
                url_dates = f"https://api.stlouisfed.org/fred/release/dates?release_id={release_id}&api_key={api_key}&file_type=json&include_release_dates_with_no_data=true"
                res_dates = requests.get(url_dates, timeout=10)
                if res_dates.status_code == 200:
                    dates_data = res_dates.json()
                    if 'release_dates' in dates_data:
                        today = datetime.datetime.now().date()
                        for rd in dates_data['release_dates']:
                            release_date = datetime.datetime.strptime(rd['date'], "%Y-%m-%d").date()
                            if release_date >= today:
                                return release_date
    except:
        pass
    return None

@st.cache_data(ttl=3600)
def get_fred_last_updated(series_id, api_key):
    """Obtiene la fecha de última actualización real desde FRED API"""
    if not api_key or not series_id:
        return None
    try:
        url = f"https://api.stlouisfed.org/fred/series?series_id={series_id}&api_key={api_key}&file_type=json"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if 'seriess' in data and len(data['seriess']) > 0:
                last_updated_str = data['seriess'][0].get('last_updated', '')
                if last_updated_str:
                    # Formato: "2025-12-16 08:19:00-06"
                    date_part = last_updated_str.split(' ')[0]
                    return datetime.datetime.strptime(date_part, "%Y-%m-%d").date()
    except:
        pass
    return None

def render_metadata_panel(indicator_name, df, config, fred_api_key=None):
    """Renderiza el panel de metadatos estilo FRED y retorna el rango de fechas seleccionado"""
    if indicator_name not in df.columns:
        return None, None
    
    series = df[indicator_name].dropna()
    if series.empty:
        return None, None
    
    # Obtener datos
    last_value = series.iloc[-1]
    last_date = series.index[-1]
    first_date = series.index[0]
    
    # Metadatos del indicador
    meta = config.get("meta", {})
    title = meta.get("title", indicator_name)
    units = meta.get("units", "Value")
    units_detail = meta.get("units_detail", "")
    frequency = meta.get("frequency", "N/A")
    source = config.get("src", "custom")
    
    # Código del indicador
    if source == "fred":
        indicator_code = config.get("id", "")
        badge_class = "fred-badge"
        source_name = "FRED"
    elif source == "bcch":
        indicator_code = config.get("ids", [""])[0]
        badge_class = "bcch-badge"
        source_name = "BCCh"
    else:
        indicator_code = ""
        badge_class = "custom-badge"
        source_name = "Custom"
    
    # Formatear valor
    is_pct = config.get("is_percent", False)
    if is_pct:
        formatted_value = f"{last_value:.1f}"
    else:
        formatted_value = f"{last_value:,.2f}"
    
    # Formatear fechas para observaciones
    if frequency in ["Monthly", "Mensual"]:
        obs_label = f"{get_month_name(last_date.month)} {last_date.year}: <b>{formatted_value}</b>"
    elif frequency in ["Daily", "Diaria"]:
        obs_label = f"{last_date.strftime('%d %b %Y')}: <b>{formatted_value}</b>"
    else:
        obs_label = f"{last_date.strftime('%Y-%m-%d')}: <b>{formatted_value}</b>"
    
    # Obtener Updated date
    if source == "fred" and fred_api_key:
        real_updated = get_fred_last_updated(indicator_code, fred_api_key)
        if real_updated:
            updated_date = real_updated.strftime("%b %d, %Y")
        else:
            updated_date = last_date.strftime("%b %d, %Y")
    else:
        updated_date = last_date.strftime("%b %d, %Y")
    
    # Obtener Next Release
    if source == "fred" and fred_api_key:
        real_next_release = get_fred_release_date(indicator_code, fred_api_key)
        if real_next_release:
            next_release_str = real_next_release.strftime("%b %d, %Y")
        else:
            next_release = estimate_next_release(last_date, frequency)
            next_release_str = next_release.strftime("%b %d, %Y")
    else:
        next_release = estimate_next_release(last_date, frequency)
        next_release_str = next_release.strftime("%b %d, %Y")
    
    # Contenedor principal
    st.markdown(f"""
    <div class="fred-panel">
        <div class="fred-header">
            <span class="fred-source-badge {badge_class}">{source_name}</span>
            <span class="fred-title-text">{title}</span>
            <span class="fred-code">({indicator_code})</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Crear las 4 columnas con Streamlit
    col1, col2, col3, col4 = st.columns([2.5, 1.5, 1, 2])
    
    with col1:
        st.markdown(f"""
        <div class="fred-col-content">
            <div class="fred-label">Observations ▼</div>
            <div class="fred-value">{obs_label}</div>
            <div class="fred-sub">Updated: {updated_date}</div>
            <div class="fred-link">Next Release: {next_release_str}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="fred-col-content fred-col-border">
            <div class="fred-label">Units:</div>
            <div class="fred-value">{units}</div>
            <div class="fred-sub">{units_detail}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="fred-col-content fred-col-border">
            <div class="fred-label">Frequency:</div>
            <div class="fred-value">{frequency}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        # Selectores de fecha interactivos
        st.markdown("<div class='fred-col-border' style='padding-left: 15px;'>", unsafe_allow_html=True)
        
        subcol1, subcol2, subcol3 = st.columns([1, 0.3, 1])
        with subcol1:
            date_from = st.date_input(
                "Desde",
                value=first_date.date() if hasattr(first_date, 'date') else first_date,
                min_value=first_date.date() if hasattr(first_date, 'date') else first_date,
                max_value=last_date.date() if hasattr(last_date, 'date') else last_date,
                key=f"date_from_{indicator_name}",
                label_visibility="collapsed"
            )
        with subcol2:
            st.markdown("<p style='text-align:center; padding-top:8px; margin:0;'>to</p>", unsafe_allow_html=True)
        with subcol3:
            date_to = st.date_input(
                "Hasta",
                value=last_date.date() if hasattr(last_date, 'date') else last_date,
                min_value=first_date.date() if hasattr(first_date, 'date') else first_date,
                max_value=last_date.date() if hasattr(last_date, 'date') else last_date,
                key=f"date_to_{indicator_name}",
                label_visibility="collapsed"
            )
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Línea divisoria después del panel
    st.markdown("<hr style='margin: 10px 0 20px 0; border-color: #e0e0e0;'>", unsafe_allow_html=True)
    
    return date_from, date_to


# --- 4. MOTOR DE DATOS ---
@st.cache_data(ttl=3600)
def get_fred_data(api_key):
    start_date = "1948-01-01" 
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
def create_pro_chart(df, col1, col2=None, invert_y2=False, logo_data="", config_format=None, custom_source_label="Proprietary Data", custom_line=None):
    if config_format is None:
        config_format = {"color": "#002b49", "width": 3, "type": "Línea", "rec": True, "color_l2": "#5ca6e5", "width_l2": 3, "dash_l2": "dash"}

    COLOR_Y1 = config_format.get("color", "#002b49")
    WIDTH_Y1 = config_format.get("width", 3)
    COLOR_Y2 = config_format.get("color_l2", "#5ca6e5")
    WIDTH_Y2 = config_format.get("width_l2", 3)
    DASH_Y1 = config_format.get("dash_l1", "solid")
    DASH_Y2 = config_format.get("dash_l2", "dash")
    
    # Nuevas opciones de formato
    show_title = config_format.get("show_title", True)
    show_axis_titles = config_format.get("show_axis_titles", True)
    show_tooltip = config_format.get("show_tooltip", True)
    log_scale_left = config_format.get("log_scale_left", False)
    frame_color = config_format.get("frame_color", "#FFFFFF")
    plot_area_color = config_format.get("plot_area_color", "#FFFFFF")
    text_color = config_format.get("text_color", "#000000")
    chart_height = config_format.get("chart_height", 450)
    chart_width = config_format.get("chart_width", 1040)
    line1_mark = config_format.get("line1_mark", "None")
    line2_mark = config_format.get("line2_mark", "None")
    line1_yaxis = config_format.get("line1_yaxis", "Left")
    line2_yaxis = config_format.get("line2_yaxis", "Left")

    has_secondary = col2 is not None and col2 != "Ninguno"
    suffix1, fmt1 = get_format_settings(col1)
    
    hoy_real = datetime.datetime.now()
    if not df.empty:
        df = df[df.index <= hoy_real] 
    
    fig = make_subplots(specs=[[{"secondary_y": has_secondary or line2_yaxis == "Right"}]])
    hover_fmt = "%{x|%A, %b %d, %Y}"
    
    # Mapeo de marcadores
    marker_map = {"None": None, "Circle": "circle", "Square": "square", "Diamond": "diamond"}

    first_valid_date = pd.Timestamp("2000-01-01") 

    # EJE 1
    try:
        s1 = df[col1].dropna()
        if not s1.empty:
            first_valid_date = s1.index[0]
            last_v1 = s1.iloc[-1]
            
            # Configurar modo y marcadores
            mode1 = 'lines'
            marker1 = None
            if line1_mark != "None":
                mode1 = 'lines+markers'
                marker1 = dict(symbol=marker_map.get(line1_mark), size=8, color=COLOR_Y1)
            
            hovertemplate1 = f"<b>{col1}</b><br>{hover_fmt}: %{{y:,.2f}}{suffix1}<extra></extra>" if show_tooltip else None
            
            if config_format["type"] == "Línea":
                trace_kwargs = dict(x=s1.index, y=s1, name=col1, line=dict(color=COLOR_Y1, width=WIDTH_Y1, dash=DASH_Y1), mode=mode1, hovertemplate=hovertemplate1)
                if marker1:
                    trace_kwargs['marker'] = marker1
                fig.add_trace(go.Scatter(**trace_kwargs), secondary_y=(line1_yaxis == "Right"))
            elif config_format["type"] == "Barra":
                fig.add_trace(go.Bar(x=s1.index, y=s1, name=col1, marker=dict(color=COLOR_Y1), hovertemplate=hovertemplate1), secondary_y=(line1_yaxis == "Right"))
            elif config_format["type"] == "Área":
                trace_kwargs = dict(x=s1.index, y=s1, name=col1, line=dict(color=COLOR_Y1, width=WIDTH_Y1, dash=DASH_Y1), fill='tozeroy', mode=mode1, hovertemplate=hovertemplate1)
                if marker1:
                    trace_kwargs['marker'] = marker1
                fig.add_trace(go.Scatter(**trace_kwargs), secondary_y=(line1_yaxis == "Right"))
            
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
                
                # Configurar modo y marcadores para línea 2
                mode2 = 'lines'
                marker2 = None
                if line2_mark != "None":
                    mode2 = 'lines+markers'
                    marker2 = dict(symbol=marker_map.get(line2_mark), size=8, color=COLOR_Y2)
                
                hovertemplate2 = f"<b>{col2}</b><br>{hover_fmt}: %{{y:,.2f}}{suffix2}<extra></extra>" if show_tooltip else None
                
                trace_kwargs2 = dict(x=s2.index, y=s2, name=col2, line=dict(color=COLOR_Y2, width=WIDTH_Y2, dash=DASH_Y2), mode=mode2, hovertemplate=hovertemplate2)
                if marker2:
                    trace_kwargs2['marker'] = marker2
                fig.add_trace(go.Scatter(**trace_kwargs2), secondary_y=(line2_yaxis == "Right"))
                
                txt_val2 = f"{last_v2:,.2f}{suffix2}" if suffix2 == "%" else f"{last_v2:,.2f}"
                yref2 = "y2" if line2_yaxis == "Right" else "y1"
                fig.add_annotation(x=s2.index[-1], y=last_v2, text=f" {txt_val2}", xref="x", yref=yref2, xanchor="left", showarrow=False, font=dict(color="white", size=11, weight="bold"), bgcolor=COLOR_Y2, borderpad=4, opacity=0.9)
        except: pass

    title_text = f"<b>{col1}</b>" if show_title else ""
    if has_secondary and show_title: title_text += f" vs <b>{col2}</b>"

    fig.update_layout(
        title=dict(text=title_text, x=0.5, y=0.98, xanchor='center', font=dict(family="Arial", size=20, color=text_color)) if show_title else None,
        plot_bgcolor=plot_area_color, paper_bgcolor=frame_color, height=chart_height,
        margin=dict(t=120, r=80, l=80, b=70), showlegend=True,
        legend=dict(orientation="h", y=1.12, x=0, xanchor='left', bgcolor="rgba(0,0,0,0)", font=dict(color=text_color)),
        images=[dict(source=logo_data, xref="paper", yref="paper", x=1, y=1.15, sizex=0.12, sizey=0.12, xanchor="right", yanchor="top")]
    )
    
    # --- RANGOS 1M Y 10Y ---
    fig.update_xaxes(
        range=[first_valid_date, hoy_real], 
        showgrid=False, linecolor=text_color, linewidth=2, tickfont=dict(color=text_color, size=12), ticks="outside",
        rangeselector=dict(
            buttons=list([
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="1Y", step="year", stepmode="backward"), 
                dict(count=5, label="5Y", step="year", stepmode="backward"),
                dict(count=10, label="10Y", step="year", stepmode="backward"),
                dict(step="all", label="Max")
            ]),
            bgcolor=frame_color, activecolor="#e6e6e6", x=0, y=1.14, xanchor='left', yanchor='bottom', font=dict(size=11, color=text_color) 
        )
    )
    
    # Configurar eje Y izquierdo
    y1_title = f"<b>{col1}</b>" if show_axis_titles else ""
    fig.update_yaxes(
        title=y1_title, 
        title_font=dict(color=COLOR_Y1), 
        showgrid=True, 
        gridcolor="#f0f0f0", 
        gridwidth=1, 
        linecolor=frame_color, 
        tickfont=dict(color=COLOR_Y1, weight="bold"), 
        ticksuffix=suffix1, 
        tickformat=fmt1, 
        zeroline=False, 
        type="log" if log_scale_left else "linear",
        secondary_y=False
    )
    
    if has_secondary:
        y2_title = f"<b>{col2} - Invertido</b>" if invert_y2 else f"<b>{col2}</b>"
        if not show_axis_titles:
            y2_title = ""
        fig.update_yaxes(title=y2_title, title_font=dict(color=COLOR_Y2), showgrid=False, tickfont=dict(color=COLOR_Y2), ticksuffix=suffix2, tickformat=fmt2, autorange="reversed" if invert_y2 else True, secondary_y=True)

    if config_format["rec"]:
        recessions = [
            ("1948-11-01", "1949-10-01"),
            ("1953-07-01", "1954-05-01"),
            ("1957-08-01", "1958-04-01"),
            ("1960-04-01", "1961-02-01"),
            ("1969-12-01", "1970-11-01"),
            ("1973-11-01", "1975-03-01"),
            ("1980-01-01", "1980-07-01"),
            ("1981-07-01", "1982-11-01"),
            ("1990-07-01", "1991-03-01"),
            ("2001-03-01", "2001-11-01"),
            ("2008-01-01", "2009-06-01"),
            ("2020-02-01", "2020-04-01")
        ]
        for start, end in recessions:
            try:
                if pd.Timestamp(end) > first_valid_date:
                    v_s = max(pd.Timestamp(start), first_valid_date)
                    v_e = min(pd.Timestamp(end), hoy_real)
                    fig.add_vrect(x0=v_s, x1=v_e, fillcolor="#e6e6e6", opacity=0.5, layer="below", line_width=0, yref="paper", y0=0, y1=1)
            except: pass
    
    # --- LÍNEA PERSONALIZADA (Create Line) ---
    if custom_line and custom_line.get("enabled", False):
        try:
            dash_map_line = {"Sólida": "solid", "Guiones": "dash", "Puntos": "dot"}
            fig.add_trace(go.Scatter(
                x=[pd.Timestamp(custom_line["x1"]), pd.Timestamp(custom_line["x2"])],
                y=[custom_line["y1"], custom_line["y2"]],
                mode='lines',
                name='Línea personalizada',
                line=dict(
                    color=custom_line.get("color", "#FF0000"),
                    width=2.5,
                    dash=dash_map_line.get(custom_line.get("style", "Sólida"), "solid")
                ),
                hovertemplate="<b>Línea personalizada</b><br>%{x|%Y-%m-%d}: %{y:,.2f}<extra></extra>"
            ), secondary_y=False)
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

    fig.add_annotation(x=0, y=-0.15, text=f"Database: {db_text}", xref="paper", yref="paper", showarrow=False, font=dict(size=10, color="gray"), xanchor="left")
    fig.add_annotation(x=1, y=-0.15, text="Source: <b>XTB Research</b>", xref="paper", yref="paper", showarrow=False, font=dict(size=10, color="black"), xanchor="right")

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

# Opciones de transformación estilo FRED
UNITS_OPTIONS = {
    "Niveles": "lin",
    "Cambio": "chg",
    "Cambio (Año Anterior)": "ch1", 
    "Cambio Porcentual": "pch",
    "Cambio Porcentual (Año Anterior)": "pc1",
    "Tasa Anual Compuesta": "pca",
    "Tasa Continua Compuesta": "cch",
    "Tasa Continua Anual Compuesta": "cca",
    "Log Natural": "log"
}

FREQUENCY_OPTIONS = {
    "Original": None,
    "Diaria": "D",
    "Semanal": "W",
    "Mensual": "M",
    "Trimestral": "Q",
    "Semestral": "2Q",
    "Anual": "A"
}

AGGREGATION_OPTIONS = {
    "Promedio": "mean",
    "Suma": "sum",
    "Fin de Período": "last",
    "Inicio de Período": "first",
    "Máximo": "max",
    "Mínimo": "min"
}

def apply_units_transformation(series, units_type):
    """Aplica transformación de unidades a la serie"""
    import numpy as np
    if units_type == "lin" or units_type is None:
        return series
    elif units_type == "chg":
        return series.diff()
    elif units_type == "ch1":
        return series.diff(12)  # Cambio vs año anterior (asume mensual)
    elif units_type == "pch":
        return series.pct_change() * 100
    elif units_type == "pc1":
        return series.pct_change(12) * 100  # % cambio vs año anterior
    elif units_type == "pca":
        return ((series / series.shift(1)) ** 12 - 1) * 100
    elif units_type == "cch":
        return (series / series.shift(1)).apply(lambda x: np.log(x) * 100 if x > 0 else None)
    elif units_type == "cca":
        return (series / series.shift(1)).apply(lambda x: np.log(x) * 1200 if x > 0 else None)
    elif units_type == "log":
        return series.apply(lambda x: np.log(x) if x > 0 else None)
    return series

def apply_frequency_transformation(series, freq, agg_method):
    """Aplica transformación de frecuencia a la serie"""
    if freq is None:
        return series
    
    agg_func = agg_method if agg_method else "mean"
    return series.resample(freq).agg(agg_func)

def apply_formula(df, formula, col_name):
    """Aplica una fórmula personalizada a los datos"""
    try:
        # Reemplazar 'a' con el nombre de la columna
        safe_formula = formula.replace('a', f'df["{col_name}"]')
        result = eval(safe_formula)
        return result
    except:
        return df[col_name]

with st.sidebar:
    st.divider()
    with st.expander("✏️ Editar Gráfico", expanded=True):
        tab1, tab2, tab3 = st.tabs(["LÍNEA 1", "LÍNEA 2", "FORMATO"])
        
        with tab1:
            st.markdown("**Selección de Serie**")
            y1_sel = st.selectbox("Serie Principal", options=all_opts, index=0)
            
            st.markdown("---")
            st.markdown("**Units**")
            units_y1 = st.selectbox(
                "Transformación", 
                options=list(UNITS_OPTIONS.keys()), 
                index=0,
                key="units_y1",
                help="Transforma los datos: niveles, cambios, porcentajes, etc."
            )
            
            st.markdown("**Modify Frequency**")
            freq_col1, freq_col2 = st.columns(2)
            with freq_col1:
                freq_y1 = st.selectbox(
                    "Frecuencia",
                    options=list(FREQUENCY_OPTIONS.keys()),
                    index=0,
                    key="freq_y1"
                )
            with freq_col2:
                agg_y1 = st.selectbox(
                    "Agregación",
                    options=list(AGGREGATION_OPTIONS.keys()),
                    index=0,
                    key="agg_y1",
                    disabled=(freq_y1 == "Original")
                )
            
            st.markdown("**Customize Data**")
            use_formula_y1 = st.checkbox("Aplicar fórmula", key="use_formula_y1")
            if use_formula_y1:
                formula_y1 = st.text_input(
                    "Fórmula (usa 'a' para la serie)",
                    value="a",
                    key="formula_y1",
                    help="Ejemplos: a*2, a+100, a/1000"
                )
            else:
                formula_y1 = "a"
        
        with tab2:
            st.markdown("**Selección de Serie**")
            y2_sel = st.selectbox("Serie Secundaria", options=["Ninguno"] + all_opts, index=0)
            invert_y2 = st.checkbox("Invertir Eje Y", value=False)
            
            # --- CREATE LINE: Línea definida por usuario ---
            st.markdown("---")
            st.markdown("**User-defined Line**")
            create_line_enabled = st.checkbox("Activar", key="create_line_enabled")
            
            if create_line_enabled:
                cl_col1, cl_col2, cl_col3 = st.columns([2, 0.5, 2])
                with cl_col1:
                    line_x1 = st.date_input("Date start/end:", key="line_x1", label_visibility="visible")
                    line_y1 = st.number_input("Value start/end:", value=0.0, key="line_y1_val")
                with cl_col2:
                    st.markdown("<div style='padding-top: 32px; text-align: center;'>to</div>", unsafe_allow_html=True)
                    st.markdown("<div style='padding-top: 25px; text-align: center;'>to</div>", unsafe_allow_html=True)
                with cl_col3:
                    line_x2 = st.date_input(" ", key="line_x2", label_visibility="hidden")
                    line_y2_val = st.number_input(" ", value=0.0, key="line_y2_val", label_visibility="hidden")
            
            if y2_sel != "Ninguno":
                st.markdown("---")
                st.markdown("**Units**")
                units_y2 = st.selectbox(
                    "Transformación",
                    options=list(UNITS_OPTIONS.keys()),
                    index=0,
                    key="units_y2"
                )
                
                st.markdown("**Modify Frequency**")
                freq_col1_y2, freq_col2_y2 = st.columns(2)
                with freq_col1_y2:
                    freq_y2 = st.selectbox(
                        "Frecuencia",
                        options=list(FREQUENCY_OPTIONS.keys()),
                        index=0,
                        key="freq_y2"
                    )
                with freq_col2_y2:
                    agg_y2 = st.selectbox(
                        "Agregación",
                        options=list(AGGREGATION_OPTIONS.keys()),
                        index=0,
                        key="agg_y2",
                        disabled=(freq_y2 == "Original")
                    )
                
                st.markdown("**Customize Data**")
                use_formula_y2 = st.checkbox("Aplicar fórmula", key="use_formula_y2")
                if use_formula_y2:
                    formula_y2 = st.text_input(
                        "Fórmula (usa 'a' para la serie)",
                        value="a",
                        key="formula_y2"
                    )
                else:
                    formula_y2 = "a"
            else:
                units_y2, freq_y2, agg_y2, formula_y2 = "Niveles", "Original", "Promedio", "a"
        
        with tab3:
            # --- GRAPH TYPE ---
            st.markdown("**Graph Type**")
            graph_type = st.selectbox("Tipo", ["Line", "Bar", "Area"], index=0, key="graph_type")
            
            st.markdown("---")
            
            # --- DETAILS ---
            st.markdown("**Details - Display**")
            show_title = st.checkbox("Title", value=True, key="show_title")
            show_axis_titles = st.checkbox("Axis titles", value=True, key="show_axis_titles")
            show_tooltip = st.checkbox("Tooltip", value=True, key="show_tooltip")
            show_recessions = st.checkbox("Recession shading", value=True, key="show_recessions")
            log_scale_left = st.checkbox("Log scale left", value=False, key="log_scale_left")
            
            st.markdown("**Details - Customize**")
            cust_col1, cust_col2, cust_col3 = st.columns(3)
            with cust_col1:
                frame_color = st.color_picker("Frame", "#FFFFFF", key="frame_color")
            with cust_col2:
                plot_area_color = st.color_picker("Plot area", "#FFFFFF", key="plot_area_color")
            with cust_col3:
                text_color = st.color_picker("Text", "#000000", key="text_color")
            
            dim_col1, dim_col2 = st.columns(2)
            with dim_col1:
                chart_height = st.number_input("Height", value=550, min_value=300, max_value=1000, key="chart_height")
            with dim_col2:
                chart_width = st.number_input("Width", value=1040, min_value=400, max_value=2000, key="chart_width")
            
            st.markdown("---")
            
            # --- LINE 1 ---
            st.markdown("**Line 1**")
            st.caption(y1_sel if y1_sel else "Serie Principal")
            
            l1_row1_col1, l1_row1_col2 = st.columns(2)
            with l1_row1_col1:
                line1_style = st.selectbox("Line style", ["Solid", "Dash", "Dot"], index=0, key="line1_style")
            with l1_row1_col2:
                line1_width = st.selectbox("Width", [1, 2, 3, 4, 5], index=2, key="line1_width")
            
            l1_row2_col1, l1_row2_col2 = st.columns(2)
            with l1_row2_col1:
                col1 = st.color_picker("Color", "#002b49", key="line1_color")
            with l1_row2_col2:
                line1_mark = st.selectbox("Mark type", ["None", "Circle", "Square", "Diamond"], index=0, key="line1_mark")
            
            line1_yaxis = st.radio("Y-Axis position", ["Left", "Right"], index=0, horizontal=True, key="line1_yaxis")
            
            st.markdown("---")
            
            # --- LINE 2 ---
            st.markdown("**Line 2**")
            if y2_sel and y2_sel != "Ninguno":
                st.caption(y2_sel)
            elif st.session_state.get('create_line_enabled', False):
                st.caption("User-defined Line")
            else:
                st.caption("No seleccionada")
            
            l2_row1_col1, l2_row1_col2 = st.columns(2)
            with l2_row1_col1:
                line2_style = st.selectbox("Line style ", ["Solid", "Dash", "Dot"], index=1, key="line2_style")
            with l2_row1_col2:
                line2_width = st.selectbox("Width ", [1, 2, 3, 4, 5], index=2, key="line2_width")
            
            l2_row2_col1, l2_row2_col2 = st.columns(2)
            with l2_row2_col1:
                col2 = st.color_picker("Color ", "#5ca6e5", key="line2_color")
            with l2_row2_col2:
                line2_mark = st.selectbox("Mark type ", ["None", "Circle", "Square", "Diamond"], index=0, key="line2_mark")
            
            line2_yaxis = st.radio("Y-Axis position ", ["Left", "Right"], index=0, horizontal=True, key="line2_yaxis")
            
            # Mapeos
            style_map = {"Solid": "solid", "Dash": "dash", "Dot": "dot"}
            type_map = {"Line": "Línea", "Bar": "Barra", "Area": "Área"}
            
            config_visual = {
                "type": type_map.get(graph_type, "Línea"),
                "color": col1,
                "width": line1_width,
                "rec": show_recessions,
                "color_l2": col2,
                "width_l2": line2_width,
                "dash_l2": style_map.get(line2_style, "dash"),
                "dash_l1": style_map.get(line1_style, "solid"),
                "show_title": show_title,
                "show_axis_titles": show_axis_titles,
                "show_tooltip": show_tooltip,
                "log_scale_left": log_scale_left,
                "frame_color": frame_color,
                "plot_area_color": plot_area_color,
                "text_color": text_color,
                "chart_height": chart_height,
                "chart_width": chart_width,
                "line1_mark": line1_mark,
                "line2_mark": line2_mark,
                "line1_yaxis": line1_yaxis,
                "line2_yaxis": line2_yaxis
            }

# --- APLICAR TRANSFORMACIONES ---
df_transformed = df_full.copy()

# Transformar Y1
if y1_sel in df_transformed.columns:
    series_y1 = df_transformed[y1_sel].copy()
    
    # 1. Aplicar transformación de unidades
    series_y1 = apply_units_transformation(series_y1, UNITS_OPTIONS.get(units_y1))
    
    # 2. Aplicar transformación de frecuencia
    if freq_y1 != "Original":
        series_y1 = apply_frequency_transformation(series_y1, FREQUENCY_OPTIONS.get(freq_y1), AGGREGATION_OPTIONS.get(agg_y1))
    
    # 3. Aplicar fórmula
    if use_formula_y1 and formula_y1 != "a":
        try:
            temp_df = pd.DataFrame({y1_sel: series_y1})
            series_y1 = apply_formula(temp_df, formula_y1, y1_sel)
        except:
            pass
    
    df_transformed[y1_sel] = series_y1

# Transformar Y2
if y2_sel != "Ninguno" and y2_sel in df_transformed.columns:
    series_y2 = df_transformed[y2_sel].copy()
    
    series_y2 = apply_units_transformation(series_y2, UNITS_OPTIONS.get(units_y2))
    
    if freq_y2 != "Original":
        series_y2 = apply_frequency_transformation(series_y2, FREQUENCY_OPTIONS.get(freq_y2), AGGREGATION_OPTIONS.get(agg_y2))
    
    if use_formula_y2 and formula_y2 != "a":
        try:
            temp_df = pd.DataFrame({y2_sel: series_y2})
            series_y2 = apply_formula(temp_df, formula_y2, y2_sel)
        except:
            pass
    
    df_transformed[y2_sel] = series_y2

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

    # === PANEL DE METADATOS ESTILO FRED ===
    date_from, date_to = None, None
    if y1_sel in INDICATOR_CONFIG:
        date_from, date_to = render_metadata_panel(y1_sel, df_full, INDICATOR_CONFIG[y1_sel], fred_api_key=fred_key)
    elif y1_sel in df_full.columns:
        # Para datos personalizados, crear config básica
        custom_config = {
            "src": "custom",
            "is_percent": "%" in y1_sel,
            "meta": {
                "units": "Percent" if "%" in y1_sel else "Value",
                "units_detail": "Custom Data",
                "frequency": "Variable",
                "title": y1_sel
            }
        }
        date_from, date_to = render_metadata_panel(y1_sel, df_full, custom_config)
    
    # Filtrar datos según el rango de fechas seleccionado
    df_filtered = df_transformed.copy()
    if date_from and date_to:
        df_filtered = df_transformed[(df_transformed.index >= pd.Timestamp(date_from)) & (df_transformed.index <= pd.Timestamp(date_to))]

    # Preparar línea personalizada si está habilitada
    custom_line_params = None
    if st.session_state.get('create_line_enabled', False):
        custom_line_params = {
            "enabled": True,
            "x1": st.session_state.get('line_x1'),
            "y1": st.session_state.get('line_y1_val', 0),
            "x2": st.session_state.get('line_x2'),
            "y2": st.session_state.get('line_y2_val', 0),
            "color": "#0066cc",
            "style": "Sólida"
        }

    # CHART
    if y1_sel in df_filtered.columns or (y2_sel != "Ninguno" and y2_sel in df_filtered.columns):
        fig = create_pro_chart(df_filtered, y1_sel, y2_sel, invert_y2, logo_b64, config_visual, custom_source_label=custom_db_label, custom_line=custom_line_params)
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
                        "Cierre Nominal": f"${current_price:,.2f}",
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