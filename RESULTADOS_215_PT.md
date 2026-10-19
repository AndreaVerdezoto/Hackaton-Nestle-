# Resultados de referencia — meta 215 pallets

## Escenario vigente: 7 min por pallet y línea

El flujo se limita al retiro de producto terminado. La meta de Nestlé es **215 pallets efectivamente descargados por AGV en almacén durante 8 h**. No equivale a limitar la producción a 215. En el caso base, cinco líneas independientes completan **68 pallets cada una** en ocho horas: **340 pallets producidos y 340 solicitudes de retiro**.

Los demás supuestos siguen iguales: velocidad 1 m/s, aceleración/desaceleración 1 m/s², carga 30 s, descarga 30 s, factor de escala 1 m/unidad y batería activada.

| AGV | Capacidad | Almacenados en 8 h | Meta 215 | Extra entregado | Pendientes | Espera media |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 2 | AJUSTADA | 339/340 | 157,67 % | +124 | 1 | 109,20 s |
| 3 | AJUSTADA | 340/340 | 158,14 % | +125 | 0 | 43,22 s |
| 4 | AJUSTADA | 340/340 | 158,14 % | +125 | 0 | 18,94 s |
| 5 | SUFICIENTE | 340/340 | 158,14 % | +125 | 0 | 0,00 s |

**Pallet contado:** la misión de retiro debe finalizar y descargarse el pallet en almacén antes del cierre. Pallets producidos, en transporte o en espera de AGV **no se suman** como entregados.

**Clasificación de capacidad:** INSUFICIENTE si se entregan menos de 215, AJUSTADA si se logra la meta pero hubo espera o quedan pallets por almacenar, y SUFICIENTE si se logra la meta retirando todo lo producido sin esperas. Esta clasificación corresponde al escenario simulado; no significa que el sistema sea seguro para operar en fábrica sin validar congestión, microparadas y demás límites reales.

Los tiempos generales o individuales por línea pueden configurarse desde **Dimensionamiento**, y el número de solicitudes se recalcula sin afectar la meta fija.

## Escenario histórico: 11 min

La simulación anterior con 660 s/pallet y 5 líneas generaba 215 pallets (43 por línea), por lo tanto 215 misiones. Su comportamiento operacional sigue disponible mediante `tiempo_produccion_s=660`; ya **no es el valor predeterminado**.
