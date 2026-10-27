import re
import unicodedata

import pandas as pd


LIMITE_GASTO = 45.20


def _normalizar_texto(valor):
    """Pasa texto a mayúsculas sin acentos y con espacios uniformes."""
    texto = ' '.join(str(valor).strip().upper().split())
    return ''.join(
        caracter for caracter in unicodedata.normalize('NFD', texto)
        if unicodedata.category(caracter) != 'Mn'
    )


def _buscar_columna(df, *terminos):
    """Busca una columna por palabras clave, tolerando acentos y formato."""
    if df is None or df.empty:
        return None

    terminos_norm = [_normalizar_texto(termino) for termino in terminos]
    for columna in df.columns:
        columna_norm = _normalizar_texto(columna)
        if all(termino in columna_norm for termino in terminos_norm):
            return columna
    return None


def _columna_fecha(df):
    return _buscar_columna(df, 'FECHA') or _buscar_columna(df, 'MARCA TEMPORAL')


def _montos_numericos(df, columna):
    """Convierte montos a números y representa datos inválidos como NaN."""
    return pd.to_numeric(
        df[columna].astype(str).str.strip().str.replace(',', '.', regex=False),
        errors='coerce',
    )

def _buscar_columna_estado(df):
    """Encuentra la columna de estado sin depender de mayúsculas o espacios."""
    for columna in df.columns:
        normalizada = ' '.join(str(columna).strip().upper().split())
        if normalizada in ['ESTADO DE VALIDACIÓN', 'ESTADO DE VALIDACION', 'COLUMNA 1']:
            return columna
    return None

def calcular_kpis(df):
    """Calcula el total de registros y la distribución por estado."""
    if df is None or df.empty:
        return {
            'total_registros': 0,
            'conteo_estados': {},
            'registros_sin_estado': 0,
        }

    resultado = {
        'total_registros': int(len(df)),
        'conteo_estados': {},
        'registros_sin_estado': 0,
    }

    columna_estado = _buscar_columna_estado(df)
    if columna_estado is None:
        return resultado

    estados = df[columna_estado].fillna('Sin estado').astype(str).str.strip()
    estados = estados.replace('', 'Sin estado')
    conteo = estados.value_counts(dropna=False)

    resultado['conteo_estados'] = {
        str(estado): int(cantidad) for estado, cantidad in conteo.items()
    }
    resultado['registros_sin_estado'] = int((estados == 'Sin estado').sum())
    return resultado

# ======================================================================
# FUNCIONES DE FERNANDO
# ======================================================================

def contar_por_motivo_gasto(df, columna='Motivo del Gasto'):
    """
    Función 1: Usa un bucle FOR para contar cuántas solicitudes hay por cada motivo.
    """
    conteo_motivos = {}
    
    col_real = next((c for c in df.columns if 'MOTIVO' in str(c).upper()), None)
    
    if col_real:
        lista_motivos = df[col_real].fillna('No especificado').tolist()
        
        for motivo in lista_motivos:
            motivo_limpio = str(motivo).strip()
            if motivo_limpio in conteo_motivos:
                conteo_motivos[motivo_limpio] += 1
            else:
                conteo_motivos[motivo_limpio] = 1
                
    return conteo_motivos

def sumar_montos_por_area(df):
    """
    Función 2: Usa un bucle FOR para sumar el monto total declarado por cada área.
    """
    suma_por_area = {}
    
    col_area_real = None
    col_monto_real = None
    
    for col in df.columns:
        col_norm = str(col).upper()
        if 'ÁREA' in col_norm or 'AREA' in col_norm:
            col_area_real = col
        if 'MONTO' in col_norm:
            col_monto_real = col
            
    if col_area_real and col_monto_real:
        lista_areas = df[col_area_real].fillna('Sin especificar').tolist()
        lista_montos = df[col_monto_real].fillna(0).tolist()
        
        for i in range(len(lista_areas)):
            area = str(lista_areas[i]).strip()
            
            monto_str = str(lista_montos[i]).replace(',', '.')
            try:
                monto_float = float(monto_str)
            except ValueError:
                monto_float = 0.0
            
            if area in suma_por_area:
                suma_por_area[area] += monto_float
            else:
                suma_por_area[area] = monto_float
    else:
        print(f"Error: No se encontraron las columnas. Columnas actuales: {df.columns.tolist()}")
                
    return suma_por_area


# ======================================================================
# FUNCIONES DE PAOLA
# ======================================================================

