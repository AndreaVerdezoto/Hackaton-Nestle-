from enum import Enum


class EstadoPallet(str, Enum):
    LISTO_PARA_TRASLADO = "LISTO_PARA_TRASLADO"
    ESPERANDO_RECOGIDA = "ESPERANDO_RECOGIDA"
    EN_TRANSPORTE = "EN_TRANSPORTE"
    ALMACENADO = "ALMACENADO"


class Pallet:
    #Este método es el constructor 
    def __init__(
        self,
        id_pallet,
        producto,
        lote,
        cantidad_cajas,
        peso,
        altura,
        ubicacion
    ):
        #self representa al objeto que estamos creando 
        self.id_pallet = id_pallet
        self.producto = producto
        self.lote = lote
        self.cantidad_cajas = cantidad_cajas
        self.peso = peso
        self.altura = altura
        self.ubicacion = ubicacion
        self.estado = EstadoPallet.LISTO_PARA_TRASLADO
        
    #Define como queremos que se vea el objeto cuando lo imprimamos 
    def __str__(self):
        return (
            f"Pallet {self.id_pallet} | "
            f"{self.producto} | "
            f"{self.peso} kg | "
            f"{self.estado.value}"
        )