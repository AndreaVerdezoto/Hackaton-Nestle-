from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.models.pallet import Pallet


app = FastAPI(
    title="Sistema de Gestión AGV - Nestlé",
    description="Backend para la gestión de pallets, solicitudes y flota de AGV",
    version="0.1.0"
)

# Aquí guardaremos temporalmente los pallets
pallets = []


class PalletEntrada(BaseModel):
    id_pallet: str
    producto: str
    lote: str

    cantidad_cajas: int = Field(gt=0, le=60)
    peso: float = Field(gt=0, le=800)
    altura: float = Field(gt=0, le=1.60)

    ubicacion: str


@app.get("/")
def inicio():
    return {
    "sistema": "Sistema de Gestión AGV - Nestlé",
    "estado": "activo"
}


@app.post("/pallets")
def registrar_pallet(datos: PalletEntrada):

    # Evitar que se registre dos veces el mismo pallet
    for pallet_existente in pallets:
        if pallet_existente.id_pallet == datos.id_pallet:
            raise HTTPException(
                status_code=400,
                detail="Ya existe un pallet con ese ID"
            )

    # Convertimos los datos recibidos en un objeto Pallet
    nuevo_pallet = Pallet(
        id_pallet=datos.id_pallet,
        producto=datos.producto,
        lote=datos.lote,
        cantidad_cajas=datos.cantidad_cajas,
        peso=datos.peso,
        altura=datos.altura,
        ubicacion=datos.ubicacion
    )

    # Guardamos el objeto
    pallets.append(nuevo_pallet)

    return {
        "mensaje": "Pallet registrado correctamente",
        "pallet": {
            "id_pallet": nuevo_pallet.id_pallet,
            "producto": nuevo_pallet.producto,
            "lote": nuevo_pallet.lote,
            "cantidad_cajas": nuevo_pallet.cantidad_cajas,
            "peso": nuevo_pallet.peso,
            "altura": nuevo_pallet.altura,
            "ubicacion": nuevo_pallet.ubicacion,
            "estado": nuevo_pallet.estado.value
        }
    }


@app.get("/pallets")
def listar_pallets():

    resultado = []

    for pallet in pallets:
        resultado.append({
            "id_pallet": pallet.id_pallet,
            "producto": pallet.producto,
            "lote": pallet.lote,
            "cantidad_cajas": pallet.cantidad_cajas,
            "peso": pallet.peso,
            "altura": pallet.altura,
            "ubicacion": pallet.ubicacion,
            "estado": pallet.estado.value
        })

    return resultado