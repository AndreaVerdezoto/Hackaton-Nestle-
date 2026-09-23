"""Vista 2D ligera: reproduce estados del simulador, sin lógica de asignación."""
import html
import time
import streamlit as st
from urllib.parse import quote

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
    return {"ControlPoint7": "Almacén / Pallet Transit 4", "ControlPoint8": "Pallet Transit 3",
            "ControlPoint11": "Pallet Transit 2", "ControlPoint13": "Pallet Transit 1",
            "ControlPoint24": "Cookies 1", "ControlPoint25": "Cookies 2", "ControlPoint26": "Cookies 3",
            "ControlPoint18": "Chocolate", "ControlPoint15": "Wafer",
            **{n: f"Cargador CP{n.removeprefix('ControlPoint')}" for n in CARGADORES}}.get(nodo, nodo)


def mapa_svg(mapa, flota, seleccionado):
    nodos = {n["id"]: (n["x"], n["y"]) for n in mapa["nodos"]}
    xs, ys = zip(*nodos.values())
    escala = min(750/(max(xs)-min(xs)), 480/(max(ys)-min(ys)))
    def xy(pos):
        return (55+(pos[0]-min(xs))*escala, 535-(pos[1]-min(ys))*escala)
    def linea(a,b,color,ancho):
        x,y=xy(a);u,v=xy(b)
        return f'<line x1="{x}" y1="{y}" x2="{u}" y2="{v}" stroke="{color}" stroke-width="{ancho}"/>'
    partes=['<style>html,body{margin:0;background:#101b2a;overflow:hidden}</style><svg viewBox="0 0 870 590" width="100%" height="570" role="img" aria-label="Mapa AGV 2D" xmlns="http://www.w3.org/2000/svg"><rect width="870" height="590" rx="16" fill="#101b2a"/>']
    for e in mapa["aristas"]:
        partes.append(linea(nodos[e["origen"]],nodos[e["destino"]],"#34455b",1.4))
    for a in flota:
        if a["agv"] == seleccionado:
            for origen,destino in zip(a["ruta"],a["ruta"][1:]):
                partes.append(linea(nodos[origen],nodos[destino],"#49c6e5",3))
    for nodo,pos in nodos.items():
        x,y=xy(pos); label=nombre_nodo(nodo)
        partes.append(f'<circle cx="{x}" cy="{y}" r="2" fill="#64748b"><title>{html.escape(nodo)}</title></circle>')
        if label != nodo:
            color="#f2c66d" if nodo in CARGADORES else "#a7c9c9"
            if nodo == "ControlPoint30": label += " · sin salida"
            partes.append(f'<rect x="{x-4}" y="{y-4}" width="8" height="8" fill="{color}"/><text x="{x+7}" y="{y-7}" font-size="10" fill="{color}">{html.escape(label)}</text>')
    for i,a in enumerate(flota):
        x,y=xy(a["posicion"])
        partes.append(f'<rect x="{x-6}" y="{y-4}" rx="2" width="12" height="8" fill="#4cdeba" stroke="#efffff"/>')
        if a["pallet"] != "—":
            partes.append(f'<circle cx="{x}" cy="{y}" r="2.5" fill="#ffcc66"/>')
        partes.append(f'<text x="{x+8}" y="{y+12+i*9}" font-size="10" fill="#ffffff">{html.escape(a["agv"])}</text>')
    partes.append('</svg>')
    return ''.join(partes)


