import sqlite3
import os

# Nombre del archivo de la base de datos
db_filename = 'sistema_inversiones.db'

# Eliminar la base de datos si existe para empezar de cero (útil para pruebas)
if os.path.exists(db_filename):
    os.remove(db_filename)
    print(f"Base de datos anterior '{db_filename}' eliminada.")

# Conexión a la base de datos SQLite (la crea si no existe)
conn = sqlite3.connect(db_filename)
cursor = conn.cursor()
print(f"Conectado a la base de datos '{db_filename}'.")

# Habilitar el soporte de claves foráneas en SQLite
cursor.execute("PRAGMA foreign_keys = ON;")

# Script SQL completo
sql_script = """
-- ==================================================
-- 6.1 & 6.2 CREACIÓN DE TABLAS (Schema Definition)
-- ==================================================

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
    tipo_operacion TEXT NOT NULL CHECK(tipo_operacion IN ('COMPRA', 'VENTA')),
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
    modelo_usado TEXT,
    FOREIGN KEY (id_activo) REFERENCES Activo(id_activo) ON DELETE CASCADE
);


-- ==================================================
-- 6.3 DATOS DE MUESTRA (Seed Data)
-- ==================================================

-- 1. Insertar Activos
INSERT INTO Activo (ticker, nombre_empresa) VALUES
('FSM', 'Fortuna Silver Mines Inc.'),
('VOLCABC1', 'Volcan Compañía Minera S.A.A.'),
('BVN', 'Compañía de Minas Buenaventura S.A.A.'),
('ABX', 'Barrick Gold Corporation'),
('BHP', 'BHP Group Limited'),
('SCCO', 'Southern Copper Corporation');

-- 2. Insertar Usuarios y Portafolios
INSERT INTO Usuario (nombre, email, perfil_riesgo) VALUES ('Juan Pérez', 'juan@mail.com', 'Moderado');
INSERT INTO Portafolio (id_usuario, nombre_portafolio) VALUES (last_insert_rowid(), 'Fondo Retiro Juan');

INSERT INTO Usuario (nombre, email, perfil_riesgo) VALUES ('María García', 'maria@mail.com', 'Agresivo');
INSERT INTO Portafolio (id_usuario, nombre_portafolio) VALUES (last_insert_rowid(), 'Inversiones María');

INSERT INTO Usuario (nombre, email, perfil_riesgo) VALUES ('Carlos López', 'carlos@mail.com', 'Conservador');
INSERT INTO Portafolio (id_usuario, nombre_portafolio) VALUES (last_insert_rowid(), 'Ahorro Seguro');

INSERT INTO Usuario (nombre, email, perfil_riesgo) VALUES ('Ana Torres', 'ana@mail.com', 'Moderado');
INSERT INTO Portafolio (id_usuario, nombre_portafolio) VALUES (last_insert_rowid(), 'Portafolio Crecimiento');

INSERT INTO Usuario (nombre, email, perfil_riesgo) VALUES ('Luis Ruiz', 'luis@mail.com', 'Agresivo');
INSERT INTO Portafolio (id_usuario, nombre_portafolio) VALUES (last_insert_rowid(), 'Trading Activo');

INSERT INTO Usuario (nombre, email, perfil_riesgo) VALUES ('Elena Díaz', 'elena@mail.com', 'Conservador');
INSERT INTO Portafolio (id_usuario, nombre_portafolio) VALUES (last_insert_rowid(), 'Fondo Universitario');


-- 3. Insertar Portafolio_Activo (Tenencias actuales)
INSERT INTO Portafolio_Activo (id_portafolio, id_activo, cantidad, precio_compra_promedio) VALUES
(1, 1, 100, 3.50), (1, 3, 50, 8.20),
(2, 2, 5000, 0.50), (2, 4, 75, 16.50), (2, 6, 30, 45.00),
(3, 5, 40, 55.00), (3, 6, 20, 42.00),
(4, 1, 150, 3.60), (4, 3, 25, 8.00), (4, 4, 20, 17.00),
(5, 1, 50, 3.55), (5, 2, 1000, 0.45), (5, 3, 30, 8.10), (5, 4, 40, 16.20), (5, 5, 10, 54.00), (5, 6, 15, 44.00),
(6, 5, 30, 56.00), (6, 3, 60, 7.90);


-- 4. Insertar Operaciones (Mínimo 6 por activo para cumplir el requisito estricto)

-- Operaciones para FSM (id_activo = 1)
INSERT INTO Operacion (id_portafolio, id_activo, tipo_operacion, cantidad, precio_unitario) VALUES
(1, 1, 'COMPRA', 50, 3.40), (1, 1, 'COMPRA', 50, 3.60),
(4, 1, 'COMPRA', 200, 3.50), (4, 1, 'VENTA', 50, 3.80),
(5, 1, 'COMPRA', 100, 3.55), (5, 1, 'VENTA', 50, 3.70);

-- Operaciones para VOLCABC1 (id_activo = 2)
INSERT INTO Operacion (id_portafolio, id_activo, tipo_operacion, cantidad, precio_unitario) VALUES
(2, 2, 'COMPRA', 3000, 0.48), (2, 2, 'COMPRA', 3000, 0.52), (2, 2, 'VENTA', 1000, 0.55),
(5, 2, 'COMPRA', 500, 0.44), (5, 2, 'COMPRA', 1000, 0.46), (5, 2, 'VENTA', 500, 0.50);

-- Operaciones para BVN (id_activo = 3)
INSERT INTO Operacion (id_portafolio, id_activo, tipo_operacion, cantidad, precio_unitario) VALUES
(1, 3, 'COMPRA', 50, 8.20), (1, 3, 'COMPRA', 20, 8.00), (1, 3, 'VENTA', 20, 8.50),
(4, 3, 'COMPRA', 25, 8.00),
(5, 3, 'COMPRA', 30, 8.10),
(6, 3, 'COMPRA', 60, 7.90);

-- Operaciones para ABX (id_activo = 4)
INSERT INTO Operacion (id_portafolio, id_activo, tipo_operacion, cantidad, precio_unitario) VALUES
(2, 4, 'COMPRA', 50, 16.00), (2, 4, 'COMPRA', 25, 17.00),
(4, 4, 'COMPRA', 40, 16.50), (4, 4, 'VENTA', 20, 17.50),
(5, 4, 'COMPRA', 40, 16.20), (5, 4, 'COMPRA', 20, 16.00), (5, 4, 'VENTA', 20, 16.80);

-- Operaciones para BHP (id_activo = 5)
INSERT INTO Operacion (id_portafolio, id_activo, tipo_operacion, cantidad, precio_unitario) VALUES
(3, 5, 'COMPRA', 20, 54.00), (3, 5, 'COMPRA', 20, 56.00),
(5, 5, 'COMPRA', 10, 54.00),
(6, 5, 'COMPRA', 40, 55.00), (6, 5, 'VENTA', 10, 57.00), (6, 5, 'COMPRA', 10, 56.50);

-- Operaciones para SCCO (id_activo = 6)
INSERT INTO Operacion (id_portafolio, id_activo, tipo_operacion, cantidad, precio_unitario) VALUES
(2, 6, 'COMPRA', 30, 45.00),
(3, 6, 'COMPRA', 20, 42.00),
(5, 6, 'COMPRA', 25, 43.00), (5, 6, 'VENTA', 10, 46.00),
(2, 6, 'COMPRA', 10, 44.00), (2, 6, 'VENTA', 10, 47.00);


-- 5. Insertar Predicciones
INSERT INTO Prediccion (id_activo, fecha_objetivo, precio_predicho, modelo_usado) VALUES
(1, '2026-12-31', 4.50, 'SVC Modelo 2.1.1'),
(3, '2026-12-31', 9.00, 'LSTM Classifier Modelo 2.1.3'),
(6, '2026-06-30', 50.00, 'ARIMA Modelo 2.2.1');
"""

