"""Vista 2D ligera: reproduce estados del simulador, sin lógica de asignación."""
import html
import time
import streamlit as st
from pathlib import Path
import streamlit.components.v1 as components

COMPONENTES = Path(__file__).parent / "componentes"
_mapa_interactivo = components.declare_component("mapa_agv_2d", path=str(COMPONENTES / "mapa_2d"))

from app.models.bateria import CARGADORES, VELOCIDAD_REFERENCIA_MS, CARGA_PALLET_S, DESCARGA_PALLET_S
from app.services.simulador_flota import SimuladorFlota, ParametrosSimulacion
from app.services.estado_visual import cargar_mapa, estado_en_instante


def horas_minutos(segundos):
    minutos = max(0, int(round(segundos / 60)))
    return f"{minutos // 60} h {minutos % 60:02d} min"


def avanzar_reloj(reloj, ahora, limite):
    """La hora real solo mueve el cursor; el modelo recibe segundos simulados."""
    if reloj["ejecutando"]:
        reloj["tiempo_s"] = min(limite, reloj["tiempo_s"] + max(0, ahora-reloj["marca"]) * reloj["velocidad"])
        if reloj["tiempo_s"] >= limite:
            reloj["ejecutando"] = False
    reloj["marca"] = ahora


def nombre_nodo(nodo):
    return {
        # Pallet Transit: un punto de parada a cada lado de cada estación.
        "ControlPoint13": "Pallet Transit 1 · Izq.",
        "ControlPoint12": "Pallet Transit 1 · Der.",
        "ControlPoint11": "Pallet Transit 2 · Izq.",
        "ControlPoint27": "Pallet Transit 2 · Der.",
        "ControlPoint8": "Pallet Transit 3 · Izq.",
        "ControlPoint10": "Pallet Transit 3 · Der.",
        "ControlPoint7": "Pallet Transit 4 · Izq.",
        "ControlPoint9": "Pallet Transit 4 · Der.",
        # Entrada de materia prima a las líneas.
        "ControlPoint23": "Entrada Cookies 1",
        "ControlPoint21": "Entrada Cookies 2",
        "ControlPoint22": "Entrada Cookies 3",
        "ControlPoint17": "Entrada Chocolate",
        "ControlPoint14": "Entrada Wafer",
        # Fin de línea / producto terminado.
        "ControlPoint24": "Cookies 1",
        "ControlPoint25": "Cookies 2",
        "ControlPoint26": "Cookies 3",
        "ControlPoint18": "Chocolate",
        "ControlPoint15": "Wafer",
        **{n: f"Cargador CP{n.removeprefix('ControlPoint')}" for n in CARGADORES},
    }.get(nodo, nodo)


LINEAS_VISUALES = {
    "COOKIE_1": {"titulo": "COOKIES 1", "fin": "ControlPoint24"},
    "COOKIE_2": {"titulo": "COOKIES 2", "fin": "ControlPoint25"},
    "COOKIE_3": {"titulo": "COOKIES 3", "fin": "ControlPoint26"},
    "CHOCOLATE": {"titulo": "CHOCOLATE", "fin": "ControlPoint18"},
    "WAFER": {"titulo": "WAFER", "fin": "ControlPoint15"},
}