def sumar_montos_por_persona(df):
    """
    Función Paola 1: Suma cuánto dinero de movilidad ha solicitado cada persona.
    """
    gastos_persona = {}
    col_nombre = next((c for c in df.columns if 'NOMBRE' in str(c).upper() or 'SOLICITANTE' in str(c).upper()), None)
    col_monto = next((c for c in df.columns if 'MONTO' in str(c).upper()), None)
    
    if col_nombre and col_monto:
        lista_nombres = df[col_nombre].fillna('Sin nombre').tolist()
        lista_montos = df[col_monto].fillna(0).tolist()
        
        for i in range(len(lista_nombres)):
            nombre = str(lista_nombres[i]).strip()
            if not nombre:
                nombre = 'Sin nombre'
            monto_str = str(lista_montos[i]).replace(',', '.')
            try:
                monto_float = float(monto_str)
            except ValueError:
                monto_float = 0.0
                
            if nombre in gastos_persona:
                gastos_persona[nombre] += monto_float
            else:
                gastos_persona[nombre] = monto_float
                
    return gastos_persona

def contar_solicitudes_pendientes(df):
    """
    Función Paola 2: Cuenta mediante un bucle cuántas solicitudes de movilidad faltan revisar (estado PENDIENTE).
    """
    pendientes = 0
    col_estado = _buscar_columna_estado(df)
    
    if col_estado:
        lista_estados = df[col_estado].fillna('Sin estado').tolist()
        
        for estado in lista_estados:
            if str(estado).strip().upper() == 'PENDIENTE':
                pendientes += 1
                
    return pendientes


# ======================================================================
# FUNCIONES DE ANDRÉ
# ======================================================================

def calcular_promedio_gasto_movilidad(df):
    """
    Función André 1: Calcula el costo promedio de los viajes/movilidades registradas.
    """
    col_monto = next((c for c in df.columns if 'MONTO' in str(c).upper()), None)
    
    if not col_monto:
        return 0.0
        
    lista_montos = df[col_monto].fillna(0).tolist()
    suma_total = 0.0
    cantidad_viajes = 0
    
    for monto in lista_montos:
        monto_str = str(monto).replace(',', '.')
        try:
            monto_float = float(monto_str)
            if monto_float > 0:
                suma_total += monto_float
                cantidad_viajes += 1
        except ValueError:
            pass
            
    if cantidad_viajes == 0:
        return 0.0
        
    return suma_total / cantidad_viajes

def contar_gastos_excesivos(df, limite=45.20):
    """
    Función André 2: Cuenta cuántos pasajes/movilidades superan el límite de la Normativa SUNAT (S/. 45.20).
    """
    excesivos = 0
    col_monto = next((c for c in df.columns if 'MONTO' in str(c).upper()), None)
    
    if col_monto:
        lista_montos = df[col_monto].fillna(0).tolist()
        
        for monto in lista_montos:
            monto_str = str(monto).replace(',', '.')
            try:
                monto_float = float(monto_str)
                if monto_float > limite:
                    excesivos += 1
            except ValueError:
                pass
                
    return excesivos


# ======================================================================
# NUEVAS FUNCIONES DE ANÁLISIS
# ======================================================================

def validar_registros(df, limite=LIMITE_GASTO):
    """Devuelve filas con campos obligatorios, fecha, DNI o monto inválidos."""
    if df is None or df.empty:
        return []

    columnas_requeridas = [
        ('correo', _buscar_columna(df, 'CORREO')),
        ('nombre', _buscar_columna(df, 'NOMBRE')),
        ('DNI', _buscar_columna(df, 'DNI')),
        ('área/carrera', _buscar_columna(df, 'AREA')),
        ('motivo', _buscar_columna(df, 'MOTIVO')),
        ('código', _buscar_columna(df, 'CODIGO')),
        ('control de ley', _buscar_columna(df, 'CONTROL', 'LEY')),
        ('estado', _buscar_columna(df, 'ESTADO', 'VALIDACION')),
        ('notificación', _buscar_columna(df, 'NOTIFICADO')),
    ]
    columna_fecha = _columna_fecha(df)
    columna_monto = _buscar_columna(df, 'MONTO')
    montos = _montos_numericos(df, columna_monto) if columna_monto else None
    incidencias = []

    for posicion, (_, fila) in enumerate(df.iterrows(), start=2):
        errores = []
        for etiqueta, columna in columnas_requeridas:
            if columna and pd.isna(fila[columna]) or (
                columna and not str(fila[columna]).strip()
            ):
                errores.append(f'{etiqueta} vacío')

        if columna_fecha:
            fecha = pd.to_datetime(fila[columna_fecha], errors='coerce', dayfirst=True)
            if pd.isna(fecha):
                errores.append('fecha inválida o vacía')

        columna_dni = _buscar_columna(df, 'DNI')
        if columna_dni and not pd.isna(fila[columna_dni]):
            dni = re.sub(r'\D', '', str(fila[columna_dni]))
            if len(dni) != 8:
                errores.append('DNI debe tener 8 dígitos')

        if columna_monto:
            monto = montos.loc[fila.name]
            if pd.isna(monto):
                errores.append('monto no numérico o vacío')
            elif monto <= 0:
                errores.append('monto debe ser mayor que cero')
            elif monto > limite:
                errores.append(f'monto excede el límite de S/ {limite:.2f}')

        if errores:
            incidencias.append({'fila': posicion, 'errores': errores})

    return incidencias


