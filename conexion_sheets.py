from decimal import Decimal, InvalidOperation
from pathlib import Path
import threading
import unicodedata

import gspread
import pandas as pd

# ID de la hoja de Google Sheets (¡Este es el ID correcto de tu navegador!)
SPREADSHEET_ID = '1beuJk14LuFMRLU3yOCdeYLjaWf_jhaIbePCFUTbW6NE'
RUTA_CREDENCIALES = Path(__file__).resolve().parent / 'credenciales.json'
_approval_lock = threading.Lock()


class ErrorRegistro(ValueError):
    """Error de validación de registro con estado HTTP seguro para la API."""

    def __init__(self, mensaje, status_code=400):
        super().__init__(mensaje)
        self.status_code = status_code


def _normalizar_encabezado(valor):
    texto = ' '.join(str(valor).strip().upper().split())
    return ''.join(
        caracter for caracter in unicodedata.normalize('NFD', texto)
        if unicodedata.category(caracter) != 'Mn'
    )


def _encontrar_columna(encabezados, *terminos):
    terminos = tuple(_normalizar_encabezado(termino) for termino in terminos)
    for indice, encabezado in enumerate(encabezados):
        normalizado = _normalizar_encabezado(encabezado)
        if all(termino in normalizado for termino in terminos):
            return indice
    return None


def _fila_por_codigo(filas, columna_codigo, codigo):
    coincidencias = [
        (numero_fila, fila)
        for numero_fila, fila in enumerate(filas[1:], start=2)
        if len(fila) > columna_codigo and str(fila[columna_codigo]).strip() == codigo
    ]
    if not coincidencias:
        raise ErrorRegistro('No se encontró el registro solicitado.', 404)
    if len(coincidencias) != 1:
        raise ErrorRegistro('El código no es único en Google Sheets.', 409)
    return coincidencias[0]


def _valor_fila(fila, indice):
    return str(fila[indice]).strip() if indice is not None and indice < len(fila) else ''


def _estado_notificado(valor):
    return _normalizar_encabezado(valor) in {'SI', 'S', 'YES', 'TRUE', 'NOTIFICADO'}


def actualizar_estado_registro(codigo, nuevo_estado, limite):
    """Actualiza un registro pendiente por código, tocando solo su celda de estado.

    Las transiciones permitidas son APROBADO y DESCARTADO. La regla de monto y
    CONTROL DE LEY bloquea aprobaciones; un rechazo sigue disponible para
    registros pendientes que incumplan esos criterios.
    """
    codigo = str(codigo or '').strip()
    if not codigo:
        raise ErrorRegistro('El código del registro es obligatorio.')
    nuevo_estado = _normalizar_encabezado(nuevo_estado)
    if nuevo_estado not in {'APROBADO', 'DESCARTADO'}:
        raise ErrorRegistro('La acción solicitada no está permitida.')

    with _approval_lock:
        hoja = conectar()
        valores = hoja.get_all_values()
        if not valores:
            raise ErrorRegistro('La hoja de Google Sheets está vacía.', 404)

        encabezados = valores[0]
        columna_codigo = _encontrar_columna(encabezados, 'CODIGO')
        columna_estado = _encontrar_columna(encabezados, 'ESTADO', 'VALIDACION')
        if columna_estado is None:
            columna_estado = _encontrar_columna(encabezados, 'COLUMNA 1')
        columna_control = _encontrar_columna(encabezados, 'CONTROL', 'LEY')
        columna_monto = _encontrar_columna(encabezados, 'MONTO')
        columna_nombre = _encontrar_columna(encabezados, 'NOMBRE')
        columna_correo = _encontrar_columna(encabezados, 'CORREO')
        columna_notificado = _encontrar_columna(encabezados, 'NOTIFICADO')

        if columna_codigo is None or columna_estado is None:
            raise ErrorRegistro('La hoja no contiene las columnas de código y estado.', 500)
        if columna_control is None or columna_monto is None:
            raise ErrorRegistro('No se puede validar el control legal del registro.', 422)

        numero_fila, fila = _fila_por_codigo(valores, columna_codigo, codigo)
        estado = _normalizar_encabezado(_valor_fila(fila, columna_estado))
        if estado != 'PENDIENTE':
            raise ErrorRegistro(
                'Solo se pueden modificar registros que continúan pendientes.', 409
            )

        try:
            monto = Decimal(_valor_fila(fila, columna_monto).replace(',', '.'))
            limite_decimal = Decimal(str(limite))
        except (InvalidOperation, ValueError):
            raise ErrorRegistro('El monto del registro no es válido.', 422) from None
        if not monto.is_finite() or not limite_decimal.is_finite():
            raise ErrorRegistro('El monto del registro no es válido.', 422)
        control = _normalizar_encabezado(_valor_fila(fila, columna_control))
        contradice_control = (
            'DENTRO' not in control
            or 'EXCEDE' in control
            or 'SUPERA' in control
        )
        if nuevo_estado == 'APROBADO':
            if monto <= 0:
                raise ErrorRegistro('El monto debe ser mayor que cero.', 422)
            if monto > limite_decimal:
                raise ErrorRegistro(
                    'El monto excede el límite vigente y no puede aprobarse.', 422
                )
            if contradice_control:
                raise ErrorRegistro(
                    'El CONTROL DE LEY no permite aprobar este registro.', 422
                )

        # Solo se actualiza la celda de estado: se conservan fórmulas y formatos.
        # update_cell retorna solo tras una respuesta exitosa de la API de Sheets.
        hoja.update_cell(numero_fila, columna_estado + 1, nuevo_estado)
        return {
            'codigo': codigo,
            'nombre': _valor_fila(fila, columna_nombre),
            'monto': str(monto),
            'correo': _valor_fila(fila, columna_correo),
            'notificado': _valor_fila(fila, columna_notificado),
            'tiene_columna_notificado': columna_notificado is not None,
            'estado': nuevo_estado,
        }