def estado_lineas_produccion(resultado, tiempo_s, flota):
    """Estado visual de las líneas usando la agenda ya calculada por la simulación.

    Es solo presentación: no añade tiempos ni cambia la lógica de producción,
    misiones, rutas o asignación de AGV.
    """
    base = {linea: {"estado": "ESPERA", "progreso": None, "pallet": "—"}
            for linea in LINEAS_VISUALES}
    if not resultado:
        return base

    t = max(0.0, float(tiempo_s))
    por_linea = {}
    for linea, datos in LINEAS_VISUALES.items():
        tareas = sorted(
            (m for m in resultado["movimientos"]
             if m["tipo"] == "producto_terminado" and m["linea"] == linea),
            key=lambda m: m["llegada_s"],
        )
        if not tareas:
            por_linea[linea] = base[linea]
            continue

        # Un pallet está listo desde que aparece en la agenda hasta que termina
        # la carga al AGV. Si hay cola, permanece visible en el fin de línea.
        listos = []
        for m in tareas:
            fin_recogida = (m["inicio_s"] + m["vacio"]["tiempo_s"] +
                            m["espera_disponibilidad_s"] + m["carga_s"])
            if m["llegada_s"] <= t < fin_recogida:
                listos.append(m)

        agv_cargando = next((a for a in flota
                             if a["origen"] == datos["fin"] and
                             a["estado"] == "CARGANDO_PALLET"), None)
        if listos:
            actual = listos[0]
            por_linea[linea] = {
                "estado": "RECOGIENDO" if agv_cargando else "LISTO",
                "progreso": 1.0,
                "pallet": actual["id_pallet"],
            }
            continue

        # Entre dos llegadas de producto terminado, el siguiente pallet se
        # representa avanzando suavemente por la banda. Es una visualización
        # del ciclo ya programado, no un nuevo modelo de proceso.
        siguiente_i = next((i for i, m in enumerate(tareas) if m["llegada_s"] > t), None)
        if siguiente_i is None:
            por_linea[linea] = {"estado": "COMPLETO", "progreso": None, "pallet": "—"}
            continue

        siguiente = tareas[siguiente_i]
        inicio = tareas[siguiente_i - 1]["llegada_s"] if siguiente_i else 0.0
        fin = siguiente["llegada_s"]
        progreso = 0.0 if fin <= inicio else max(0.0, min(1.0, (t - inicio) / (fin - inicio)))
        por_linea[linea] = {
            "estado": "PRODUCIENDO",
            "progreso": progreso,
            "pallet": siguiente["id_pallet"],
        }

    return por_linea


def lineas_produccion_svg(nodos, xy, estados_linea=None):
    """Dibuja solo las cinco líneas de producción; sin almacén ni Pallet Transit."""
    estados_linea = estados_linea or {}
    partes = []
    orden = [
        ("COOKIE_3", "ControlPoint26", "COOKIES 3"),
        ("COOKIE_2", "ControlPoint25", "COOKIES 2"),
        ("COOKIE_1", "ControlPoint24", "COOKIES 1"),
        ("CHOCOLATE", "ControlPoint18", "CHOCOLATE"),
        ("WAFER", "ControlPoint15", "WAFER"),
    ]
    for clave, nodo, titulo in orden:
        x, y = xy(nodos[nodo])
        bx, by, bw, bh = x + 22, y - 24, 190, 48
        estado = estados_linea.get(clave, {"estado": "ESPERA", "progreso": None, "pallet": "—"})
        nombre_estado = estado["estado"]
        progreso = estado.get("progreso")

        if nombre_estado == "PRODUCIENDO":
            texto_estado, color_estado_linea = "PRODUCIENDO", "#b86b13"
        elif nombre_estado == "LISTO":
            texto_estado, color_estado_linea = "LISTO", "#287c64"
        elif nombre_estado == "RECOGIENDO":
            texto_estado, color_estado_linea = "RECOGIENDO", "#286ca3"
        elif nombre_estado == "COMPLETO":
            texto_estado, color_estado_linea = "COMPLETO", "#64748b"
        else:
            texto_estado, color_estado_linea = "ESPERA", "#8b98a8"

        partes.append(f'<line x1="{x+5}" y1="{y}" x2="{bx}" y2="{y}" stroke="#aeb9c6" stroke-width="2"/>')
        partes.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="10" fill="#ffffff" stroke="#dfe5eb" stroke-width="1.2"/>')
        partes.append(f'<rect x="{bx}" y="{by}" width="4" height="{bh}" rx="2" fill="#c42336"/>')
        partes.append(f'<text x="{bx+12}" y="{by+15}" font-family="Arial,sans-serif" font-size="10.5" font-weight="800" fill="#28364a">{titulo}</text>')
        partes.append(f'<circle cx="{bx+bw-72}" cy="{by+12}" r="3" fill="{color_estado_linea}"/>')
        partes.append(f'<text x="{bx+bw-10}" y="{by+15}" text-anchor="end" font-family="Arial,sans-serif" font-size="7.5" font-weight="800" fill="{color_estado_linea}">{texto_estado}</text>')
        partes.append(f'<text x="{bx+12}" y="{by+27}" font-family="Arial,sans-serif" font-size="7.5" font-weight="700" letter-spacing=".55" fill="#8793a3">LÍNEA DE PRODUCCIÓN</text>')

        # Banda y estaciones. El bloque ámbar representa el pallet/caja.
        cy = by + 38
        inicio_banda = bx + 82
        fin_banda = bx + bw - 25
        partes.append(f'<line x1="{inicio_banda}" y1="{cy}" x2="{bx+bw-13}" y2="{cy}" stroke="#aeb9c6" stroke-width="3" stroke-linecap="round"/>')
        for i in range(5):
            cx = bx + 91 + i * 17
            partes.append(f'<circle cx="{cx}" cy="{cy}" r="2.4" fill="#d9e0e7" stroke="#9aa8b7"/>')
        partes.append(f'<rect x="{bx+78}" y="{cy-7}" width="13" height="14" rx="2.5" fill="#eef2f6" stroke="#9eabb9"/>')
        partes.append(f'<rect x="{bx+bw-34}" y="{cy-7}" width="13" height="14" rx="2.5" fill="#f8e8eb" stroke="#c42336"/>')

        if progreso is not None:
            px_pallet = inicio_banda + (fin_banda - inicio_banda) * max(0.0, min(1.0, progreso))
            partes.append(
                f'<g class="linea-pallet" data-linea="{clave}" transform="translate({px_pallet:.3f} {cy:.3f})">'
                f'<rect x="-6" y="-6" width="12" height="12" rx="2" fill="#e9bd78" stroke="#bd8540" stroke-width="1"/>'
                f'<line x1="-5" y1="7" x2="5" y2="7" stroke="#9f6f36" stroke-width="1.4"/>'
                f'<title>{html.escape(estado.get("pallet", "Pallet"))}</title>'
                '</g>'
            )

    return partes