def detectar_codigos_duplicados(df):
    """Devuelve códigos repetidos y los números de fila donde aparecen."""
    columna_codigo = _buscar_columna(df, 'CODIGO')
    if df is None or df.empty or not columna_codigo:
        return {}

    filas_por_codigo = {}
    for posicion, codigo in enumerate(df[columna_codigo], start=2):
        codigo_norm = str(codigo).strip().upper()
        if codigo_norm and codigo_norm != 'NAN':
            filas_por_codigo.setdefault(codigo_norm, []).append(posicion)

    return {
        codigo: filas
        for codigo, filas in filas_por_codigo.items()
        if len(filas) > 1
    }


def verificar_control_legal(df, limite=LIMITE_GASTO):
    """Encuentra montos cuyo CONTROL LEY contradice el máximo permitido."""
    if df is None or df.empty:
        return []

    columna_monto = _buscar_columna(df, 'MONTO')
    columna_control = _buscar_columna(df, 'CONTROL', 'LEY')
    if not columna_monto or not columna_control:
        return []

    montos = _montos_numericos(df, columna_monto)
    columna_codigo = _buscar_columna(df, 'CODIGO')
    inconsistencias = []
    for indice, monto in montos.items():
        if pd.isna(monto):
            continue
        control = _normalizar_texto(df.at[indice, columna_control])
        marcado_dentro = 'DENTRO' in control or 'DENTRO DEL LIMITE' in control
        marcado_excede = 'EXCEDE' in control or 'SUPERA' in control
        contradice = (monto > limite and marcado_dentro) or (
            monto <= limite and marcado_excede
        )
        if contradice:
            codigo = df.at[indice, columna_codigo] if columna_codigo else ''
            inconsistencias.append({
                'fila': indice + 2,
                'codigo': str(codigo).strip(),
                'monto': float(monto),
                'control_ley': str(df.at[indice, columna_control]).strip(),
            })
    return inconsistencias


def contar_no_notificados(df):
    """Cuenta gastos que aún no han sido notificados."""
    columna = _buscar_columna(df, 'NOTIFICADO')
    if df is None or df.empty or not columna:
        return 0

    valores_no = {'NO', 'NO NOTIFICADO', 'PENDIENTE'}
    return int(df[columna].fillna('').map(
        lambda valor: _normalizar_texto(valor) in valores_no
    ).sum())


def sumar_montos_por_mes(df):
    """Agrupa los montos declarados por mes (AAAA-MM)."""
    if df is None or df.empty:
        return {}
    columna_fecha = _columna_fecha(df)
    columna_monto = _buscar_columna(df, 'MONTO')
    if not columna_fecha or not columna_monto:
        return {}

    fechas = pd.to_datetime(df[columna_fecha], errors='coerce', dayfirst=True)
    montos = _montos_numericos(df, columna_monto)
    resumen = {}
    for fecha, monto in zip(fechas, montos):
        if pd.isna(fecha) or pd.isna(monto):
            continue
        mes = fecha.strftime('%Y-%m')
        resumen[mes] = resumen.get(mes, 0.0) + float(monto)
    return dict(sorted(resumen.items()))


def sumar_montos_por_estado(df):
    """Agrupa el monto declarado según el estado de validación."""
    if df is None or df.empty:
        return {}
    columna_estado = _buscar_columna(df, 'ESTADO', 'VALIDACION')
    columna_monto = _buscar_columna(df, 'MONTO')
    if not columna_estado or not columna_monto:
        return {}

    resumen = {}
    montos = _montos_numericos(df, columna_monto)
    for estado, monto in zip(df[columna_estado], montos):
        if pd.isna(monto):
            continue
        etiqueta = str(estado).strip() if not pd.isna(estado) else 'Sin estado'
        etiqueta = etiqueta or 'Sin estado'
        resumen[etiqueta] = resumen.get(etiqueta, 0.0) + float(monto)
    return resumen


