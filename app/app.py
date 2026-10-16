"""Radar Estado Peruano: consulta local de la base histórica consolidada."""

from pathlib import Path
import unicodedata

import pandas as pd
import streamlit as st


DATA_PATH = Path(__file__).resolve().parents[1] / "data/processed/funcionarios_gobpe_consolidado.csv"
COLUMNS = ["pagina", "id_funcionario", "nombre", "entidad_url", "perfil"]


def normalize(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(char)
    )


@st.cache_data(show_spinner=False)
def load_data(path: str, modified_ns: int) -> pd.DataFrame:
    # La fecha del archivo invalida la caché si se reemplaza la base.
    df = pd.read_csv(path, sep=";", encoding="utf-8", dtype=str, keep_default_na=False)
    if list(df.columns) != COLUMNS:
        raise ValueError("Las columnas del CSV no coinciden con el esquema esperado.")
    if df.empty or df.apply(lambda col: col.str.strip().eq("").any()).any():
        raise ValueError("La base está vacía o contiene campos obligatorios vacíos.")
    pages = pd.to_numeric(df["pagina"], errors="raise")
    if ((pages < 1) | (pages % 1 != 0)).any():
        raise ValueError("La base contiene números de página inválidos.")
    df["pagina"] = pages.astype(int)
    if df["id_funcionario"].duplicated().any() or df["perfil"].duplicated().any():
        raise ValueError("La base contiene identificadores o perfiles duplicados.")
    if not df["perfil"].str.startswith("https://www.gob.pe/institucion/").all():
        raise ValueError("La base contiene enlaces fuera de la fuente oficial esperada.")
    df["_nombre_busqueda"] = df["nombre"].map(normalize)
    return df


def filter_data(df: pd.DataFrame, query: str, entities: list[str]) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    for term in normalize(query).split():
        mask &= df["_nombre_busqueda"].str.contains(term, regex=False)
    if entities:
        mask &= df["entidad_url"].isin(entities)
    return df.loc[mask].sort_values(["nombre", "entidad_url"], kind="stable")


def export_csv(df: pd.DataFrame) -> bytes:
    return df[COLUMNS].to_csv(index=False, sep=";").encode("utf-8-sig")


def entity_counts(df: pd.DataFrame) -> pd.DataFrame:
    return (df.groupby("entidad_url").size().rename("perfiles").reset_index()
            .sort_values(["perfiles", "entidad_url"], ascending=[False, True])
            .reset_index(drop=True))


def number(value: int) -> str:
    return f"{value:,}"


def main() -> None:
    st.set_page_config(page_title="Radar Estado Peruano", page_icon="🇵🇪", layout="wide")
    st.caption("RADAR ESTADO PERUANO · VERSIÓN 1")
    st.title("Explora los perfiles del Estado")
    st.markdown("Consulta histórica de perfiles de funcionarios publicados en **gob.pe**.")
    st.info("Un perfil en esta base no acredita que la persona ejerza actualmente un cargo. "
            "La fuente no contiene fechas de ejercicio, cargos ni remuneraciones.")
    try:
        with st.spinner("Cargando la base consolidada…"):
            df = load_data(str(DATA_PATH), DATA_PATH.stat().st_mtime_ns)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        st.error(f"No se pudo cargar la base consolidada: {exc}")
        st.stop()

    metrics = st.columns(3)
    metrics[0].metric("Perfiles únicos", number(df["id_funcionario"].nunique()))
    metrics[1].metric("Identificadores de entidades", number(df["entidad_url"].nunique()))
    metrics[2].metric("Cobertura de páginas", f'{number(df["pagina"].min())} – {number(df["pagina"].max())}')
    st.caption(f'{number(df["pagina"].nunique())} páginas distintas representadas en la base. '
               "Los indicadores superiores corresponden al conjunto completo.")
    if len(df) != 41866:
        st.warning(f"Se esperaban 41,866 registros; el archivo contiene {number(len(df))}.")

    st.subheader("Encuentra un perfil")
    query = st.text_input("Nombre y apellidos", placeholder="Ejemplo: José Pérez", key="query",
                          help="Ignora mayúsculas y tildes. Busca todos los términos, en cualquier orden.")
    entities = st.multiselect("Entidad pública (identificador de la fuente)",
                              sorted(df["entidad_url"].unique()), key="entities",
                              placeholder="Todas las entidades · escribe para buscar")
    st.caption("Los identificadores se muestran tal como aparecen en el CSV; no son nombres oficiales completos.")
    filtered = filter_data(df, query, entities)
    st.markdown(f"**{number(len(filtered))} perfiles encontrados** · "
                f'{number(filtered["entidad_url"].nunique())} entidades')
    profiles_tab, entities_tab = st.tabs(["Perfiles", "Entidades por cantidad de perfiles"])
    with profiles_tab:
        if filtered.empty:
            st.warning("No hay coincidencias. Prueba menos términos o cambia las entidades seleccionadas.")
        st.dataframe(filtered[["nombre", "entidad_url", "perfil"]], hide_index=True,
                     width="stretch", height=480,
                     column_config={
                         "nombre": st.column_config.TextColumn("Nombre", width="large"),
                         "entidad_url": st.column_config.TextColumn("Entidad (identificador)"),
                         "perfil": st.column_config.LinkColumn("Ficha oficial", display_text="Ver en gob.pe"),
                     })
        st.download_button("Descargar resultados en CSV", data=export_csv(filtered),
                           file_name="radar_estado_peru_resultados.csv", mime="text/csv",
                           disabled=filtered.empty)
        st.caption("Descarga todas las coincidencias con las cinco columnas originales, "
                   "separadas por punto y coma y en UTF-8 con BOM para Excel.")
    with entities_tab:
        st.caption("Conteo de perfiles según la búsqueda y los filtros actuales. "
                   "Sin filtros, muestra todas las entidades de la base.")
        st.dataframe(entity_counts(filtered), hide_index=True, width="stretch", height=480,
                     column_config={"entidad_url": "Entidad (identificador)",
                                    "perfiles": st.column_config.NumberColumn("Cantidad de perfiles", format="%d")})
    st.divider()
    st.caption("Fuente: funcionarios_gobpe_consolidado.csv · Relación histórica de perfiles de gob.pe. "
               "La base no permite reconstruir una cronología de cargos ni confirmar vigencia laboral.")


if __name__ == "__main__":
    main()