def mapa_svg(mapa, flota, seleccionado, estados_linea=None):
    nodos = {n["id"]: (n["x"], n["y"]) for n in mapa["nodos"]}
    xs, ys = zip(*nodos.values())
    ancho, alto = 1000, 720
    escala = min(760/(max(xs)-min(xs)), 565/(max(ys)-min(ys)))
    margen_x = (ancho-(max(xs)-min(xs))*escala)/2
    margen_y = (alto-(max(ys)-min(ys))*escala)/2
    def xy(pos):
        return (margen_x+(pos[0]-min(xs))*escala, alto-margen_y-(pos[1]-min(ys))*escala)
    def linea(a,b,color,grosor):
        x,y=xy(a);u,v=xy(b)
        return f'<line x1="{x}" y1="{y}" x2="{u}" y2="{v}" stroke="{color}" stroke-width="{grosor}" stroke-linecap="round" vector-effect="non-scaling-stroke"/>'
    partes=[f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="Mapa AGV 2D" xmlns="http://www.w3.org/2000/svg">',
            '<defs><pattern id="cuadricula" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".7" fill="#dfe5eb"/></pattern></defs>',
            '<rect x="-10000" y="-10000" width="20000" height="20000" fill="#f8fafb"/><rect x="-10000" y="-10000" width="20000" height="20000" fill="url(#cuadricula)"/>']
    partes.extend(lineas_produccion_svg(nodos, xy, estados_linea))
    for e in mapa["aristas"]:
        partes.append(linea(nodos[e["origen"]],nodos[e["destino"]],"#b9c4d0",2))
    for a in flota:
        if a["agv"] == seleccionado:
            for origen,destino in zip(a["ruta"],a["ruta"][1:]):
                partes.append(linea(nodos[origen],nodos[destino],"#c42336",3.5))
    etiquetas=[]
    puntos_parada = {
        # Pallet Transit, ambos lados.
        "ControlPoint13", "ControlPoint12", "ControlPoint11", "ControlPoint27",
        "ControlPoint8", "ControlPoint10", "ControlPoint7", "ControlPoint9",
        # Entradas de materia prima.
        "ControlPoint23", "ControlPoint21", "ControlPoint22", "ControlPoint17", "ControlPoint14",
        # Fines de línea.
        "ControlPoint24", "ControlPoint25", "ControlPoint26", "ControlPoint18", "ControlPoint15",
    }
    etiquetas_sin_caja = {
        "ControlPoint24", "ControlPoint25", "ControlPoint26", "ControlPoint18", "ControlPoint15",
        # Pallet Transit: mantener solo los cuadrados y el tooltip, sin etiquetas visibles.
        "ControlPoint13", "ControlPoint12", "ControlPoint11", "ControlPoint27",
        "ControlPoint8", "ControlPoint10", "ControlPoint7", "ControlPoint9",
    }
    for nodo,pos in nodos.items():
        x,y=xy(pos); label=nombre_nodo(nodo)
        partes.append(f'<circle cx="{x}" cy="{y}" r="2.7" fill="#94a3b4"><title>{html.escape(label if label != nodo else nodo)}</title></circle>')
        if nodo in CARGADORES:
            # Cargadores: misma forma cuadrada, verde para distinguirlos de paradas.
            partes.append(f'<rect x="{x-5}" y="{y-5}" rx="2" width="10" height="10" fill="#2f9e68" stroke="white" stroke-width="1.5"><title>{html.escape(label)}</title></rect>')
            etiquetas.append((x,y,label,nodo))
        elif nodo in puntos_parada:
            # Pallet Transit, entradas y fin de línea se mantienen grises.
            partes.append(f'<rect x="{x-5}" y="{y-5}" rx="2" width="10" height="10" fill="#536477" stroke="white" stroke-width="1.5"><title>{html.escape(label)}</title></rect>')
            if nodo not in etiquetas_sin_caja:
                etiquetas.append((x,y,label,nodo))
    cajas=[]
    for x,y,label,nodo in sorted(etiquetas,key=lambda e:e[1]):
        derecha=nodo in ("ControlPoint24","ControlPoint25","ControlPoint26","ControlPoint18","ControlPoint15")
        w=len(label)*6.7+16;lx=x+14 if derecha else x-w-14;ly=y-13
        lx=max(12,min(ancho-w-12,lx))
        while any(lx < bx+bw+5 and lx+w+5 > bx and ly < by+bh+4 and ly+24+4 > by for bx,by,bw,bh in cajas):
            ly+=26
        cajas.append((lx,ly,w,24))
        partes.append(f'<path d="M{x},{y} L{lx if derecha else lx+w},{ly+12}" stroke="#bdc7d2" fill="none"/>')
        partes.append(f'<rect x="{lx}" y="{ly}" width="{w}" height="24" rx="5" fill="white" fill-opacity=".95" stroke="#e4e9ef"/><text x="{lx+8}" y="{ly+16}" font-family="Arial,sans-serif" font-size="12" font-weight="600" fill="#3c4b60">{html.escape(label)}</text>')
    posiciones={}
    for a in flota:
        x,y=xy(a["posicion"]); clave=(round(x),round(y))
        indice=posiciones.get(clave,0);posiciones[clave]=indice+1
        color=color_estado(a["estado"])
        label_y=-36-indice*26
        # Todo el AGV vive dentro de un grupo trasladable. El componente web puede
        # interpolar este transform entre actualizaciones del simulador sin tocar
        # la lógica de rutas, Dijkstra ni el reloj de Python.
        partes.append(f'<g class="agv-marker" data-agv="{html.escape(a["agv"])}" transform="translate({x:.3f} {y:.3f})">')
        partes.append(f'<circle cx="0" cy="0" r="22" fill="{color}" fill-opacity=".09"/>')
        if a["agv"] == seleccionado:
            partes.append(f'<circle cx="0" cy="0" r="23" fill="none" stroke="{color}" stroke-opacity=".45" stroke-width="1.5"/>')
        partes.append(f'<rect x="-13" y="-9" rx="4" width="26" height="18" fill="{color}" stroke="white" stroke-width="2"/><rect x="-7" y="-5" width="8" height="10" rx="2" fill="white" fill-opacity=".8"/>')
        if a["pallet"] != "—":
            partes.append('<rect x="2" y="-4" width="8" height="8" rx="1" fill="#f0c47d"/>')
        partes.append(f'<path d="M0,-11 L30,{label_y+12}" stroke="{color}" stroke-opacity=".6"/><rect x="7" y="{label_y-7}" width="79" height="23" rx="5" fill="white" stroke="{color}" stroke-width="1.2"/><text x="15" y="{label_y+9}" font-family="Arial,sans-serif" font-size="14" font-weight="700" fill="{color}">{html.escape(a["agv"])}</text>')
        partes.append('</g>')
    partes.append('</svg>')
    return ''.join(partes)


