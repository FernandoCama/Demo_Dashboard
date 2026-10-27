from pathlib import Path
import unicodedata

import matplotlib
matplotlib.use('Agg')  # Genera la imagen sin abrir una ventana gráfica.
import matplotlib.pyplot as plt
import plotly.graph_objects as go # IMPORTACIÓN DE PLOTLY AÑADIDA

CARPETA_STATIC = Path(__file__).resolve().parent / 'static'
RUTA_GRAFICO = CARPETA_STATIC / 'grafico_estados.png'


def _normalizar_texto(valor):
    """Normaliza un texto para comparar nombres de columnas con seguridad."""
    texto = ' '.join(str(valor).strip().upper().split())
    return ''.join(
        caracter for caracter in unicodedata.normalize('NFD', texto)
        if unicodedata.category(caracter) != 'Mn'
    )


def _buscar_columna_estado(df):
    """Encuentra la columna de validación aunque cambien acentos o espacios."""
    if df is None or df.empty:
        return None

    for columna in df.columns:
        if _normalizar_texto(columna) == 'ESTADO DE VALIDACION':
            return columna
    return None


def colores_para_estados(estados):
    """Asigna colores semánticos compartidos por el gráfico y el resumen."""
    colores_semanticos = {
        'aprobado': '#075982',
        'aprobada': '#075982',
        'approved': '#075982',
        'pendiente': '#f5b335',
        'pending': '#f5b335',
        'descartado': '#d96b5f',
        'descartada': '#d96b5f',
        'rejected': '#d96b5f',
    }
    paleta_extra = ['#438b9d', '#82a95d', '#7186a0', '#b98744', '#d96b5f']
    colores = {}

    for estado in estados:
        clave = _normalizar_texto(estado).casefold()
        colores[estado] = colores_semanticos.get(
            clave,
            paleta_extra[len(colores) % len(paleta_extra)],
        )

    return colores

# =====================================================================
# FUNCIÓN ORIGINAL: MATPLOTLIB (Mantenida intacta)
# =====================================================================
def generar_graficos(df):
    """Genera un gráfico de barras estático (PNG) con Matplotlib."""
    CARPETA_STATIC.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=160)
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#ffffff')

    columna_estado = _buscar_columna_estado(df)
    if columna_estado is None:
        ax.axis('off')
        if df is None or df.empty:
            mensaje = 'No hay datos disponibles'
        else:
            mensaje = 'No se encontró la columna\nESTADO DE VALIDACIÓN'
        ax.text(0.5, 0.5, mensaje, ha='center', va='center',
                color='#6d8090', fontsize=12, transform=ax.transAxes)
    else:
        estados = df[columna_estado].fillna('Sin estado').astype(str).str.strip()
        estados = estados.replace('', 'Sin estado')
        conteo = estados.value_counts()
        total_registros = int(conteo.sum())

        if conteo.empty or total_registros == 0:
            ax.axis('off')
            ax.text(0.5, 0.5, 'No hay estados para mostrar', ha='center',
                    va='center', color='#6d8090', fontsize=12,
                    transform=ax.transAxes)
        else:
            colores_base = ['#075982', '#f5b335', '#438b9d', '#82a95d',
                            '#d96b5f', '#7186a0', '#b98744']
            colores = [colores_base[i % len(colores_base)]
                       for i in range(len(conteo))]

            barras = ax.bar(
                conteo.index.astype(str),
                conteo.values,
                color=colores,
                width=0.58,
                edgecolor='none',
                zorder=3,
            )

            ax.set_title('Estado de las solicitudes', fontsize=14,
                         pad=16, fontweight='bold', color='#173c56')
            ax.set_xlabel('Estado', fontsize=10, color='#6d8090', labelpad=10)
            ax.set_ylabel('Cantidad', fontsize=10, color='#6d8090', labelpad=8)
            ax.tick_params(axis='x', labelsize=9, colors='#3e5e72', length=0, pad=8)
            ax.tick_params(axis='y', labelsize=9, colors='#6d8090', length=0)
            plt.setp(ax.get_xticklabels(), rotation=15, ha='right')

            for barra in barras:
                altura = int(barra.get_height())
                porcentaje = (altura / total_registros) * 100
                texto = f'{altura}\n({porcentaje:.1f}%)'
                ax.annotate(
                    texto,
                    xy=(barra.get_x() + barra.get_width() / 2, altura),
                    xytext=(0, 5),
                    textcoords='offset points',
                    ha='center',
                    va='bottom',
                    fontsize=9,
                    fontweight='bold',
                    color='#3e5e72',
                )

            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_visible(False)
            ax.spines['bottom'].set_color('#e3eaee')
            ax.grid(axis='y', linestyle='--', linewidth=0.7,
                    color='#d7e3e9', alpha=0.65, zorder=0)
            ax.set_axisbelow(True)
            ax.set_ylim(0, max(conteo.values) * 1.28)

    fig.tight_layout()
    fig.savefig(RUTA_GRAFICO, dpi=180, facecolor=fig.get_facecolor(),
                bbox_inches='tight')
    plt.close(fig)
    return str(RUTA_GRAFICO)