# Ejecutar el script y validar
try:
    cursor.executescript(sql_script)
    conn.commit()
    print("\n✅ ¡Tablas creadas y datos de muestra insertados correctamente!")

    # --- Verificación estricta de la rúbrica ---
    print("\n--- Verificación de Requisitos del Entregable ---")
    
    cursor.execute("SELECT COUNT(*) FROM Usuario")
    print(f"Usuarios creados: {cursor.fetchone()[0]} (Requerido: al menos 6)")

    cursor.execute("SELECT COUNT(*) FROM Activo")
    print(f"Empresas de testeo: {cursor.fetchone()[0]} (Requerido: FSM, VOLCABC1, BVN, ABX, BHP, SCCO)")

    print("\n--- Validación de 'Al menos 6 operaciones por activo' ---")
    cursor.execute("""
        SELECT A.ticker, COUNT(O.id_operacion) 
        FROM Activo A 
        LEFT JOIN Operacion O ON A.id_activo = O.id_activo 
        GROUP BY A.ticker
    """)
    resultados_operaciones = cursor.fetchall()
    for ticker, conteo in resultados_operaciones:
        estado = "✅ Cumple" if conteo >= 6 else "❌ No cumple"
        print(f"Activo {ticker}: {conteo} operaciones históricas -> {estado}")

except sqlite3.Error as e:
    print(f"\n❌ Error al ejecutar el script SQL: {e}")
    conn.rollback()

finally:
    conn.close()
    print("\nConexión a la base de datos cerrada.")