def color_estado(estado):
    if "BATERIA" in estado or "CARGADOR" in estado:
        return "#286ca3"
    return "#287c64" if estado == "DISPONIBLE" else "#c42336"


def tarjeta_agv(a):
    color=color_estado(a["estado"])
    carga=(f'<div class="agv-row"><span>Hasta 100 %</span><b>{horas_minutos(a["carga_restante_s"])}</b></div>'
           if a["carga_restante_s"] is not None else '')
    return (f'<div class="agv-card" style="--estado:{color}"><div class="agv-top"><span>{html.escape(a["agv"])}</span><span>{a["bateria"]:.0f} %</span></div>'
            f'<div class="agv-status"><i class="agv-dot"></i>{html.escape(a["estado"].replace("_"," "))}</div>'
            f'<div class="battery-track"><span style="width:{min(100,max(0,a["bateria"]))}%"></span></div>'
            f'<div class="agv-row"><span>Hasta reserva 20 %</span><b>{horas_minutos(a["uso_restante_s"])}</b></div>{carga}'
            f'<div class="agv-row"><span>Destino</span><b>{html.escape(nombre_nodo(a["destino"]))}</b></div>'
            f'<div class="agv-foot">{html.escape(a["mision"])} · {html.escape(a["pallet"])}</div></div>')


