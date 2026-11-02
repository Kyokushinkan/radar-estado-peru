import sqlite3
"""Pantalla aislada V2.5.3: movimientos observados."""

import pandas as pd
import streamlit as st

from app.datos_movimientos_v253 import (
    cargar_movimientos,
    cargar_movimientos_json,
    filtrar_movimientos,
)


COLUMNAS = {
    "id_funcionario": "ID funcionario",
    "campo": "Campo observado",
    "valor_anterior": "Valor anterior",
    "valor_nuevo": "Valor publicado",
    "fecha_deteccion": "Fecha de deteccion",
    "clasificacion": "Clasificacion",
    "verificacion_oficial": "Verificacion oficial",
    "perfil_oficial": "Ficha Gob.pe",
    "fuente_oficial": "Fuente oficial",
}


def preparar_tabla(registros):
    """Prepara datos para mostrar, sin alterar su significado."""
    if not registros:
        return pd.DataFrame(columns=list(COLUMNAS.values()))

    tabla = pd.DataFrame(registros)

    for columna in COLUMNAS:
        if columna not in tabla.columns:
            tabla[columna] = ""

    return tabla[list(COLUMNAS)].rename(columns=COLUMNAS)


def mostrar(ruta):
    """Renderiza una seccion independiente del dashboard V2.5.3."""
    st.header("Movimientos observados")
    st.caption(
        "Cambios detectados entre publicaciones de perfiles de Gob.pe. "
        "No acreditan por si mismos nombramientos, ceses ni traslados."
    )

    try:
        registros = (cargar_movimientos_json(ruta) if str(ruta).lower().endswith('.json') else cargar_movimientos(ruta))
    except (OSError, ValueError, TypeError, sqlite3.Error) as error:
        st.error("No fue posible leer los movimientos: " + str(error))
        return

    if not registros:
        st.info("Sin cambios observados registrados.")
        st.caption(
            "La ausencia de registros no demuestra que no existan "
            "movimientos de funcionarios."
        )
        return

    a, b, c = st.columns(3)
    a.metric("Cambios registrados", len(registros))
    b.metric(
        "Verificacion pendiente",
        sum(
            r.get("verificacion_oficial") == "pendiente"
            for r in registros
        )
    )
    c.metric(
        "Otros estados de verificacion",
        sum(
            r.get("verificacion_oficial") != "pendiente"
            for r in registros
        )
    )

    funcionario = st.text_input(
        "ID del funcionario",
        key="v25_mov_funcionario"
    )

    campos = sorted({
        str(r.get("campo", ""))
        for r in registros if r.get("campo")
    })

    estados = sorted({
        str(r.get("verificacion_oficial", ""))
        for r in registros if r.get("verificacion_oficial")
    })

    col1, col2 = st.columns(2)

    with col1:
        campo = st.selectbox(
            "Campo modificado",
            ["Todos"] + campos,
            key="v25_mov_campo"
        )

    with col2:
        verificacion = st.selectbox(
            "Estado de verificacion",
            ["Todos"] + estados,
            key="v25_mov_verificacion"
        )

    filtrados = filtrar_movimientos(
        registros,
        funcionario=funcionario,
        campo="" if campo == "Todos" else campo,
        verificacion="" if verificacion == "Todos" else verificacion,
    )

    st.caption(
        "Resultados: " + str(len(filtrados))
        + ". Fuente: historial de observaciones y exportacion validada."
    )

    tabla = preparar_tabla(filtrados)

    st.dataframe(
        tabla,
        hide_index=True,
        width="stretch",
        column_config={
            "Ficha Gob.pe": st.column_config.LinkColumn(
                "Ficha Gob.pe",
                display_text="Abrir ficha"
            ),
            "Fuente oficial": st.column_config.LinkColumn(
                "Fuente oficial",
                display_text="Consultar"
            ),
        },
    )

    st.download_button(
        "Exportar movimientos filtrados CSV",
        tabla.to_csv(index=False).encode("utf-8-sig"),
        file_name="movimientos_observados_v25.csv",
        mime="text/csv",
        disabled=tabla.empty,
        key="v25_mov_exportar",
    )

    st.warning(
        "Un cambio observado no constituye confirmacion oficial "
        "de nombramiento, cese o traslado."
    )