@st.fragment(run_every=0.5)
def mostrar_2d():
    if st.session_state.get("modo_principal") != "Simulación 2D":
        return
    st.subheader("Simulación 2D · producto terminado")
    st.caption("215 pallets · velocidad 1 m/s · batería temporal 8 h · carga completa 3 h · reserva del prototipo 20 %. "
               "Python calcula la simulación; el mapa reproduce su estado con reloj simulado.")
    resultado = st.session_state.get("resultado_2d")
    reloj = st.session_state.setdefault("reloj_2d", {"tiempo_s": 0., "marca": time.monotonic(), "ejecutando": False, "velocidad": 1})
    if resultado:
        avanzar_reloj(reloj, time.monotonic(), resultado["kpis"]["tiempo_total_s"])
    controles = st.columns([1,1,1,1,1,1])
    cantidad = controles[0].selectbox("AGV", [2,3,4,5], index=1, key="n_2d")
    velocidad = controles[1].selectbox("Velocidad", [1,2,5,10], format_func=lambda n:f"×{n}", key="vel_2d")
    reloj["velocidad"] = velocidad
    if controles[2].button("Iniciar", key="iniciar_2d", disabled=resultado is not None):
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
        st.iframe("data:text/html;charset=utf-8," + quote(mapa_svg(mapa, [], None)), height=580)
        st.caption("Cargadores confirmados: CP31, CP32, CP30 y CP29. CP30 no tiene salida hacia almacén en el grafo actual.")
        return
    estado = estado_en_instante(resultado, reloj["tiempo_s"], mapa)
    st.caption(f"Tiempo simulado: {horas_minutos(estado['tiempo_s'])} · {'EN MARCHA' if reloj['ejecutando'] else 'PAUSADA / FINALIZADA'} · {resultado['numero_agv']} AGV")
    if cantidad != resultado["numero_agv"]:
        st.caption("Reinicia e inicia para aplicar otra cantidad de AGV.")
    for col,(nombre,valor) in zip(st.columns(4),[("Pallets completados",estado["completados"]),
            ("Solicitudes pendientes",len(estado["pendientes"])),("Misiones activas",len(estado["activas"])),
            ("Utilización en misiones",f"{estado['utilizacion_pct']:.0f} %")]):
        col.metric(nombre,valor)
    izquierda,derecha=st.columns([7,3])
    with izquierda:
        seleccionado=st.selectbox("Ruta destacada", [a["agv"] for a in estado["flota"]], key="ruta_2d")
        st.iframe("data:text/html;charset=utf-8," + quote(mapa_svg(mapa,estado["flota"],seleccionado)), height=580)
        st.caption("CP30 no utilizable: falta una ruta de salida. Se emplean CP31, CP32 y CP29; una plaza por cargador (supuesto).")
    with derecha:
        st.markdown("**Estado de la flota**")
        for a in estado["flota"]:
            with st.container(border=True):
                st.markdown(f"**{a['agv']} · {a['bateria']:.0f} %**")
                st.caption(a["estado"])
                st.write(f"Uso restante hasta reserva: **{horas_minutos(a['uso_restante_s'])}**")
                if a["carga_restante_s"] is not None:
                    st.write(f"Carga completa en: **{horas_minutos(a['carga_restante_s'])}**")
                st.caption(f"Misión: {a['mision']} · Destino: {nombre_nodo(a['destino'])} · Pallet: {a['pallet']}")
    a,b=st.columns(2)
    with a:
        st.markdown("**Solicitudes pendientes**")
        st.dataframe([{"ID": f"M-{m['numero']:03d}", "Origen":nombre_nodo(m["origen"]),"Destino":nombre_nodo(m["destino"]),
            "Prioridad":"NORMAL", "Espera":horas_minutos(estado["tiempo_s"]-m["llegada_s"])} for m in estado["pendientes"][:10]],height=200,hide_index=True)
        if len(estado["pendientes"]) > 10: st.caption(f"Primeras 10 de {len(estado['pendientes'])} pendientes.")
    with b:
        st.markdown("**Misiones activas**")
        st.dataframe([{"Misión":x["mision"],"AGV":x["agv"],"Pallet":x["pallet_asignado"],"Origen":nombre_nodo(x["origen"]),"Destino":nombre_nodo(x["destino"]),"Estado":x["estado"]}
            for x in estado["flota"] if x["mision"] != "—"],height=200,hide_index=True)
    with st.expander("Explorar instante y detalle",expanded=False):
        instante=st.number_input("Instante simulado (s)",min_value=0.,max_value=float(resultado["kpis"]["tiempo_total_s"]),value=0.,key="instante_2d")
        if st.button("Ver instante y pausar",key="buscar_2d"):
            reloj.update(tiempo_s=instante,ejecutando=False,marca=time.monotonic())
            st.rerun(scope="fragment")
        st.json(next(x for x in estado["flota"] if x["agv"] == seleccionado),expanded=False)