def calcular_margen_hasta_limite(df, limite=LIMITE_GASTO):
    """Devuelve por gasto cuánto margen queda (negativo si excede el tope)."""
    if df is None or df.empty:
        return []
    columna_monto = _buscar_columna(df, 'MONTO')
    if not columna_monto:
        return []

    columna_codigo = _buscar_columna(df, 'CODIGO')
    montos = _montos_numericos(df, columna_monto)
    resultado = []
    for indice, monto in montos.items():
        if pd.isna(monto):
            continue
        margen = round(limite - float(monto), 2)
        codigo = df.at[indice, columna_codigo] if columna_codigo else ''
        resultado.append({
            'fila': indice + 2,
            'codigo': str(codigo).strip(),
            'monto': float(monto),
            'margen': margen,
            'excede_limite': margen < 0,
        })
    return resultado


# ======================================================================
# BLOQUE DE PRUEBA
# ======================================================================
if __name__ == '__main__':
    from conexion_sheets import obtener_datos

    df_prueba = obtener_datos()
    if df_prueba is None:
        print('No fue posible leer Google Sheets. Revisa conexión y credenciales.')
    elif df_prueba.empty:
        print('La hoja está conectada, pero no contiene registros para analizar.')
    else:
        print('\n' + '=' * 68)
        print('ANÁLISIS DE GASTOS DE MOVILIDAD')
        print(f'Registros analizados: {len(df_prueba)} | Límite: S/ {LIMITE_GASTO:.2f}')
        print('=' * 68)

        print('\n--- FUNCIONES EXISTENTES ---')
        print('1. Solicitudes por motivo (Fernando):')
        for motivo, cantidad in contar_por_motivo_gasto(df_prueba).items():
            print(f'   • {motivo}: {cantidad}')

        print('\n2. Monto acumulado por área/carrera (Fernando):')
        for area, total in sumar_montos_por_area(df_prueba).items():
            print(f'   • {area}: S/ {total:.2f}')

        print('\n3. Monto acumulado por persona (Paola):')
        for persona, total in sumar_montos_por_persona(df_prueba).items():
            print(f'   • {persona}: S/ {total:.2f}')

        print('\n4. Solicitudes pendientes de revisión (Paola):')
        print(f'   • Total pendientes: {contar_solicitudes_pendientes(df_prueba)}')

        print('\n5. Monto promedio por movilidad (André):')
        print(f'   • Promedio: S/ {calcular_promedio_gasto_movilidad(df_prueba):.2f}')

        print('\n6. Gastos que superan S/ 45.20 (André):')
        print(f'   • Total que excede el límite: {contar_gastos_excesivos(df_prueba):}')

        print('\n--- NUEVAS FUNCIONES ---')
        print('7. Validación de registros: detecta campos incompletos, DNI inválido, '
              'monto no válido o monto superior al límite.')
        incidencias = validar_registros(df_prueba)
        print(f'   • Filas con observaciones: {len(incidencias)}')
        for incidencia in incidencias:
            print(f"   • Fila {incidencia['fila']}: {'; '.join(incidencia['errores'])}")

        print('\n8. Detección de códigos duplicados: evita procesar dos veces un gasto.')
        duplicados = detectar_codigos_duplicados(df_prueba)
        if duplicados:
            for codigo, filas in duplicados.items():
                print(f'   • {codigo}: filas {filas}')
        else:
            print('   • No se encontraron códigos duplicados.')

        print('\n9. Consistencia del control legal: compara el monto con CONTROL LEY.')
        inconsistencias = verificar_control_legal(df_prueba)
        if inconsistencias:
            for caso in inconsistencias:
                print(f"   • Fila {caso['fila']} ({caso['codigo']}): "
                      f"S/ {caso['monto']:.2f} marcado como {caso['control_ley']}")
        else:
            print('   • No se encontraron contradicciones.')

        print('\n10. Notificaciones pendientes: cuenta registros no notificados.')
        print(f'   • Pendientes de notificar: {contar_no_notificados(df_prueba)}')

        print('\n11. Total de gastos por mes: ayuda a comparar periodos.')
        resumen_mensual = sumar_montos_por_mes(df_prueba)
        if resumen_mensual:
            for mes, total in resumen_mensual.items():
                print(f'   • {mes}: S/ {total:.2f}')
        else:
            print('   • No hay fechas y montos válidos para agrupar.')

        print('\n12. Monto por estado: muestra el importe aprobado, pendiente o descartado.')
        resumen_estados = sumar_montos_por_estado(df_prueba)
        if resumen_estados:
            for estado, total in resumen_estados.items():
                print(f'   • {estado}: S/ {total:.2f}')
        else:
            print('   • No hay estados y montos válidos para resumir.')

        print('\n13. Margen hasta el límite: positivo = disponible; negativo = excedido.')
        for gasto in calcular_margen_hasta_limite(df_prueba):
            codigo = gasto['codigo'] or f"fila {gasto['fila']}"
            print(f"   • {codigo}: gasto S/ {gasto['monto']:.2f}; "
                  f"margen S/ {gasto['margen']:.2f}")

        print('\n' + '=' * 68)