def mostrar_mapa(mapa, flota, seleccionado, estados_linea=None):
    _mapa_interactivo(svg=mapa_svg(mapa, flota, seleccionado, estados_linea), key="mapa_2d_explorable", default=None)


def tabla_operativa(filas, mensaje):
    if not filas:
        st.html(f'<div class="tabla-operativa tabla-vacia">{html.escape(mensaje)}</div>')
        return
    columnas=list(filas[0])
    cabecera=''.join(f'<th>{html.escape(c)}</th>' for c in columnas)
    cuerpo=''.join('<tr>'+''.join(f'<td>{html.escape(str(f[c]))}</td>' for c in columnas)+'</tr>' for f in filas)
    st.html(f'<div class="tabla-operativa"><table><thead><tr>{cabecera}</tr></thead><tbody>{cuerpo}</tbody></table></div>')


@st.fragment(run_every=0.2)
def mostrar_2d():
    if st.session_state.get("modo_principal") != "Simulación 2D":
        return
    with st.container(key="vista2d"):
        st.html('<style>'+ (COMPONENTES / "estilos_2d.css").read_text(encoding="utf-8") +'</style>')
        st.html('<div class="control-cabecera"><div><div class="eyebrow">INTRALOGÍSTICA · CONTROL DE FLOTA</div><h2>Centro de operaciones AGV</h2><p>Producto terminado · 215 pallets por turno · Simulación 2D</p></div><div class="marca-reservada" aria-label="Espacio reservado para el logo de Nestlé">Nestlé<small>ESPACIO PARA LOGO</small></div></div>')
        resultado = st.session_state.get("resultado_2d")
        reloj = st.session_state.setdefault("reloj_2d", {"tiempo_s": 0., "marca": time.monotonic(), "ejecutando": False, "velocidad": 1})
        if resultado:
            avanzar_reloj(reloj, time.monotonic(), resultado["kpis"]["tiempo_total_s"])
        controles = st.columns([1,1,1,1,1,1])
        cantidad = controles[0].selectbox("AGV", [2,3,4,5], index=1, key="n_2d")
        velocidad = controles[1].selectbox("Velocidad", [1,2,5,10], format_func=lambda n:f"×{n}", key="vel_2d")
        reloj["velocidad"] = velocidad
        if controles[2].button("Iniciar", key="iniciar_2d", type="primary", disabled=resultado is not None):
            try:
                p = ParametrosSimulacion(velocidad_maxima_ms=VELOCIDAD_REFERENCIA_MS,
                    tiempo_carga_s=CARGA_PALLET_S, tiempo_descarga_s=DESCARGA_PALLET_S)
                resultado = SimuladorFlota(p).ejecutar(cantidad, simular_bateria=True, cargadores=CARGADORES)
                st.session_state.resultado_2d = resultado
                reloj.update(tiempo_s=0., marca=time.monotonic(), ejecutando=True)
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))
        if controles[3].button("Pausar", disabled=not reloj["ejecutando"], key="pausa_2d"):
            reloj["ejecutando"] = False
        if controles[4].button("Reanudar", disabled=resultado is None or reloj["ejecutando"], key="reanudar_2d"):
            reloj.update(ejecutando=True, marca=time.monotonic())
        if controles[5].button("Reiniciar", key="reset_2d"):
            st.session_state.pop("resultado_2d", None)
            reloj.update(tiempo_s=0., ejecutando=False, marca=time.monotonic())
            resultado = None
        mapa = cargar_mapa()
        if resultado is None:
            mostrar_mapa(mapa, [], None, estado_lineas_produccion(None, 0, []))
            st.caption("Cargadores confirmados: CP31, CP32, CP30 y CP29 · Rueda para acercar, arrastra para explorar.")
            return
        estado = estado_en_instante(resultado, reloj["tiempo_s"], mapa)
        st.caption(f"Tiempo simulado: {horas_minutos(estado['tiempo_s'])} · {'EN MARCHA' if reloj['ejecutando'] else 'PAUSADA / FINALIZADA'} · {resultado['numero_agv']} AGV")
        if cantidad != resultado["numero_agv"]:
            st.caption("Reinicia e inicia para aplicar otra cantidad de AGV.")
        for col,(nombre,valor) in zip(st.columns(4),[("Pallets completados",estado["completados"]),
                ("Solicitudes pendientes",len(estado["pendientes"])),("Misiones activas",len(estado["activas"])),
                ("Utilización en misiones",f"{estado['utilizacion_pct']:.0f} %")]):
            col.metric(nombre,valor)
        izquierda,derecha=st.columns([3.4,1],gap="small")
        with izquierda:
            seleccionado=st.selectbox("Ruta destacada", [a["agv"] for a in estado["flota"]], key="ruta_2d")
            estados_linea = estado_lineas_produccion(resultado, estado["tiempo_s"], estado["flota"])
            mostrar_mapa(mapa, estado["flota"], seleccionado, estados_linea)
            no_utilizables = resultado.get("cargadores_no_utilizables", [])
            if no_utilizables:
                st.caption("Sin conectividad para recarga: " + ", ".join(no_utilizables))
            else:
                st.caption("Rutas del grafo existente · Una plaza por cargador (supuesto).")
        with derecha:
            st.markdown("**Estado de la flota**")
            for a in estado["flota"]:
                st.html(tarjeta_agv(a))
        a,b=st.columns(2)
        with a:
            st.markdown("**Solicitudes pendientes**")
            tabla_operativa([{"ID": f"M-{m['numero']:03d}", "Origen":nombre_nodo(m["origen"]),"Destino":nombre_nodo(m["destino"]),
                "Prioridad":"NORMAL", "Espera":horas_minutos(estado["tiempo_s"]-m["llegada_s"])} for m in estado["pendientes"][:10]], "Sin solicitudes pendientes")
            if len(estado["pendientes"]) > 10: st.caption(f"Primeras 10 de {len(estado['pendientes'])} pendientes.")
        with b:
            st.markdown("**Misiones activas**")
            tabla_operativa([{"Misión":x["mision"],"AGV":x["agv"],"Pallet":x["pallet_asignado"],"Origen":nombre_nodo(x["origen"]),"Destino":nombre_nodo(x["destino"]),"Estado":x["estado"]}
                for x in estado["flota"] if x["mision"] != "—"], "Sin misiones activas")
        with st.expander("Explorar instante y detalle",expanded=False):
            instante=st.number_input("Instante simulado (s)",min_value=0.,max_value=float(resultado["kpis"]["tiempo_total_s"]),value=0.,key="instante_2d")
            if st.button("Ver instante y pausar",key="buscar_2d"):
                reloj.update(tiempo_s=instante,ejecutando=False,marca=time.monotonic())
                st.rerun(scope="fragment")
            st.json(next(x for x in estado["flota"] if x["agv"] == seleccionado),expanded=False)
