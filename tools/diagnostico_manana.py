"""Diagnóstico offline de clases reales; no modifica parámetros ni código del proyecto.

Uso: .venv-agv/Scripts/python.exe -B tools/diagnostico_manana.py
Ocho corridas a la referencia confirmada 1 m/s; CSV en la raíz del proyecto.
Los campos vacíos representan datos no disponibles, nunca ceros inferidos.
"""
from __future__ import annotations

import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.bateria import CARGADORES, VELOCIDAD_REFERENCIA_MS
from app.services.simulador_flota import ParametrosSimulacion, SimuladorFlota
from app.services.estado_visual import estado_en_instante


def contexto_error(exc):
    """Lee los frames de la excepción; no parchea ni vuelve a ejecutar el motor."""
    contexto = {}
    tb = exc.__traceback__
    while tb:
        frame = tb.tb_frame
        loc = frame.f_locals
        if frame.f_code.co_name == 'ejecutar':
            contexto.update(reloj_s=loc.get('reloj'), finalizados=loc.get('finalizados'),
                            pendientes=loc.get('pendientes'))
        if frame.f_code.co_name == 'recargar':
            b, t, agv = loc['self'], loc['t'], loc['agv']
            opciones = []
            for nodo, libre in b.libres.items():
                try:
                    viaje = b.trayecto(b.vehiculos[agv]['posicion'], nodo)
                    llegada = t + viaje['tiempo_s']
                    inicio = max(llegada, libre)
                    opciones.append(dict(nodo=nodo, libre_s=libre, llegada_s=llegada,
                        conexion_s=inicio, espera_s=inicio-llegada,
                        bateria_conexion_pct=b.nivel(agv, t)-b.modelo.consumo(inicio-t)))
                except ValueError as error:
                    opciones.append(dict(nodo=nodo, error=str(error)))
            contexto.update(agv_fallido=agv, tiempo_s=t, cargadores_libres_desde=b.libres,
                vehiculos=b.vehiculos, baterias_pct={a:b.nivel(a,t) for a in b.vehiculos},
                opciones_cargador=opciones, recargas_parciales=b.recargas)
        tb = tb.tb_next
    return contexto


def identidad_y_tiempos(r):
    movimientos = r['movimientos']
    errores, muestras = [], []
    elegidos = {1, 2, 3, 211, 215}
    for prod in r['producciones']:
        ciclo = prod['id_ciclo']
        asociados = [m for m in movimientos if m['id_ciclo'] == ciclo]
        s = [m for m in asociados if m['tipo'] == 'suministro']
        pt = [m for m in asociados if m['tipo'] == 'producto_terminado']
        d = next((d for d in r['demanda'] if d['id_ciclo'] == ciclo), None)
        correcto = (len(s) == len(pt) == 1 and d is not None
            and d['id_pallet'] == s[0]['id_pallet'] == prod['id_pallet'] == pt[0]['id_pallet']
            and s[0]['fin_s'] <= prod['inicio_s'] < prod['fin_s'] == pt[0]['llegada_s']
            and pt[0]['destino'] == 'ControlPoint7'
            and prod['movimiento_suministro'] == s[0]['numero']
            and prod['movimiento_producto_terminado'] == pt[0]['numero'])
        if not correcto:
            errores.append(ciclo)
        if ciclo in elegidos and s and pt:
            muestras.append(dict(id_ciclo=ciclo, id_pallet=prod['id_pallet'], linea=prod['linea'],
                necesidad_s=s[0]['llegada_s'], suministro_inicio_s=s[0]['inicio_s'],
                suministro_fin_s=s[0]['fin_s'], produccion_inicio_s=prod['inicio_s'],
                produccion_fin_s=prod['fin_s'], retiro_llegada_s=pt[0]['llegada_s'],
                retiro_inicio_s=pt[0]['inicio_s'], almacen_s=pt[0]['fin_s'],
                agv_suministro=s[0]['agv'], agv_retiro=pt[0]['agv']))
    return dict(ciclos_verificados=len(r['producciones']), errores=errores, muestras=muestras)


def ejecutar_caso(n, bateria):
    p = ParametrosSimulacion(velocidad_maxima_ms=VELOCIDAD_REFERENCIA_MS)
    fila = dict(agv=n, bateria=bateria, velocidad_ms=p.velocidad_maxima_ms,
                pallets_requeridos=p.pallets_terminados, movimientos_totales=p.movimientos,
                suministros_requeridos=p.suministros_requeridos, parametros_json=json.dumps(asdict(p)),
                error='', contexto_error_json='')
    try:
        r = SimuladorFlota(p).ejecutar(n, simular_bateria=bateria, cargadores=CARGADORES)
        k = r['kpis']
        campos = dict(pallets_8h='pallets_terminados_turno', suministros_8h='suministros_turno',
            movimientos_totales='movimientos_logisticos_totales', movimientos_8h='completados_turno',
            backlog_corte_movimientos='backlog_corte', backlog_maximo='backlog_maximo',
            utilizacion_pct='utilizacion_media_pct', espera_media_s='espera_media_s',
            distancia_total_m='distancia_total_m', tiempo_total_s='tiempo_total_s')
        fila.update({destino:k.get(origen) for destino,origen in campos.items()})
        fila.update(suministros=sum(m['tipo']=='suministro' for m in r['movimientos']),
            retiros=sum(m['tipo']=='producto_terminado' for m in r['movimientos']),
            movimientos_completados_final=len(r['movimientos']),
            cantidad_recargas=sum(map(len,r['recargas'].values())) if 'recargas' in r else None,
            identidad_json=json.dumps(identidad_y_tiempos(r), ensure_ascii=False),
            kpis_json=json.dumps(k, ensure_ascii=False),
            recargas_json=json.dumps(r.get('recargas'), ensure_ascii=False),
            bateria_visual_8h_json=json.dumps({a['agv']:a['bateria'] for a in
                estado_en_instante(r, p.duracion_turno_s)['flota']}))
    except Exception as exc:
        fila['error'] = traceback.format_exc()
        fila['contexto_error_json'] = json.dumps(contexto_error(exc), ensure_ascii=False)
    return fila


def main():
    filas = []
    for bateria in (False, True):
        for n in (2,3,4,5):
            fila = ejecutar_caso(n, bateria)
            filas.append(fila)
            print(f"{n} AGV bateria={bateria}: " +
                  (fila['error'].splitlines()[-1] if fila['error'] else
                   f"{fila['pallets_8h']} pallets/8h; fin={fila['tiempo_total_s']:.3f}s"))
    commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    grafo = hashlib.sha256((ROOT/'data/red_agv_grafo_actualizado.json').read_bytes()).hexdigest()
    for fila in filas:
        fila.update(commit=commit, grafo_sha256=grafo)
    campos = list(dict.fromkeys(c for fila in filas for c in fila))
    with (ROOT/'resultados_diagnostico.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas)
    print('CSV: resultados_diagnostico.csv. Sin batería: recargas vacío = no modeladas.')


if __name__ == '__main__':
    main()
