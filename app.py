# ============================================================================
# app.py - Sistema de Predicción de Tendencias y Precios Bursátiles con IA
# Universidad Nacional Mayor de San Marcos - Inteligencia de Negocios
# Opción 4: Streamlit Community Cloud
# ============================================================================

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import sqlite3
import os
import joblib
import gc
import datetime
import warnings
import requests #
warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURACIÓN DE PÁGINA
# ============================================================================
st.set_page_config(
    page_title="Sistema Predictivo Bursátil - UNMSM",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# ESTILOS CSS - Fondo Blanco (Política de Ahorro de Tinta)
# ============================================================================
st.markdown("""
<style>
    /* Fondo blanco obligatorio */
    .stApp { background-color: #FFFFFF; }
    section[data-testid="stSidebar"] { background-color: #F8F9FA; }
    
    /* Métricas con bordes claros */
    div[data-testid="stMetric"] {
        background-color: #FFFFFF;
        border: 1px solid #DEE2E6;
        border-radius: 8px;
        padding: 12px;
    }
    
    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #FFFFFF;
        border: 1px solid #DEE2E6;
        border-radius: 6px 6px 0 0;
        color: #333333;
    }
    
    /* Botones con fondo blanco y bordes delineados */
    .stButton > button {
        background-color: #FFFFFF;
        border: 2px solid #0F52BA;
        color: #0F52BA;
        border-radius: 6px;
    }
    .stButton > button:hover {
        background-color: #E8F0FE;
        border: 2px solid #0F52BA;
        color: #0F52BA;
    }
    
    /* Headers */
    h1, h2, h3 { color: #1A1A2E; }
    
    /* Tablas */
    .dataframe { border: 1px solid #DEE2E6; }
    
    /* Señales de compra/venta */
    .signal-buy { color: #28A745; font-weight: bold; }
    .signal-sell { color: #DC3545; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# FUNCIONES DE CACHÉ PARA OPTIMIZAR MEMORIA
# ============================================================================
@st.cache_data(ttl=300)
def descargar_datos(ticker_symbol, periodo="1y"):
    """Descarga datos de Yahoo Finance evadiendo el bloqueo extremo de IP."""
    import requests # Nos aseguramos de que requests esté disponible aquí
    
    try:
        # 1. Sesión con headers extremadamente detallados para engañar al WAF de Yahoo
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0"
        })
        
        # 2. Usamos yf.download pasándole nuestra sesión blindada
        datos = yf.download(tickers=ticker_symbol, period=periodo, session=session, progress=False)
        
        # 3. Validar que la tabla no esté vacía
        if datos is None or datos.empty:
            return None
            
        # 4. Aplanar columnas (yfinance 0.2.40+ devuelve un MultiIndex que rompe Plotly)
        if isinstance(datos.columns, pd.MultiIndex):
            datos.columns = datos.columns.get_level_values(0)
            
        # 5. Quitar zonas horarias para no tener conflictos con SQLite
        if datos.index.tz is not None:
            datos.index = datos.index.tz_localize(None)
            
        return datos
        
    except Exception as e:
        # Si falla, no colapsa la app, solo muestra el error en amarillo
        st.warning(f"El proveedor de datos bloqueó la conexión para {ticker_symbol}. Intenta de nuevo en unos minutos. Detalle: {e}")
        return None

# ============================================================================
# BASE DE DATOS - Inicialización y funciones CRUD
# ============================================================================
DB_PATH = os.path.join('database', 'sistema_inversiones.db')

def init_database():
    """Inicializa la BD si no existe y asegura que el esquema esté actualizado."""
    os.makedirs('database', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Verificar si ya existen tablas
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Usuario'")
    if cursor.fetchone() is None:
        sql_script = """
        CREATE TABLE IF NOT EXISTS Usuario (
            id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            perfil_riesgo TEXT CHECK(perfil_riesgo IN ('Conservador', 'Moderado', 'Agresivo'))
        );
        CREATE TABLE IF NOT EXISTS Activo (
            id_activo INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT UNIQUE NOT NULL,
            nombre_empresa TEXT
        );
        CREATE TABLE IF NOT EXISTS Portafolio (
            id_portafolio INTEGER PRIMARY KEY AUTOINCREMENT,
            id_usuario INTEGER UNIQUE NOT NULL,
            nombre_portafolio TEXT,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (id_usuario) REFERENCES Usuario(id_usuario) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS Portafolio_Activo (
            id_portafolio INTEGER NOT NULL,
            id_activo INTEGER NOT NULL,
            cantidad REAL NOT NULL CHECK(cantidad > 0),
            precio_compra_promedio REAL NOT NULL CHECK(precio_compra_promedio >= 0),
            PRIMARY KEY (id_portafolio, id_activo),
            FOREIGN KEY (id_portafolio) REFERENCES Portafolio(id_portafolio) ON DELETE CASCADE,
            FOREIGN KEY (id_activo) REFERENCES Activo(id_activo) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS Operacion (
            id_operacion INTEGER PRIMARY KEY AUTOINCREMENT,
            id_portafolio INTEGER NOT NULL,
            id_activo INTEGER NOT NULL,
            tipo_operacion TEXT NOT NULL CHECK(tipo_operacion IN ('COMPRA', 'VENTA', 'RECOMPRA', 'SHORT')),
            cantidad REAL NOT NULL CHECK(cantidad > 0),
            precio_unitario REAL NOT NULL CHECK(precio_unitario >= 0),
            fecha_operacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (id_portafolio) REFERENCES Portafolio(id_portafolio),
            FOREIGN KEY (id_activo) REFERENCES Activo(id_activo)
        );
        CREATE TABLE IF NOT EXISTS Prediccion (
            id_prediccion INTEGER PRIMARY KEY AUTOINCREMENT,
            id_activo INTEGER NOT NULL,
            fecha_generacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_objetivo DATE NOT NULL,
            precio_predicho REAL NOT NULL,
            tendencia TEXT,
            modelo_usado TEXT,
            FOREIGN KEY (id_activo) REFERENCES Activo(id_activo) ON DELETE CASCADE
        );
        
        -- Seed Data
        INSERT INTO Activo (ticker, nombre_empresa) VALUES
        ('FSM', 'Fortuna Silver Mines Inc.'),
        ('VOLCABC1.LM', 'Volcan Compañía Minera S.A.A.'),
        ('BVN', 'Compañía de Minas Buenaventura S.A.A.'),
        ('ABX', 'Barrick Gold Corporation'),
        ('BHP', 'BHP Group Limited'),
        ('SCCO', 'Southern Copper Corporation');
        
        INSERT INTO Usuario (nombre, email, perfil_riesgo) VALUES 
        ('Juan Pérez', 'juan@mail.com', 'Moderado'),
        ('María García', 'maria@mail.com', 'Agresivo'),
        ('Carlos López', 'carlos@mail.com', 'Conservador'),
        ('Ana Torres', 'ana@mail.com', 'Moderado'),
        ('Luis Ruiz', 'luis@mail.com', 'Agresivo'),
        ('Elena Díaz', 'elena@mail.com', 'Conservador');
        
        INSERT INTO Portafolio (id_usuario, nombre_portafolio) VALUES 
        (1, 'Fondo Retiro Juan'), (2, 'Inversiones María'),
        (3, 'Ahorro Seguro'), (4, 'Portafolio Crecimiento'),
        (5, 'Trading Activo'), (6, 'Fondo Universitario');
        
        INSERT INTO Portafolio_Activo (id_portafolio, id_activo, cantidad, precio_compra_promedio) VALUES
        (1,1,100,3.50),(1,3,50,8.20),(2,2,5000,0.50),(2,4,75,16.50),(2,6,30,45.00),
        (3,5,40,55.00),(3,6,20,42.00),(4,1,150,3.60),(4,3,25,8.00),(4,4,20,17.00),
        (5,1,50,3.55),(5,2,1000,0.45),(5,3,30,8.10),(5,4,40,16.20),(5,5,10,54.00),(5,6,15,44.00),
        (6,5,30,56.00),(6,3,60,7.90);
        
        INSERT INTO Operacion (id_portafolio, id_activo, tipo_operacion, cantidad, precio_unitario, fecha_operacion) VALUES
        (1,1,'COMPRA',50,3.40,'2025-06-15'),(1,1,'COMPRA',50,3.60,'2025-07-20'),
        (4,1,'COMPRA',200,3.50,'2025-05-10'),(4,1,'VENTA',50,3.80,'2025-08-15'),
        (5,1,'COMPRA',100,3.55,'2025-09-01'),(5,1,'VENTA',50,3.70,'2025-10-10'),
        (2,2,'COMPRA',3000,0.48,'2025-03-01'),(2,2,'COMPRA',3000,0.52,'2025-05-15'),(2,2,'VENTA',1000,0.55,'2025-07-20'),
        (5,2,'COMPRA',500,0.44,'2025-04-10'),(5,2,'COMPRA',1000,0.46,'2025-06-15'),(5,2,'VENTA',500,0.50,'2025-08-20'),
        (1,3,'COMPRA',50,8.20,'2025-02-10'),(1,3,'COMPRA',20,8.00,'2025-04-15'),(1,3,'VENTA',20,8.50,'2025-06-20'),
        (4,3,'COMPRA',25,8.00,'2025-03-15'),(5,3,'COMPRA',30,8.10,'2025-05-20'),(6,3,'COMPRA',60,7.90,'2025-07-25'),
        (2,4,'COMPRA',50,16.00,'2025-01-15'),(2,4,'COMPRA',25,17.00,'2025-03-20'),
        (4,4,'COMPRA',40,16.50,'2025-05-10'),(4,4,'VENTA',20,17.50,'2025-07-15'),
        (5,4,'COMPRA',40,16.20,'2025-02-20'),(5,4,'COMPRA',20,16.00,'2025-04-25'),(5,4,'VENTA',20,16.80,'2025-09-15'),
        (3,5,'COMPRA',20,54.00,'2025-01-20'),(3,5,'COMPRA',20,56.00,'2025-04-15'),
        (5,5,'COMPRA',10,54.00,'2025-06-10'),(6,5,'COMPRA',40,55.00,'2025-03-15'),
        (6,5,'VENTA',10,57.00,'2025-08-20'),(6,5,'COMPRA',10,56.50,'2025-10-01'),
        (2,6,'COMPRA',30,45.00,'2025-02-15'),(3,6,'COMPRA',20,42.00,'2025-04-10'),
        (5,6,'COMPRA',25,43.00,'2025-05-20'),(5,6,'VENTA',10,46.00,'2025-07-25'),
        (2,6,'COMPRA',10,44.00,'2025-09-10'),(2,6,'VENTA',10,47.00,'2025-11-15');
        """
        cursor.executescript(sql_script)
        conn.commit()

    # Parche para bases de datos antiguas: asegurar que la columna 'tendencia' existe
    cursor.execute("PRAGMA table_info(Prediccion)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'tendencia' not in columns:
        try:
            cursor.execute("ALTER TABLE Prediccion ADD COLUMN tendencia TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            # La columna podría estar siendo añadida por otro proceso, lo ignoramos
            pass
            
    conn.close()
def get_db_connection():
    """Retorna una conexión a la BD."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def ejecutar_query(query, params=None):
    """Ejecuta una query SELECT y devuelve un DataFrame."""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        conn.close()

def ejecutar_insert(query, params=None):
    """Ejecuta un INSERT/UPDATE y confirma."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()

# Inicializar base de datos al arrancar
init_database()

# ============================================================================
# FUNCIONES DE MODELOS PREDICTIVOS
# ============================================================================

def calcular_indicadores_tecnicos(df):
    """Calcula indicadores técnicos sobre datos OHLCV."""
    data = df.copy()
    # Moving Averages
    data['SMA_5'] = data['Close'].rolling(window=5).mean()
    data['SMA_10'] = data['Close'].rolling(window=10).mean()
    data['SMA_20'] = data['Close'].rolling(window=20).mean()
    data['EMA_12'] = data['Close'].ewm(span=12, adjust=False).mean()
    data['EMA_26'] = data['Close'].ewm(span=26, adjust=False).mean()
    
    # MACD
    data['MACD'] = data['EMA_12'] - data['EMA_26']
    data['MACD_Signal'] = data['MACD'].ewm(span=9, adjust=False).mean()
    
    # RSI
    delta = data['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    data['RSI'] = 100 - (100 / (1 + rs))
    
    # Bollinger Bands
    data['BB_Mid'] = data['Close'].rolling(window=20).mean()
    bb_std = data['Close'].rolling(window=20).std()
    data['BB_Upper'] = data['BB_Mid'] + 2 * bb_std
    data['BB_Lower'] = data['BB_Mid'] - 2 * bb_std
    
    # Retornos
    data['Returns'] = data['Close'].pct_change()
    data['Log_Returns'] = np.log(data['Close'] / data['Close'].shift(1))
    
    # Volatilidad
    data['Volatility_20'] = data['Returns'].rolling(window=20).std() * np.sqrt(252)
    
    # Target para clasificación: 1 si sube mañana, 0 si baja
    data['Target'] = (data['Close'].shift(-1) > data['Close']).astype(int)
    
    data.dropna(inplace=True)
    return data

def modelo_svc_prediccion(data):
    """Modelo SVC (2.1.1) - Support Vector Classifier."""
    from sklearn.svm import SVC
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report
    
    features = ['Open', 'High', 'Low', 'Close', 'Volume', 'SMA_5', 'SMA_10', 'SMA_20', 'RSI', 'MACD']
    X = data[features].values
    y = data['Target'].values
    
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    
    scaler = MinMaxScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    
    model = SVC(kernel='rbf', C=1.0, gamma='scale', probability=True)
    model.fit(X_train_s, y_train)
    
    y_pred = model.predict(X_test_s)
    y_prob = model.predict_proba(X_test_s)[:, 1]
    
    # Predicción para mañana (último dato disponible)
    ultimo = scaler.transform(X[-1:])
    pred_manana = model.predict(ultimo)[0]
    prob_manana = model.predict_proba(ultimo)[0]
    
    metricas = {
        'accuracy': accuracy_score(y_test, y_pred),
        'precision': precision_score(y_test, y_pred, zero_division=0),
        'recall': recall_score(y_test, y_pred, zero_division=0),
        'f1': f1_score(y_test, y_pred, zero_division=0),
    }
    
    return pred_manana, prob_manana, y_test, y_pred, metricas, model

def modelo_rnn_simple_prediccion(data, window=10):
    """Modelo SimpleRNN Classifier (2.1.2)."""
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    
    features = ['Close', 'Volume', 'SMA_5', 'RSI', 'MACD']
    X_raw = data[features].values
    y_raw = data['Target'].values
    
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_raw)
    
    X_seq, y_seq = [], []
    for i in range(window, len(X_scaled)):
        X_seq.append(X_scaled[i-window:i])
        y_seq.append(y_raw[i])
    X_seq = np.array(X_seq)
    y_seq = np.array(y_seq)
    
    split = int(len(X_seq) * 0.8)
    X_train, X_test = X_seq[:split], X_seq[split:]
    y_train, y_test = y_seq[:split], y_seq[split:]
    
    try:
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import SimpleRNN, Dense, Dropout
        
        model = Sequential([
            SimpleRNN(64, input_shape=(window, len(features)), return_sequences=False),
            Dropout(0.2),
            Dense(32, activation='relu'),
            Dense(1, activation='sigmoid')
        ])
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        model.fit(X_train, y_train, epochs=20, batch_size=32, verbose=0, validation_split=0.1)
        
        y_prob = model.predict(X_test, verbose=0).flatten()
        y_pred = (y_prob >= 0.5).astype(int)
        
        pred_manana = (model.predict(X_seq[-1:], verbose=0).flatten()[0] >= 0.5).astype(int)
        prob_manana = model.predict(X_seq[-1:], verbose=0).flatten()[0]
    except ImportError:
        # Fallback sin TensorFlow: usar Logistic Regression como proxy
        from sklearn.linear_model import LogisticRegression
        X_train_flat = X_train.reshape(X_train.shape[0], -1)
        X_test_flat = X_test.reshape(X_test.shape[0], -1)
        
        model = LogisticRegression(max_iter=1000)
        model.fit(X_train_flat, y_train)
        y_pred = model.predict(X_test_flat)
        y_prob = model.predict_proba(X_test_flat)[:, 1]
        
        ultimo_flat = X_seq[-1:].reshape(1, -1)
        pred_manana = model.predict(ultimo_flat)[0]
        prob_manana = model.predict_proba(ultimo_flat)[0][1]
    
    metricas = {
        'accuracy': accuracy_score(y_test, y_pred),
        'precision': precision_score(y_test, y_pred, zero_division=0),
        'recall': recall_score(y_test, y_pred, zero_division=0),
        'f1': f1_score(y_test, y_pred, zero_division=0),
    }
    
    return pred_manana, prob_manana if isinstance(prob_manana, float) else float(prob_manana), y_test, y_pred, metricas

def modelo_lstm_classifier(data, window=10):
    """Modelo LSTM Classifier (2.1.3)."""
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    
    features = ['Close', 'Volume', 'SMA_5', 'SMA_10', 'RSI', 'MACD']
    X_raw = data[features].values
    y_raw = data['Target'].values
    
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_raw)
    
    X_seq, y_seq = [], []
    for i in range(window, len(X_scaled)):
        X_seq.append(X_scaled[i-window:i])
        y_seq.append(y_raw[i])
    X_seq = np.array(X_seq)
    y_seq = np.array(y_seq)
    
    split = int(len(X_seq) * 0.8)
    X_train, X_test = X_seq[:split], X_seq[split:]
    y_train, y_test = y_seq[:split], y_seq[split:]
    
    try:
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout
        
        model = Sequential([
            LSTM(64, input_shape=(window, len(features)), return_sequences=False),
            Dropout(0.2),
            Dense(32, activation='relu'),
            Dense(1, activation='sigmoid')
        ])
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        model.fit(X_train, y_train, epochs=20, batch_size=32, verbose=0, validation_split=0.1)
        
        y_prob = model.predict(X_test, verbose=0).flatten()
        y_pred = (y_prob >= 0.5).astype(int)
        pred_manana = (model.predict(X_seq[-1:], verbose=0).flatten()[0] >= 0.5).astype(int)
        prob_manana = float(model.predict(X_seq[-1:], verbose=0).flatten()[0])
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier
        X_train_flat = X_train.reshape(X_train.shape[0], -1)
        X_test_flat = X_test.reshape(X_test.shape[0], -1)
        
        model = GradientBoostingClassifier(n_estimators=100, max_depth=3)
        model.fit(X_train_flat, y_train)
        y_pred = model.predict(X_test_flat)
        y_prob = model.predict_proba(X_test_flat)[:, 1]
        
        ultimo_flat = X_seq[-1:].reshape(1, -1)
        pred_manana = model.predict(ultimo_flat)[0]
        prob_manana = float(model.predict_proba(ultimo_flat)[0][1])
    
    metricas = {
        'accuracy': accuracy_score(y_test, y_pred),
        'precision': precision_score(y_test, y_pred, zero_division=0),
        'recall': recall_score(y_test, y_pred, zero_division=0),
        'f1': f1_score(y_test, y_pred, zero_division=0),
    }
    
    return pred_manana, prob_manana, y_test, y_pred, metricas

def modelo_bilstm_classifier(data, window=10):
    """Modelo BiLSTM Classifier (2.1.4)."""
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    
    features = ['Close', 'Volume', 'SMA_5', 'SMA_10', 'RSI', 'MACD']
    X_raw = data[features].values
    y_raw = data['Target'].values
    
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_raw)
    
    X_seq, y_seq = [], []
    for i in range(window, len(X_scaled)):
        X_seq.append(X_scaled[i-window:i])
        y_seq.append(y_raw[i])
    X_seq = np.array(X_seq)
    y_seq = np.array(y_seq)
    
    split = int(len(X_seq) * 0.8)
    X_train, X_test = X_seq[:split], X_seq[split:]
    y_train, y_test = y_seq[:split], y_seq[split:]
    
    try:
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Bidirectional, Dense, Dropout
        
        model = Sequential([
            Bidirectional(LSTM(64, return_sequences=False), input_shape=(window, len(features))),
            Dropout(0.2),
            Dense(32, activation='relu'),
            Dense(1, activation='sigmoid')
        ])
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        model.fit(X_train, y_train, epochs=20, batch_size=32, verbose=0, validation_split=0.1)
        
        y_prob = model.predict(X_test, verbose=0).flatten()
        y_pred = (y_prob >= 0.5).astype(int)
        pred_manana = (model.predict(X_seq[-1:], verbose=0).flatten()[0] >= 0.5).astype(int)
        prob_manana = float(model.predict(X_seq[-1:], verbose=0).flatten()[0])
    except ImportError:
        from sklearn.ensemble import RandomForestClassifier
        X_train_flat = X_train.reshape(X_train.shape[0], -1)
        X_test_flat = X_test.reshape(X_test.shape[0], -1)
        
        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X_train_flat, y_train)
        y_pred = model.predict(X_test_flat)
        y_prob = model.predict_proba(X_test_flat)[:, 1]
        
        ultimo_flat = X_seq[-1:].reshape(1, -1)
        pred_manana = model.predict(ultimo_flat)[0]
        prob_manana = float(model.predict_proba(ultimo_flat)[0][1])
    
    metricas = {
        'accuracy': accuracy_score(y_test, y_pred),
        'precision': precision_score(y_test, y_pred, zero_division=0),
        'recall': recall_score(y_test, y_pred, zero_division=0),
        'f1': f1_score(y_test, y_pred, zero_division=0),
    }
    
    return pred_manana, prob_manana, y_test, y_pred, metricas

def modelo_gru_classifier(data, window=10):
    """Modelo GRU Classifier (2.1.5)."""
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
    
    features = ['Close', 'Volume', 'SMA_5', 'SMA_10', 'RSI', 'MACD']
    X_raw = data[features].values
    y_raw = data['Target'].values
    
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_raw)
    
    X_seq, y_seq = [], []
    for i in range(window, len(X_scaled)):
        X_seq.append(X_scaled[i-window:i])
        y_seq.append(y_raw[i])
    X_seq = np.array(X_seq)
    y_seq = np.array(y_seq)
    
    split = int(len(X_seq) * 0.8)
    X_train, X_test = X_seq[:split], X_seq[split:]
    y_train, y_test = y_seq[:split], y_seq[split:]
    
    try:
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import GRU, Dense, Dropout
        
        model = Sequential([
            GRU(64, input_shape=(window, len(features)), return_sequences=False),
            Dropout(0.2),
            Dense(32, activation='relu'),
            Dense(1, activation='sigmoid')
        ])
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        model.fit(X_train, y_train, epochs=20, batch_size=32, verbose=0, validation_split=0.1)
        
        y_prob = model.predict(X_test, verbose=0).flatten()
        y_pred = (y_prob >= 0.5).astype(int)
        pred_manana = (model.predict(X_seq[-1:], verbose=0).flatten()[0] >= 0.5).astype(int)
        prob_manana = float(model.predict(X_seq[-1:], verbose=0).flatten()[0])
    except ImportError:
        from sklearn.ensemble import AdaBoostClassifier
        X_train_flat = X_train.reshape(X_train.shape[0], -1)
        X_test_flat = X_test.reshape(X_test.shape[0], -1)
        
        model = AdaBoostClassifier(n_estimators=100, random_state=42)
        model.fit(X_train_flat, y_train)
        y_pred = model.predict(X_test_flat)
        y_prob = model.predict_proba(X_test_flat)[:, 1]
        
        ultimo_flat = X_seq[-1:].reshape(1, -1)
        pred_manana = model.predict(ultimo_flat)[0]
        prob_manana = float(model.predict_proba(ultimo_flat)[0][1])
    
    metricas = {
        'accuracy': accuracy_score(y_test, y_pred),
        'precision': precision_score(y_test, y_pred, zero_division=0),
        'recall': recall_score(y_test, y_pred, zero_division=0),
        'f1': f1_score(y_test, y_pred, zero_division=0),
    }
    
    return pred_manana, prob_manana, y_test, y_pred, metricas

def modelo_arima_regresion(data, steps=1):
    """Modelo ARIMA (2.2.1) - Regresión de precios."""
    from sklearn.metrics import mean_squared_error, mean_absolute_error
    
    close_prices = data['Close'].values
    split = int(len(close_prices) * 0.8)
    train = close_prices[:split]
    test = close_prices[split:]
    
    try:
        from statsmodels.tsa.arima.model import ARIMA
        model = ARIMA(train, order=(5, 1, 0))
        model_fit = model.fit()
        
        # Predicciones sobre test set
        predictions = []
        history = list(train)
        for t in range(len(test)):
            m = ARIMA(history, order=(5, 1, 0))
            m_fit = m.fit()
            yhat = m_fit.forecast(steps=1)[0]
            predictions.append(yhat)
            history.append(test[t])
        predictions = np.array(predictions)
        
        # Predicción para mañana
        model_full = ARIMA(close_prices, order=(5, 1, 0))
        model_full_fit = model_full.fit()
        precio_predicho = model_full_fit.forecast(steps=steps)[0]
        
    except (ImportError, Exception):
        # Fallback: media móvil simple
        predictions = pd.Series(close_prices[split:]).rolling(5, min_periods=1).mean().values
        precio_predicho = float(np.mean(close_prices[-5:]))
    
    rmse = np.sqrt(mean_squared_error(test[:len(predictions)], predictions[:len(test)]))
    mae = mean_absolute_error(test[:len(predictions)], predictions[:len(test)])
    
    precio_actual = close_prices[-1]
    tendencia = "SUBIDA" if precio_predicho > precio_actual else "BAJADA"
    
    metricas = {'rmse': rmse, 'mae': mae}
    
    return precio_predicho, tendencia, test, predictions, metricas, data.index[split:]

def modelo_lstm_regressor(data, window=10):
    """Modelo LSTM Regressor (2.2.2) - Predicción de precios."""
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.metrics import mean_squared_error, mean_absolute_error
    
    close_prices = data['Close'].values.reshape(-1, 1)
    
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(close_prices)
    
    X_seq, y_seq = [], []
    for i in range(window, len(scaled)):
        X_seq.append(scaled[i-window:i, 0])
        y_seq.append(scaled[i, 0])
    X_seq = np.array(X_seq).reshape(-1, window, 1)
    y_seq = np.array(y_seq)
    
    split = int(len(X_seq) * 0.8)
    X_train, X_test = X_seq[:split], X_seq[split:]
    y_train, y_test = y_seq[:split], y_seq[split:]
    
    try:
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout
        
        model = Sequential([
            LSTM(50, input_shape=(window, 1), return_sequences=True),
            Dropout(0.2),
            LSTM(50, return_sequences=False),
            Dropout(0.2),
            Dense(25, activation='relu'),
            Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse')
        model.fit(X_train, y_train, epochs=20, batch_size=32, verbose=0, validation_split=0.1)
        
        y_pred_scaled = model.predict(X_test, verbose=0).flatten()
        pred_manana_scaled = model.predict(X_seq[-1:], verbose=0).flatten()[0]
    except ImportError:
        from sklearn.svm import SVR
        X_train_flat = X_train.reshape(X_train.shape[0], -1)
        X_test_flat = X_test.reshape(X_test.shape[0], -1)
        
        model = SVR(kernel='rbf')
        model.fit(X_train_flat, y_train)
        y_pred_scaled = model.predict(X_test_flat)
        pred_manana_scaled = model.predict(X_seq[-1:].reshape(1, -1))[0]
    
    # Invertir escalado
    y_pred_real = scaler.inverse_transform(y_pred_scaled.reshape(-1, 1)).flatten()
    y_test_real = scaler.inverse_transform(y_test.reshape(-1, 1)).flatten()
    precio_predicho = scaler.inverse_transform([[pred_manana_scaled]])[0][0]
    
    rmse = np.sqrt(mean_squared_error(y_test_real, y_pred_real))
    mae = mean_absolute_error(y_test_real, y_pred_real)
    
    precio_actual = close_prices[-1][0]
    tendencia = "SUBIDA" if precio_predicho > precio_actual else "BAJADA"
    
    metricas = {'rmse': rmse, 'mae': mae}
    
    return precio_predicho, tendencia, y_test_real, y_pred_real, metricas

def modelo_arima_lstm_ensamblaje(precio_arima, precio_lstm, precio_actual):
    """Modelo ARIMA-LSTM Ensamblaje (2.2.3)."""
    # Promedio ponderado: 40% ARIMA, 60% LSTM
    precio_ensamblado = 0.4 * precio_arima + 0.6 * precio_lstm
    tendencia = "SUBIDA" if precio_ensamblado > precio_actual else "BAJADA"
    return precio_ensamblado, tendencia

# ============================================================================
# FUNCIONES DE BACKTESTING
# ============================================================================

def ejecutar_backtesting(data, señales, nombre_modelo, capital_inicial=10000, comision=0.001):
    """Ejecuta backtesting básico sobre las señales de un modelo."""
    close = data['Close'].values[-len(señales):]
    
    capital = capital_inicial
    posicion = 0
    acciones = 0
    historial_capital = [capital_inicial]
    trades = 0
    ganancias = 0
    perdidas = 0
    
    for i in range(1, len(señales)):
        precio = close[i]
        if señales[i] == 1 and posicion == 0:  # Comprar
            acciones = capital / precio
            capital = 0
            posicion = 1
            trades += 1
            precio_compra = precio
        elif señales[i] == 0 and posicion == 1:  # Vender
            capital = acciones * precio
            posicion = 0
            trades += 1
            if precio > precio_compra:
                ganancias += 1
            else:
                perdidas += 1
            acciones = 0
        
        valor_actual = capital + acciones * precio if posicion == 1 else capital
        historial_capital.append(valor_actual)
    
    # Si termina con posición abierta
    if posicion == 1:
        capital = acciones * close[-1]
    
    capital_final = capital if posicion == 0 else acciones * close[-1]
    retorno_total = (capital_final - capital_inicial) / capital_inicial * 100
    
    # Buy and Hold para comparación
    bh_return = (close[-1] - close[0]) / close[0] * 100
    
    # Calcular métricas
    historial = np.array(historial_capital)
    returns = np.diff(historial) / historial[:-1]
    
    sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
    
    # Max Drawdown
    peak = np.maximum.accumulate(historial)
    drawdown = (historial - peak) / peak
    max_drawdown = np.min(drawdown) * 100
    
    win_rate = ganancias / (ganancias + perdidas) * 100 if (ganancias + perdidas) > 0 else 0
    
    return {
        'modelo': nombre_modelo,
        'capital_inicial': capital_inicial,
        'capital_final': round(capital_final, 2),
        'retorno_total': round(retorno_total, 2),
        'retorno_buyhold': round(bh_return, 2),
        'sharpe_ratio': round(sharpe, 4),
        'max_drawdown': round(max_drawdown, 2),
        'total_trades': trades,
        'win_rate': round(win_rate, 2),
        'historial': historial
    }

# ============================================================================
# GRÁFICOS DE VELAS JAPONESAS CON PLOTLY
# ============================================================================
def grafico_velas_japonesas(df, ticker_name, periodo_label):
    """Genera gráfico de velas japonesas con Plotly."""
    import plotly.graph_objects as go
    
    fig = go.Figure(data=[go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        increasing_line_color='#28A745',
        decreasing_line_color='#DC3545',
        increasing_fillcolor='#28A745',
        decreasing_fillcolor='#DC3545'
    )])
    
    # Agregar medias móviles si existen
    if 'SMA_20' in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df['SMA_20'],
            mode='lines', name='SMA 20',
            line=dict(color='#0F52BA', width=1.5)
        ))
    if 'SMA_5' in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df['SMA_5'],
            mode='lines', name='SMA 5',
            line=dict(color='#FF8C00', width=1)
        ))
    if 'BB_Upper' in df.columns:
        fig.add_trace(go.Scatter(
            x=df.index, y=df['BB_Upper'],
            mode='lines', name='BB Superior',
            line=dict(color='#999999', width=0.8, dash='dot')
        ))
        fig.add_trace(go.Scatter(
            x=df.index, y=df['BB_Lower'],
            mode='lines', name='BB Inferior',
            line=dict(color='#999999', width=0.8, dash='dot'),
            fill='tonexty', fillcolor='rgba(200,200,200,0.1)'
        ))
    
    fig.update_layout(
        title=f"Velas Japonesas - {ticker_name} ({periodo_label})",
        yaxis_title="Precio (USD)",
        xaxis_title="Fecha",
        template="plotly_white",
        plot_bgcolor='#FFFFFF',
        paper_bgcolor='#FFFFFF',
        xaxis_rangeslider_visible=False,
        height=500,
        font=dict(color='#333333')
    )
    
    return fig

def grafico_volumen(df):
    """Genera gráfico de volumen."""
    import plotly.graph_objects as go
    
    colors = ['#28A745' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#DC3545' for i in range(len(df))]
    
    fig = go.Figure(data=[go.Bar(
        x=df.index, y=df['Volume'],
        marker_color=colors,
        opacity=0.7
    )])
    
    fig.update_layout(
        title="Volumen de Transacciones",
        yaxis_title="Volumen",
        template="plotly_white",
        plot_bgcolor='#FFFFFF',
        paper_bgcolor='#FFFFFF',
        height=250,
        font=dict(color='#333333')
    )
    
    return fig

def grafico_rsi(df):
    """Genera gráfico de RSI."""
    import plotly.graph_objects as go
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], mode='lines', name='RSI', line=dict(color='#0F52BA', width=1.5)))
    fig.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Sobrecompra (70)")
    fig.add_hline(y=30, line_dash="dash", line_color="green", annotation_text="Sobreventa (30)")
    
    fig.update_layout(
        title="RSI (Relative Strength Index)",
        yaxis_title="RSI",
        template="plotly_white",
        plot_bgcolor='#FFFFFF',
        paper_bgcolor='#FFFFFF',
        height=250,
        yaxis=dict(range=[0, 100]),
        font=dict(color='#333333')
    )
    
    return fig

# ============================================================================
# SIDEBAR - PANEL DE CONTROL
# ============================================================================
st.sidebar.markdown("## Panel de Control")

# Selector de empresa
empresas = {
    "FSM": "Fortuna Silver Mines",
    "VOLCABC1.LM": "Volcan Cía Minera",
    "BVN": "Buenaventura S.A.A.",
    "ABX": "Barrick Gold Corp.",
    "BHP": "BHP Billiton",
    "SCCO": "Southern Copper"
}
ticker = st.sidebar.selectbox(
    "Seleccione Activo Financiero:",
    list(empresas.keys()),
    format_func=lambda x: f"{x} - {empresas[x]}"
)

# Período de datos
periodo = st.sidebar.selectbox("Período de datos:", ["3mo", "6mo", "1y", "2y", "5y"], index=2)
periodo_labels = {"3mo": "3 Meses", "6mo": "6 Meses", "1y": "1 Año", "2y": "2 Años", "5y": "5 Años"}

st.sidebar.markdown("---")

# Autenticación de usuario
st.sidebar.markdown("### Usuario")
try:
    usuarios_df = ejecutar_query("SELECT id_usuario, nombre, perfil_riesgo FROM Usuario")
    if not usuarios_df.empty:
        usuario_seleccionado = st.sidebar.selectbox("Usuario activo:", usuarios_df['nombre'].tolist())
        perfil = usuarios_df[usuarios_df['nombre'] == usuario_seleccionado]['perfil_riesgo'].values[0]
        id_usuario = int(usuarios_df[usuarios_df['nombre'] == usuario_seleccionado]['id_usuario'].values[0])
        st.sidebar.info(f"**Perfil de Riesgo:** {perfil}")
    else:
        usuario_seleccionado = None
        id_usuario = None
except Exception:
    usuario_seleccionado = None
    id_usuario = None
    st.sidebar.warning("BD no conectada.")

st.sidebar.markdown("---")
st.sidebar.markdown("### Información del Sistema")
st.sidebar.caption("UNMSM - Inteligencia de Negocios 2025-I")
st.sidebar.caption("Docente: Mg. Ernesto David Cancho Rodríguez")
st.sidebar.caption("Equipo 2")

# ============================================================================
# HEADER PRINCIPAL
# ============================================================================
st.title("Sistema Predictivo de Tendencias y Precios Bursátiles")
st.markdown("Plataforma de análisis financiero con **Machine Learning** y **Deep Learning** — UNMSM")
st.markdown("---")

# ============================================================================
# DESCARGA DE DATOS
# ============================================================================
datos_raw = descargar_datos(ticker, periodo)

if datos_raw is not None and not datos_raw.empty:
    
    # Calcular indicadores técnicos
    datos_con_indicadores = calcular_indicadores_tecnicos(datos_raw.copy())
    
    # ========================================================================
    # KPIs SUPERIORES
    # ========================================================================
    st.subheader(f"Cotización: {empresas[ticker]} ({ticker})")
    
    precio_actual = float(datos_raw['Close'].iloc[-1])
    precio_anterior = float(datos_raw['Close'].iloc[-2])
    variacion = precio_actual - precio_anterior
    variacion_pct = (variacion / precio_anterior) * 100
    vol_actual = float(datos_raw['Volume'].iloc[-1])
    high_hoy = float(datos_raw['High'].iloc[-1])
    low_hoy = float(datos_raw['Low'].iloc[-1])
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Precio Actual", f"${precio_actual:.2f}", f"{variacion:+.2f} ({variacion_pct:+.2f}%)")
    col2.metric("Volumen", f"{vol_actual:,.0f}")
    col3.metric("Rango del Día", f"${low_hoy:.2f} — ${high_hoy:.2f}")
    col4.metric("Tendencia", "ALCISTA" if variacion > 0 else "BAJISTA", f"{'Subida' if variacion > 0 else 'Bajada'}")
    
    st.markdown("---")
    
    # ========================================================================
    # TABS PRINCIPALES
    # ========================================================================
    tab_dashboard, tab_clasificacion, tab_regresion, tab_backtesting, tab_portafolio, tab_operaciones, tab_bd = st.tabs([
        "Dashboard",
        "Modelos de Clasificación",
        "Modelos de Regresión",
        "Backtesting",
        "Portafolios",
        "Operaciones",
        "Base de Datos"
    ])
    
    # ====================================================================
    # TAB 1: DASHBOARD
    # ====================================================================
    with tab_dashboard:
        st.markdown("### Dashboard de Análisis Técnico")
        
        # Gráfico de velas japonesas
        fig_velas = grafico_velas_japonesas(datos_con_indicadores, empresas[ticker], periodo_labels[periodo])
        st.plotly_chart(fig_velas, use_container_width=True)
        
        col_v, col_r = st.columns(2)
        with col_v:
            fig_vol = grafico_volumen(datos_raw)
            st.plotly_chart(fig_vol, use_container_width=True)
        with col_r:
            fig_rsi = grafico_rsi(datos_con_indicadores)
            st.plotly_chart(fig_rsi, use_container_width=True)
        
        # Indicadores actuales
        st.markdown("### Indicadores Técnicos Actuales")
        col_i1, col_i2, col_i3, col_i4, col_i5 = st.columns(5)
        ultimo = datos_con_indicadores.iloc[-1]
        col_i1.metric("RSI (14)", f"{ultimo['RSI']:.2f}")
        col_i2.metric("SMA 20", f"${ultimo['SMA_20']:.2f}")
        col_i3.metric("MACD", f"{ultimo['MACD']:.4f}")
        col_i4.metric("Volatilidad 20d", f"{ultimo['Volatility_20']:.2%}")
        col_i5.metric("BB Superior", f"${ultimo['BB_Upper']:.2f}")
        
        # Tabla de datos históricos
        with st.expander("Ver datos históricos completos"):
            st.dataframe(datos_raw.tail(30).style.format({
                'Open': '${:.2f}', 'High': '${:.2f}', 'Low': '${:.2f}',
                'Close': '${:.2f}', 'Volume': '{:,.0f}'
            }), use_container_width=True)
    
    # ====================================================================
    # TAB 2: MODELOS DE CLASIFICACIÓN
    # ====================================================================
    with tab_clasificacion:
        st.markdown("### Modelos de Clasificación — Predicción de Tendencia (Subida/Bajada)")
        st.markdown(f"**Activo:** {empresas[ticker]} ({ticker}) | **Predicción:** Tendencia del día siguiente")
        
        if st.button("Ejecutar Todos los Modelos de Clasificación", key="btn_clf"):
            resultados_clf = {}
            
            with st.spinner("Ejecutando Modelo 2.1.1: SVC (Support Vector Classifier)..."):
                try:
                    pred, prob, y_test, y_pred, metricas, _ = modelo_svc_prediccion(datos_con_indicadores)
                    resultados_clf['SVC (2.1.1)'] = {
                        'prediccion': pred, 'probabilidad': prob,
                        'y_test': y_test, 'y_pred': y_pred, 'metricas': metricas
                    }
                except Exception as e:
                    st.error(f"Error SVC: {e}")
            
            with st.spinner("Ejecutando Modelo 2.1.2: SimpleRNN Classifier..."):
                try:
                    pred, prob, y_test, y_pred, metricas = modelo_rnn_simple_prediccion(datos_con_indicadores)
                    resultados_clf['SimpleRNN (2.1.2)'] = {
                        'prediccion': pred, 'probabilidad': prob,
                        'y_test': y_test, 'y_pred': y_pred, 'metricas': metricas
                    }
                except Exception as e:
                    st.error(f"Error SimpleRNN: {e}")
            
            with st.spinner("Ejecutando Modelo 2.1.3: LSTM Classifier..."):
                try:
                    pred, prob, y_test, y_pred, metricas = modelo_lstm_classifier(datos_con_indicadores)
                    resultados_clf['LSTM Classifier (2.1.3)'] = {
                        'prediccion': pred, 'probabilidad': prob,
                        'y_test': y_test, 'y_pred': y_pred, 'metricas': metricas
                    }
                except Exception as e:
                    st.error(f"Error LSTM Classifier: {e}")
            
            with st.spinner("Ejecutando Modelo 2.1.4: BiLSTM Classifier..."):
                try:
                    pred, prob, y_test, y_pred, metricas = modelo_bilstm_classifier(datos_con_indicadores)
                    resultados_clf['BiLSTM (2.1.4)'] = {
                        'prediccion': pred, 'probabilidad': prob,
                        'y_test': y_test, 'y_pred': y_pred, 'metricas': metricas
                    }
                except Exception as e:
                    st.error(f"Error BiLSTM: {e}")
            
            with st.spinner("Ejecutando Modelo 2.1.5: GRU Classifier..."):
                try:
                    pred, prob, y_test, y_pred, metricas = modelo_gru_classifier(datos_con_indicadores)
                    resultados_clf['GRU (2.1.5)'] = {
                        'prediccion': pred, 'probabilidad': prob,
                        'y_test': y_test, 'y_pred': y_pred, 'metricas': metricas
                    }
                except Exception as e:
                    st.error(f"Error GRU: {e}")
            
            if resultados_clf:
                st.session_state['resultados_clf'] = resultados_clf
                st.success("Todos los modelos de clasificación ejecutados correctamente.")
        
        # Mostrar resultados
        if 'resultados_clf' in st.session_state:
            resultados_clf = st.session_state['resultados_clf']
            
            # Tabla de predicciones
            st.markdown("#### Predicciones para el Próximo Día")
            pred_data = []
            for nombre, res in resultados_clf.items():
                tendencia = "SUBIDA" if res['prediccion'] == 1 else "BAJADA"
                recomendacion = "COMPRAR" if res['prediccion'] == 1 else "VENDER / ESPERAR"
                if isinstance(res['probabilidad'], np.ndarray):
                    confianza = float(max(res['probabilidad']))
                else:
                    confianza = float(res['probabilidad']) if res['prediccion'] == 1 else 1 - float(res['probabilidad'])
                pred_data.append({
                    'Modelo': nombre,
                    'Tendencia': tendencia,
                    'Confianza': f"{confianza:.2%}",
                    'Recomendación': recomendacion
                })
            
            df_pred = pd.DataFrame(pred_data)
            st.dataframe(df_pred, use_container_width=True, hide_index=True)
            
            # Consenso
            votos_subida = sum(1 for r in resultados_clf.values() if r['prediccion'] == 1)
            total_modelos = len(resultados_clf)
            if votos_subida > total_modelos / 2:
                st.success(f"**CONSENSO: SUBIDA** ({votos_subida}/{total_modelos} modelos predicen subida) — Recomendación: COMPRAR")
            else:
                st.error(f"**CONSENSO: BAJADA** ({total_modelos - votos_subida}/{total_modelos} modelos predicen bajada) — Recomendación: VENDER / ESPERAR")
            
            # Tabla comparativa de métricas
            st.markdown("#### Comparativa de Métricas de Evaluación")
            metricas_data = []
            for nombre, res in resultados_clf.items():
                m = res['metricas']
                metricas_data.append({
                    'Modelo': nombre,
                    'Accuracy': f"{m['accuracy']:.4f}",
                    'Precision': f"{m['precision']:.4f}",
                    'Recall': f"{m['recall']:.4f}",
                    'F1 Score': f"{m['f1']:.4f}"
                })
            
            df_metricas = pd.DataFrame(metricas_data)
            st.dataframe(df_metricas, use_container_width=True, hide_index=True)
            
            # Gráfico comparativo de métricas
            import plotly.graph_objects as go
            
            fig_comp = go.Figure()
            modelos_nombres = [m['Modelo'] for m in metricas_data]
            for metrica in ['Accuracy', 'Precision', 'Recall', 'F1 Score']:
                valores = [float(m[metrica]) for m in metricas_data]
                fig_comp.add_trace(go.Bar(name=metrica, x=modelos_nombres, y=valores))
            
            fig_comp.update_layout(
                title="Comparativa de Métricas — Modelos de Clasificación",
                barmode='group',
                template="plotly_white",
                plot_bgcolor='#FFFFFF',
                paper_bgcolor='#FFFFFF',
                yaxis_title="Valor",
                height=400,
                font=dict(color='#333333')
            )
            st.plotly_chart(fig_comp, use_container_width=True)
            
            gc.collect()
    
    # ====================================================================
    # TAB 3: MODELOS DE REGRESIÓN
    # ====================================================================
    with tab_regresion:
        st.markdown("### Modelos de Regresión — Predicción de Precios")
        st.markdown(f"**Activo:** {empresas[ticker]} ({ticker}) | **Predicción:** Precio del día siguiente")
        
        if st.button("Ejecutar Todos los Modelos de Regresión", key="btn_reg"):
            resultados_reg = {}
            
            with st.spinner("Ejecutando Modelo 2.2.1: ARIMA..."):
                try:
                    precio_pred, tendencia, test, predictions, metricas, fechas_test = modelo_arima_regresion(datos_con_indicadores)
                    resultados_reg['ARIMA (2.2.1)'] = {
                        'precio': precio_pred, 'tendencia': tendencia,
                        'test': test, 'predictions': predictions, 
                        'metricas': metricas, 'fechas': fechas_test
                    }
                except Exception as e:
                    st.error(f"Error ARIMA: {e}")
            
            with st.spinner("Ejecutando Modelo 2.2.2: LSTM Regressor..."):
                try:
                    precio_pred, tendencia, test_real, pred_real, metricas = modelo_lstm_regressor(datos_con_indicadores)
                    resultados_reg['LSTM Regressor (2.2.2)'] = {
                        'precio': precio_pred, 'tendencia': tendencia,
                        'test': test_real, 'predictions': pred_real,
                        'metricas': metricas
                    }
                except Exception as e:
                    st.error(f"Error LSTM Regressor: {e}")
            
            # Ensamblaje ARIMA-LSTM
            if 'ARIMA (2.2.1)' in resultados_reg and 'LSTM Regressor (2.2.2)' in resultados_reg:
                precio_ens, tendencia_ens = modelo_arima_lstm_ensamblaje(
                    resultados_reg['ARIMA (2.2.1)']['precio'],
                    resultados_reg['LSTM Regressor (2.2.2)']['precio'],
                    precio_actual
                )
                resultados_reg['ARIMA-LSTM Ensamblaje (2.2.3)'] = {
                    'precio': precio_ens, 'tendencia': tendencia_ens,
                    'metricas': {
                        'rmse': (resultados_reg['ARIMA (2.2.1)']['metricas']['rmse'] + resultados_reg['LSTM Regressor (2.2.2)']['metricas']['rmse']) / 2,
                        'mae': (resultados_reg['ARIMA (2.2.1)']['metricas']['mae'] + resultados_reg['LSTM Regressor (2.2.2)']['metricas']['mae']) / 2
                    }
                }
            
            if resultados_reg:
                st.session_state['resultados_reg'] = resultados_reg
                st.success("Todos los modelos de regresión ejecutados correctamente.")
        
        # Mostrar resultados
        if 'resultados_reg' in st.session_state:
            resultados_reg = st.session_state['resultados_reg']
            
            st.markdown("#### Predicciones de Precio para el Próximo Día")
            reg_data = []
            for nombre, res in resultados_reg.items():
                diferencia = res['precio'] - precio_actual
                reg_data.append({
                    'Modelo': nombre,
                    'Precio Predicho': f"${res['precio']:.2f}",
                    'Precio Actual': f"${precio_actual:.2f}",
                    'Diferencia': f"${diferencia:+.2f}",
                    'Tendencia': res['tendencia'],
                    'Recomendación': 'COMPRAR' if res['tendencia'] == 'SUBIDA' else 'VENDER'
                })
            
            df_reg = pd.DataFrame(reg_data)
            st.dataframe(df_reg, use_container_width=True, hide_index=True)
            
            # Métricas de error
            st.markdown("#### Métricas de Error de Regresión")
            err_data = []
            for nombre, res in resultados_reg.items():
                m = res['metricas']
                err_data.append({
                    'Modelo': nombre,
                    'RMSE': f"${m['rmse']:.4f}",
                    'MAE': f"${m['mae']:.4f}"
                })
            
            df_err = pd.DataFrame(err_data)
            st.dataframe(df_err, use_container_width=True, hide_index=True)
            
            # Gráficos de Real vs Predicho
            import plotly.graph_objects as go
            
            for nombre, res in resultados_reg.items():
                if 'test' in res and res['test'] is not None:
                    fig_reg = go.Figure()
                    
                    min_len = min(len(res['test']), len(res['predictions']))
                    fig_reg.add_trace(go.Scatter(
                        y=res['test'][:min_len], mode='lines',
                        name='Precio Real', line=dict(color='#0F52BA', width=2)
                    ))
                    fig_reg.add_trace(go.Scatter(
                        y=res['predictions'][:min_len], mode='lines',
                        name='Precio Predicho', line=dict(color='#DC3545', width=2, dash='dash')
                    ))
                    
                    fig_reg.update_layout(
                        title=f"Real vs Predicho — {nombre}",
                        yaxis_title="Precio (USD)",
                        xaxis_title="Observaciones (Test Set)",
                        template="plotly_white",
                        plot_bgcolor='#FFFFFF',
                        paper_bgcolor='#FFFFFF',
                        height=350,
                        font=dict(color='#333333')
                    )
                    st.plotly_chart(fig_reg, use_container_width=True)
            
            gc.collect()
    
    # ====================================================================
    # TAB 4: BACKTESTING
    # ====================================================================
    with tab_backtesting:
        st.markdown("### Backtesting de Estrategias")
        st.markdown(f"**Activo:** {empresas[ticker]} ({ticker}) | **Capital Inicial:** $10,000.00 USD | **Comisión:** 0.1%")
        
        if st.button("Ejecutar Backtesting de Todos los Modelos", key="btn_bt"):
            resultados_bt = {}
            
            # Necesitamos ejecutar los modelos de clasificación primero para obtener señales
            with st.spinner("Generando señales de los modelos y ejecutando backtesting..."):
                try:
                    # SVC
                    _, _, y_test_svc, y_pred_svc, _, _ = modelo_svc_prediccion(datos_con_indicadores)
                    resultados_bt['SVC (2.1.1)'] = ejecutar_backtesting(datos_con_indicadores, y_pred_svc, 'SVC (2.1.1)')
                except Exception as e:
                    st.warning(f"SVC Backtesting falló: {e}")
                
                try:
                    _, _, y_test_rnn, y_pred_rnn, _ = modelo_rnn_simple_prediccion(datos_con_indicadores)
                    resultados_bt['SimpleRNN (2.1.2)'] = ejecutar_backtesting(datos_con_indicadores, y_pred_rnn, 'SimpleRNN (2.1.2)')
                except Exception as e:
                    st.warning(f"SimpleRNN Backtesting falló: {e}")
                
                try:
                    _, _, y_test_lstm, y_pred_lstm, _ = modelo_lstm_classifier(datos_con_indicadores)
                    resultados_bt['LSTM Classifier (2.1.3)'] = ejecutar_backtesting(datos_con_indicadores, y_pred_lstm, 'LSTM Classifier (2.1.3)')
                except Exception as e:
                    st.warning(f"LSTM Backtesting falló: {e}")
                
                try:
                    _, _, y_test_bi, y_pred_bi, _ = modelo_bilstm_classifier(datos_con_indicadores)
                    resultados_bt['BiLSTM (2.1.4)'] = ejecutar_backtesting(datos_con_indicadores, y_pred_bi, 'BiLSTM (2.1.4)')
                except Exception as e:
                    st.warning(f"BiLSTM Backtesting falló: {e}")
                
                try:
                    _, _, y_test_gru, y_pred_gru, _ = modelo_gru_classifier(datos_con_indicadores)
                    resultados_bt['GRU (2.1.5)'] = ejecutar_backtesting(datos_con_indicadores, y_pred_gru, 'GRU (2.1.5)')
                except Exception as e:
                    st.warning(f"GRU Backtesting falló: {e}")
            
            if resultados_bt:
                st.session_state['resultados_bt'] = resultados_bt
                st.success("Backtesting completado para todos los modelos.")
        
        if 'resultados_bt' in st.session_state:
            resultados_bt = st.session_state['resultados_bt']
            
            # Tabla comparativa de estrategias
            st.markdown("#### Comparativa de Estrategias")
            bt_data = []
            for nombre, res in resultados_bt.items():
                bt_data.append({
                    'Modelo / Estrategia': res['modelo'],
                    'Capital Final': f"${res['capital_final']:,.2f}",
                    'Retorno Total': f"{res['retorno_total']:+.2f}%",
                    'Buy & Hold': f"{res['retorno_buyhold']:+.2f}%",
                    'Sharpe Ratio': f"{res['sharpe_ratio']:.4f}",
                    'Max Drawdown': f"{res['max_drawdown']:.2f}%",
                    'Total Trades': res['total_trades'],
                    'Win Rate': f"{res['win_rate']:.1f}%"
                })
            
            df_bt = pd.DataFrame(bt_data)
            st.dataframe(df_bt, use_container_width=True, hide_index=True)
            
            # Mejor modelo
            mejor = max(resultados_bt.values(), key=lambda x: x['retorno_total'])
            st.success(f"**Mejor Estrategia:** {mejor['modelo']} con retorno de {mejor['retorno_total']:+.2f}%")
            
            # Gráfico de evolución de capital
            import plotly.graph_objects as go
            
            fig_bt = go.Figure()
            colors = ['#0F52BA', '#28A745', '#DC3545', '#FF8C00', '#6F42C1']
            for i, (nombre, res) in enumerate(resultados_bt.items()):
                fig_bt.add_trace(go.Scatter(
                    y=res['historial'], mode='lines',
                    name=nombre,
                    line=dict(color=colors[i % len(colors)], width=2)
                ))
            
            # Línea de capital inicial
            max_len = max(len(res['historial']) for res in resultados_bt.values())
            fig_bt.add_hline(y=10000, line_dash="dash", line_color="gray", annotation_text="Capital Inicial ($10,000)")
            
            fig_bt.update_layout(
                title="Evolución del Capital — Comparativa de Estrategias",
                yaxis_title="Capital (USD)",
                xaxis_title="Número de Operaciones",
                template="plotly_white",
                plot_bgcolor='#FFFFFF',
                paper_bgcolor='#FFFFFF',
                height=450,
                font=dict(color='#333333')
            )
            st.plotly_chart(fig_bt, use_container_width=True)
            
            # Gráfico de barras: Retorno por modelo
            fig_ret = go.Figure()
            nombres = [r['modelo'] for r in resultados_bt.values()]
            retornos = [r['retorno_total'] for r in resultados_bt.values()]
            colores_ret = ['#28A745' if r > 0 else '#DC3545' for r in retornos]
            
            fig_ret.add_trace(go.Bar(
                x=nombres, y=retornos,
                marker_color=colores_ret,
                text=[f"{r:+.2f}%" for r in retornos],
                textposition='auto'
            ))
            
            fig_ret.update_layout(
                title="Retorno Total por Estrategia",
                yaxis_title="Retorno (%)",
                template="plotly_white",
                plot_bgcolor='#FFFFFF',
                paper_bgcolor='#FFFFFF',
                height=350,
                font=dict(color='#333333')
            )
            st.plotly_chart(fig_ret, use_container_width=True)
            
            gc.collect()
    
    # ====================================================================
    # TAB 5: PORTAFOLIOS
    # ====================================================================
    with tab_portafolio:
        st.markdown("### Gestión de Portafolios")
        
        if id_usuario:
            # Obtener portafolio del usuario
            portafolio_df = ejecutar_query("""
                SELECT P.id_portafolio, P.nombre_portafolio, P.fecha_creacion
                FROM Portafolio P
                WHERE P.id_usuario = ?
            """, (id_usuario,))
            
            if not portafolio_df.empty:
                id_portafolio = int(portafolio_df['id_portafolio'].iloc[0])
                st.markdown(f"**Portafolio:** {portafolio_df['nombre_portafolio'].iloc[0]} | **Creado:** {portafolio_df['fecha_creacion'].iloc[0]}")
                
                # Activos en portafolio
                activos_port = ejecutar_query("""
                    SELECT A.ticker, A.nombre_empresa, PA.cantidad, PA.precio_compra_promedio,
                           (PA.cantidad * PA.precio_compra_promedio) as valor_compra
                    FROM Portafolio_Activo PA
                    JOIN Activo A ON PA.id_activo = A.id_activo
                    WHERE PA.id_portafolio = ?
                """, (id_portafolio,))
                
                if not activos_port.empty:
                    st.markdown("#### Composición del Portafolio")
                    
                    # Obtener precios actuales
                    activos_port['precio_actual'] = 0.0
                    activos_port['valor_actual'] = 0.0
                    activos_port['ganancia_perdida'] = 0.0
                    activos_port['rendimiento_pct'] = 0.0
                    
                    for idx, row in activos_port.iterrows():
                        try:
                            tk = row['ticker']
                            datos_tk = yf.download(tk, period="1d", progress=False)
                            if not datos_tk.empty:
                                if isinstance(datos_tk.columns, pd.MultiIndex):
                                    precio = float(datos_tk['Close'].iloc[-1].values[0])
                                else:
                                    precio = float(datos_tk['Close'].iloc[-1])
                                activos_port.at[idx, 'precio_actual'] = precio
                                activos_port.at[idx, 'valor_actual'] = row['cantidad'] * precio
                                activos_port.at[idx, 'ganancia_perdida'] = (precio - row['precio_compra_promedio']) * row['cantidad']
                                activos_port.at[idx, 'rendimiento_pct'] = ((precio - row['precio_compra_promedio']) / row['precio_compra_promedio']) * 100
                        except Exception:
                            pass
                    
                    st.dataframe(activos_port.rename(columns={
                        'ticker': 'Ticker', 'nombre_empresa': 'Empresa',
                        'cantidad': 'Cantidad', 'precio_compra_promedio': 'Precio Compra Prom.',
                        'valor_compra': 'Valor Compra', 'precio_actual': 'Precio Actual',
                        'valor_actual': 'Valor Actual', 'ganancia_perdida': 'G/P (USD)',
                        'rendimiento_pct': 'Rendimiento (%)'
                    }).style.format({
                        'Precio Compra Prom.': '${:.2f}', 'Valor Compra': '${:.2f}',
                        'Precio Actual': '${:.2f}', 'Valor Actual': '${:.2f}',
                        'G/P (USD)': '${:+.2f}', 'Rendimiento (%)': '{:+.2f}%',
                        'Cantidad': '{:.0f}'
                    }), use_container_width=True, hide_index=True)
                    
                    # Resumen
                    total_invertido = activos_port['valor_compra'].sum()
                    total_actual = activos_port['valor_actual'].sum()
                    ganancia_total = total_actual - total_invertido
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total Invertido", f"${total_invertido:,.2f}")
                    c2.metric("Valor Actual", f"${total_actual:,.2f}")
                    c3.metric("Ganancia/Pérdida", f"${ganancia_total:+,.2f}", f"{(ganancia_total/total_invertido)*100:+.2f}%")
                    
                    # Gráfico circular de composición
                    import plotly.graph_objects as go
                    
                    if total_actual > 0:
                        fig_pie = go.Figure(data=[go.Pie(
                            labels=activos_port['ticker'],
                            values=activos_port['valor_actual'],
                            hole=0.3,
                            marker_colors=['#0F52BA', '#28A745', '#DC3545', '#FF8C00', '#6F42C1', '#17A2B8']
                        )])
                        fig_pie.update_layout(
                            title="Distribución del Portafolio",
                            template="plotly_white",
                            plot_bgcolor='#FFFFFF',
                            paper_bgcolor='#FFFFFF',
                            height=350,
                            font=dict(color='#333333')
                        )
                        st.plotly_chart(fig_pie, use_container_width=True)
                
                # Agregar activo al portafolio
                st.markdown("---")
                st.markdown("#### Agregar Activo al Portafolio")
                with st.form("form_agregar_activo"):
                    activos_disponibles = ejecutar_query("SELECT id_activo, ticker, nombre_empresa FROM Activo")
                    activo_sel = st.selectbox("Activo:", activos_disponibles['ticker'].tolist())
                    cantidad_nueva = st.number_input("Cantidad:", min_value=1.0, value=10.0, step=1.0)
                    precio_compra = st.number_input("Precio de Compra Promedio:", min_value=0.01, value=1.0, step=0.01)
                    
                    if st.form_submit_button("Agregar Activo"):
                        id_activo_sel = int(activos_disponibles[activos_disponibles['ticker'] == activo_sel]['id_activo'].values[0])
                        try:
                            # Verificar si ya existe
                            existente = ejecutar_query(
                                "SELECT cantidad, precio_compra_promedio FROM Portafolio_Activo WHERE id_portafolio = ? AND id_activo = ?",
                                (id_portafolio, id_activo_sel)
                            )
                            if not existente.empty:
                                # Actualizar
                                cant_anterior = float(existente['cantidad'].values[0])
                                precio_anterior = float(existente['precio_compra_promedio'].values[0])
                                nueva_cant = cant_anterior + cantidad_nueva
                                nuevo_precio = (cant_anterior * precio_anterior + cantidad_nueva * precio_compra) / nueva_cant
                                conn = get_db_connection()
                                conn.execute(
                                    "UPDATE Portafolio_Activo SET cantidad = ?, precio_compra_promedio = ? WHERE id_portafolio = ? AND id_activo = ?",
                                    (nueva_cant, nuevo_precio, id_portafolio, id_activo_sel)
                                )
                                conn.commit()
                                conn.close()
                            else:
                                ejecutar_insert(
                                    "INSERT INTO Portafolio_Activo (id_portafolio, id_activo, cantidad, precio_compra_promedio) VALUES (?, ?, ?, ?)",
                                    (id_portafolio, id_activo_sel, cantidad_nueva, precio_compra)
                                )
                            st.success(f"Activo {activo_sel} agregado/actualizado en el portafolio.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al agregar activo: {e}")
            else:
                st.info("Este usuario no tiene portafolio asignado.")
        else:
            st.warning("Seleccione un usuario desde el panel lateral.")
    
    # ====================================================================
    # TAB 6: OPERACIONES
    # ====================================================================
    with tab_operaciones:
        st.markdown("### Registro de Operaciones")
        
        if id_usuario:
            portafolio_df = ejecutar_query("SELECT id_portafolio FROM Portafolio WHERE id_usuario = ?", (id_usuario,))
            
            if not portafolio_df.empty:
                id_portafolio = int(portafolio_df['id_portafolio'].iloc[0])
                
                # Formulario para nueva operación
                st.markdown("#### Registrar Nueva Operación")
                with st.form("form_nueva_operacion"):
                    col_op1, col_op2 = st.columns(2)
                    with col_op1:
                        activos_disp = ejecutar_query("SELECT id_activo, ticker, nombre_empresa FROM Activo")
                        activo_op = st.selectbox("Activo:", activos_disp.apply(lambda r: f"{r['ticker']} - {r['nombre_empresa']}", axis=1).tolist(), key="op_activo")
                        tipo_op = st.selectbox("Tipo de Operación:", ["COMPRA", "VENTA", "RECOMPRA", "SHORT"])
                    with col_op2:
                        cantidad_op = st.number_input("Cantidad:", min_value=1.0, value=10.0, step=1.0, key="op_cantidad")
                        precio_op = st.number_input("Precio Unitario:", min_value=0.01, value=1.0, step=0.01, key="op_precio")
                    
                    if st.form_submit_button("Registrar Operación"):
                        ticker_op = activo_op.split(" - ")[0]
                        id_activo_op = int(activos_disp[activos_disp['ticker'] == ticker_op]['id_activo'].values[0])
                        try:
                            ejecutar_insert(
                                "INSERT INTO Operacion (id_portafolio, id_activo, tipo_operacion, cantidad, precio_unitario) VALUES (?, ?, ?, ?, ?)",
                                (id_portafolio, id_activo_op, tipo_op, cantidad_op, precio_op)
                            )
                            
                            # Actualizar Portafolio_Activo
                            existente = ejecutar_query(
                                "SELECT cantidad, precio_compra_promedio FROM Portafolio_Activo WHERE id_portafolio = ? AND id_activo = ?",
                                (id_portafolio, id_activo_op)
                            )
                            
                            conn = get_db_connection()
                            if tipo_op in ("COMPRA", "RECOMPRA"):
                                if not existente.empty:
                                    cant_ant = float(existente['cantidad'].values[0])
                                    prec_ant = float(existente['precio_compra_promedio'].values[0])
                                    nueva_cant = cant_ant + cantidad_op
                                    nuevo_prec = (cant_ant * prec_ant + cantidad_op * precio_op) / nueva_cant
                                    conn.execute(
                                        "UPDATE Portafolio_Activo SET cantidad = ?, precio_compra_promedio = ? WHERE id_portafolio = ? AND id_activo = ?",
                                        (nueva_cant, nuevo_prec, id_portafolio, id_activo_op)
                                    )
                                else:
                                    conn.execute(
                                        "INSERT INTO Portafolio_Activo (id_portafolio, id_activo, cantidad, precio_compra_promedio) VALUES (?, ?, ?, ?)",
                                        (id_portafolio, id_activo_op, cantidad_op, precio_op)
                                    )
                            elif tipo_op == "VENTA":
                                if not existente.empty:
                                    cant_ant = float(existente['cantidad'].values[0])
                                    nueva_cant = cant_ant - cantidad_op
                                    if nueva_cant > 0:
                                        conn.execute(
                                            "UPDATE Portafolio_Activo SET cantidad = ? WHERE id_portafolio = ? AND id_activo = ?",
                                            (nueva_cant, id_portafolio, id_activo_op)
                                        )
                                    else:
                                        conn.execute(
                                            "DELETE FROM Portafolio_Activo WHERE id_portafolio = ? AND id_activo = ?",
                                            (id_portafolio, id_activo_op)
                                        )
                            conn.commit()
                            conn.close()
                            
                            st.success(f"Operación {tipo_op} de {cantidad_op} unidades de {ticker_op} registrada exitosamente.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error al registrar operación: {e}")
                
                # Historial de operaciones
                st.markdown("---")
                st.markdown("#### Historial de Operaciones")
                
                operaciones_df = ejecutar_query("""
                    SELECT O.id_operacion, A.ticker, A.nombre_empresa, O.tipo_operacion,
                           O.cantidad, O.precio_unitario, (O.cantidad * O.precio_unitario) as monto_total,
                           O.fecha_operacion
                    FROM Operacion O
                    JOIN Activo A ON O.id_activo = A.id_activo
                    WHERE O.id_portafolio = ?
                    ORDER BY O.fecha_operacion DESC
                """, (id_portafolio,))
                
                if not operaciones_df.empty:
                    st.dataframe(operaciones_df.rename(columns={
                        'id_operacion': 'ID', 'ticker': 'Ticker', 'nombre_empresa': 'Empresa',
                        'tipo_operacion': 'Tipo', 'cantidad': 'Cantidad',
                        'precio_unitario': 'Precio Unit.', 'monto_total': 'Monto Total',
                        'fecha_operacion': 'Fecha'
                    }).style.format({
                        'Precio Unit.': '${:.2f}', 'Monto Total': '${:.2f}',
                        'Cantidad': '{:.0f}'
                    }), use_container_width=True, hide_index=True)
                    
                    # Resumen por tipo
                    st.markdown("#### Resumen por Tipo de Operación")
                    resumen_ops = operaciones_df.groupby('tipo_operacion').agg({
                        'cantidad': 'sum', 'monto_total': 'sum', 'id_operacion': 'count'
                    }).rename(columns={'id_operacion': 'Num. Operaciones', 'cantidad': 'Total Unidades', 'monto_total': 'Monto Total'})
                    st.dataframe(resumen_ops.style.format({
                        'Total Unidades': '{:,.0f}', 'Monto Total': '${:,.2f}'
                    }), use_container_width=True)
                else:
                    st.info("No hay operaciones registradas para este portafolio.")
        else:
            st.warning("Seleccione un usuario desde el panel lateral.")
    
    # ====================================================================
    # TAB 7: BASE DE DATOS
    # ====================================================================
    with tab_bd:
        st.markdown("### Administración de Base de Datos")
        st.markdown("Gestión dinámica de la base de datos SQLite del sistema.")
        
        subtab_usuarios, subtab_activos, subtab_predicciones, subtab_consultas = st.tabs([
            "Usuarios", "Activos", "Predicciones", "Consultas SQL"
        ])
        
        with subtab_usuarios:
            st.markdown("#### Usuarios del Sistema")
            
            usuarios_all = ejecutar_query("SELECT * FROM Usuario")
            st.dataframe(usuarios_all, use_container_width=True, hide_index=True)
            
            st.markdown("#### Agregar Nuevo Usuario")
            with st.form("form_nuevo_usuario"):
                col_u1, col_u2, col_u3 = st.columns(3)
                with col_u1:
                    nombre_nuevo = st.text_input("Nombre completo:")
                with col_u2:
                    email_nuevo = st.text_input("Email:")
                with col_u3:
                    perfil_nuevo = st.selectbox("Perfil de Riesgo:", ["Conservador", "Moderado", "Agresivo"])
                
                crear_portafolio = st.checkbox("Crear portafolio automáticamente", value=True)
                nombre_portafolio = st.text_input("Nombre del Portafolio:", value="Mi Portafolio")
                
                if st.form_submit_button("Crear Usuario"):
                    if nombre_nuevo and email_nuevo:
                        try:
                            nuevo_id = ejecutar_insert(
                                "INSERT INTO Usuario (nombre, email, perfil_riesgo) VALUES (?, ?, ?)",
                                (nombre_nuevo, email_nuevo, perfil_nuevo)
                            )
                            if crear_portafolio and nuevo_id:
                                ejecutar_insert(
                                    "INSERT INTO Portafolio (id_usuario, nombre_portafolio) VALUES (?, ?)",
                                    (nuevo_id, nombre_portafolio)
                                )
                            st.success(f"Usuario '{nombre_nuevo}' creado exitosamente (ID: {nuevo_id}).")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
                    else:
                        st.warning("Complete todos los campos obligatorios.")
        
        with subtab_activos:
            st.markdown("#### Catálogo de Activos Financieros")
            
            activos_all = ejecutar_query("SELECT * FROM Activo")
            st.dataframe(activos_all, use_container_width=True, hide_index=True)
            
            st.markdown("#### Agregar Nuevo Activo")
            with st.form("form_nuevo_activo"):
                col_a1, col_a2 = st.columns(2)
                with col_a1:
                    ticker_nuevo = st.text_input("Ticker (Yahoo Finance):")
                with col_a2:
                    empresa_nueva = st.text_input("Nombre de la Empresa:")
                
                if st.form_submit_button("Agregar Activo"):
                    if ticker_nuevo:
                        try:
                            ejecutar_insert(
                                "INSERT INTO Activo (ticker, nombre_empresa) VALUES (?, ?)",
                                (ticker_nuevo.upper(), empresa_nueva)
                            )
                            st.success(f"Activo '{ticker_nuevo.upper()}' agregado exitosamente.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error: {e}")
        
        with subtab_predicciones:
            st.markdown("#### Historial de Predicciones")
            
            predicciones_all = ejecutar_query("""
                SELECT P.id_prediccion, A.ticker, A.nombre_empresa, P.fecha_generacion,
                       P.fecha_objetivo, P.precio_predicho, P.tendencia, P.modelo_usado
                FROM Prediccion P
                JOIN Activo A ON P.id_activo = A.id_activo
                ORDER BY P.fecha_generacion DESC
            """)
            
            if not predicciones_all.empty:
                st.dataframe(predicciones_all, use_container_width=True, hide_index=True)
            else:
                st.info("No hay predicciones registradas aún.")
            
            st.markdown("#### Guardar Predicción")
            with st.form("form_guardar_prediccion"):
                col_p1, col_p2 = st.columns(2)
                with col_p1:
                    activos_pred = ejecutar_query("SELECT id_activo, ticker FROM Activo")
                    activo_pred = st.selectbox("Activo:", activos_pred['ticker'].tolist())
                    precio_pred_input = st.number_input("Precio Predicho:", min_value=0.01, value=1.0, step=0.01)
                with col_p2:
                    fecha_obj = st.date_input("Fecha Objetivo:", value=datetime.date.today() + datetime.timedelta(days=1))
                    tendencia_pred = st.selectbox("Tendencia:", ["SUBIDA", "BAJADA"])
                    modelo_pred = st.text_input("Modelo Usado:", value="Manual")
                
                if st.form_submit_button("Guardar Predicción"):
                    id_activo_pred = int(activos_pred[activos_pred['ticker'] == activo_pred]['id_activo'].values[0])
                    try:
                        ejecutar_insert(
                            "INSERT INTO Prediccion (id_activo, fecha_objetivo, precio_predicho, tendencia, modelo_usado) VALUES (?, ?, ?, ?, ?)",
                            (id_activo_pred, str(fecha_obj), precio_pred_input, tendencia_pred, modelo_pred)
                        )
                        st.success("Predicción guardada exitosamente.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
        
        with subtab_consultas:
            st.markdown("#### Ejecutar Consultas SQL")
            st.warning("Solo se permiten consultas SELECT por seguridad.")
            
            query_ejemplo = st.selectbox("Consultas de ejemplo:", [
                "Seleccionar consulta...",
                "SELECT * FROM Usuario",
                "SELECT * FROM Activo",
                "SELECT * FROM Portafolio",
                "SELECT U.nombre, P.nombre_portafolio FROM Usuario U JOIN Portafolio P ON U.id_usuario = P.id_usuario",
                "SELECT A.ticker, COUNT(O.id_operacion) as total_ops FROM Activo A LEFT JOIN Operacion O ON A.id_activo = O.id_activo GROUP BY A.ticker",
                "SELECT A.ticker, PA.cantidad, PA.precio_compra_promedio FROM Portafolio_Activo PA JOIN Activo A ON PA.id_activo = A.id_activo",
                "SELECT * FROM Prediccion ORDER BY fecha_generacion DESC"
            ])
            
            query_custom = st.text_area("Escriba su consulta SQL:", value=query_ejemplo if query_ejemplo != "Seleccionar consulta..." else "")
            
            if st.button("Ejecutar Consulta", key="btn_sql"):
                if query_custom.strip():
                    if query_custom.strip().upper().startswith("SELECT"):
                        try:
                            resultado = ejecutar_query(query_custom)
                            st.markdown(f"**Resultados:** {len(resultado)} filas")
                            st.dataframe(resultado, use_container_width=True, hide_index=True)
                        except Exception as e:
                            st.error(f"Error en consulta: {e}")
                    else:
                        st.error("Solo se permiten consultas SELECT.")
                else:
                    st.warning("Escriba una consulta SQL.")

else:
    st.error("No se pudieron cargar los datos del mercado. Verifique su conexión a Internet o el ticker seleccionado.")
    st.info("Tickers disponibles: FSM, VOLCABC1.LM, BVN, ABX, BHP, SCCO")

# ============================================================================
# FOOTER
# ============================================================================
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666666; font-size: 0.85em;'>
    <p>Sistema de Predicción de Tendencias y Precios Bursátiles con IA — Versión Prototipo</p>
    <p>UNMSM — Facultad de Ingeniería de Sistemas e Informática — Inteligencia de Negocios 2025-I</p>
    <p>Docente: Mg. Ernesto David Cancho Rodríguez | Equipo 2</p>
</div>
""", unsafe_allow_html=True)