# =====================================================================
# FUNCIÓN NUEVA: PLOTLY INTERACTIVO (Añadida)
# =====================================================================
def grafico_estados_interactivo(df):
    """Genera un gráfico horizontal con cantidades visibles de forma permanente."""
    fig = go.Figure()
    
    columna_estado = _buscar_columna_estado(df)
    
    if columna_estado is None or df is None or df.empty:
        # Si no hay datos, retornamos una figura vacía con un mensaje
        fig.update_layout(title="No hay datos disponibles para el gráfico")
        return fig
        
    estados = df[columna_estado].fillna('Sin estado').astype(str).str.strip()
    estados = estados.replace('', 'Sin estado')
    conteo = estados.value_counts()
    
    etiquetas = conteo.index.tolist()
    cantidades = conteo.astype(int).tolist()
    total_registros = sum(cantidades)
    porcentajes = [cantidad / total_registros * 100 for cantidad in cantidades]
    etiquetas_cantidad = [
        f'{cantidad} ({porcentaje:.1f}%)'
        for cantidad, porcentaje in zip(cantidades, porcentajes)
    ]
    
    colores_por_estado = colores_para_estados(etiquetas)
    colores = [colores_por_estado[estado] for estado in etiquetas]

    fig.add_trace(go.Bar(
        x=cantidades,
        y=etiquetas,
        orientation='h',
        marker=dict(
            color=colores,
            line=dict(color='rgba(255,255,255,0.82)', width=1.5),
            opacity=0.94,
        ),
        text=etiquetas_cantidad,
        textposition='outside',
        cliponaxis=False,
        customdata=list(zip(porcentajes, colores)),
        # Se muestra una tarjeta propia desde el evento de hover, no la etiqueta
        # nativa de Plotly, que puede recortarse o perder contraste.
        hoverinfo='none',
        hoverlabel=dict(
            bgcolor='#07395a',
            bordercolor='#07395a',
            font=dict(color='#ffffff', size=13),
            align='left',
            namelength=-1,
        ),
    ))

    fig.update_layout(
        template='plotly_white',
        margin=dict(l=20, r=90, t=20, b=45),
        height=max(310, 58 * len(etiquetas) + 80),
        showlegend=False,
        bargap=0.35,
        barcornerradius='12px',
        hovermode='closest',
        hoverdistance=30,
        transition=dict(duration=650, easing='cubic-in-out'),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        hoverlabel=dict(
            bgcolor='#07395a',
            bordercolor='#07395a',
            font=dict(color='#ffffff', size=13),
            align='left',
        ),
        xaxis=dict(
            title='Cantidad',
            range=[0, max(cantidades) * 1.4],
            rangemode='tozero',
            showgrid=True,
            gridcolor='#e8edf5',
            zeroline=False,
        ),
        yaxis=dict(
            title='Estado',
            autorange='reversed',
            automargin=True,
        ),
    )

    return fig