def aprobar_registro(codigo, limite):
    """Compatibilidad para callers existentes; aplica las mismas reglas."""
    return actualizar_estado_registro(codigo, 'APROBADO', limite)


def marcar_registro_notificado(codigo):
    """Marca SÍ solo después de que el transporte confirme el envío."""
    codigo = str(codigo or '').strip()
    with _approval_lock:
        hoja = conectar()
        valores = hoja.get_all_values()
        if not valores:
            raise ErrorRegistro('La hoja de Google Sheets está vacía.', 404)
        encabezados = valores[0]
        columna_codigo = _encontrar_columna(encabezados, 'CODIGO')
        columna_estado = _encontrar_columna(encabezados, 'ESTADO', 'VALIDACION')
        columna_notificado = _encontrar_columna(encabezados, 'NOTIFICADO')
        if columna_codigo is None or columna_estado is None or columna_notificado is None:
            raise ErrorRegistro('Falta una columna necesaria para registrar la notificación.', 500)

        numero_fila, fila = _fila_por_codigo(valores, columna_codigo, codigo)
        if _normalizar_encabezado(_valor_fila(fila, columna_estado)) not in {
            'APROBADO', 'DESCARTADO'
        }:
            raise ErrorRegistro('El registro ya no tiene un estado final.', 409)
        if _estado_notificado(_valor_fila(fila, columna_notificado)):
            return False

        hoja.update_cell(numero_fila, columna_notificado + 1, 'SÍ')
        return True


def conectar():
    """Abre la primera pestaña de la hoja usando la cuenta de servicio."""
    cliente = gspread.service_account(filename=str(RUTA_CREDENCIALES))
    archivo = cliente.open_by_key(SPREADSHEET_ID)
    return archivo.sheet1


def _leer_valores():
    """Lee las filas de la pestaña, incluido el encabezado."""
    return conectar().get_all_values()


def leer_todos():
    """Devuelve las filas de gastos sin incluir el encabezado."""
    valores = _leer_valores()
    return valores[1:] if valores else []


def agregar_gasto(fecha, correo, nombre, dni, area, motivo, monto, codigo,
                  control_ley, estado, notificado):
    """Valida y agrega un gasto al final de la hoja; propaga errores de Sheets."""
    campos = [
        fecha, correo, nombre, dni, area, motivo, monto, codigo,
        control_ley, estado, notificado,
    ]
    if any(valor is None or not str(valor).strip() for valor in campos):
        raise ValueError('Todos los campos del gasto son obligatorios.')

    try:
        monto_decimal = Decimal(str(monto).strip().replace(',', '.'))
    except InvalidOperation as error:
        raise ValueError('El monto debe ser un número válido.') from error
    if not monto_decimal.is_finite() or monto_decimal < 0:
        raise ValueError('El monto debe ser un número finito y no negativo.')

    fila = [str(valor).strip() for valor in campos]
    fila[6] = float(monto_decimal)

    hoja = conectar()
    encabezados = hoja.row_values(1)
    if len(encabezados) != len(fila):
        raise ValueError(
            f'La hoja tiene {len(encabezados)} columnas; se esperaban {len(fila)}.'
        )

    resultado = hoja.append_row(fila, value_input_option='USER_ENTERED')
    print(f"Gasto {fila[7]} registrado")
    return resultado


def obtener_datos():
    """
    Se conecta a Google Sheets usando credenciales.json 
    y retorna los datos de la primera hoja como un DataFrame de Pandas.
    """
    try:
        valores = _leer_valores()
        
        if not valores:
            return None
            
        # Construimos el DataFrame con los valores
        encabezados = valores[0]
        df = pd.DataFrame(valores[1:], columns=encabezados)
        
        # LIMPIEZA 1: Si existe la columna de fecha
        if 'FECHA Y HORA' in df.columns:
             df['FECHA Y HORA'] = df['FECHA Y HORA'].astype(str).str.replace("'", "", regex=False)

        # LIMPIEZA 2: Convertir la columna de Monto respetando los decimales reales
        for col in df.columns:
            if 'MONTO' in str(col).upper():
                # Reemplaza la coma por punto y lo convierte a número flotante real
                df[col] = df[col].astype(str).str.replace(',', '.').apply(pd.to_numeric, errors='coerce').fillna(0.0)

        return df

    except Exception as e:
        print(f"Error al conectar con Google Sheets: {e}")
        return None

# Bloque de prueba de conexión
if __name__ == "__main__":
    print("Conectando a Google Sheets...")
    
    # Autenticamos y verificamos la conexión
    try:
        hoja_prueba = conectar()
        
        print("\n¡Conexión exitosa!")
        print(f"Nombre de la pestaña: {hoja_prueba.title}")
    except Exception as e:
        print(f"Error al obtener el título: {e}")

    # Llamamos a la función que trae y limpia los datos
    df_datos = obtener_datos()
    
    if df_datos is not None and not df_datos.empty:
        print(f"Datos recuperados correctamente. Total de filas procesadas: {len(df_datos)}")
        print("\nPrimeras filas del DataFrame:")
        print(df_datos.head())
    else:
        print("\nNo se pudieron cargar los datos o la hoja está vacía.")