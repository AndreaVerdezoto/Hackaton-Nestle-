from enum import Enum


class EstadoPallet(str, Enum):
    LISTO_PARA_TRASLADO = "LISTO_PARA_TRASLADO"
    ESPERANDO_RECOGIDA = "ESPERANDO_RECOGIDA"
    EN_TRANSPORTE = "EN_TRANSPORTE"
    ALMACENADO = "ALMACENADO"


class Pallet:
    """Representa el pallet físico que viaja entre las áreas de la planta."""

    def __init__(
        self,
        id_pallet,
        producto,
        lote,
        cantidad_cajas,
        peso,
        altura,
        ubicacion,
        limite_cajas=None,
    ):
        self.id_pallet = id_pallet
        self.producto = producto
        self.lote = lote
        self.cantidad_cajas = cantidad_cajas
        self.peso = peso
        self.altura = altura
        self.ubicacion = ubicacion
        self.limite_cajas = limite_cajas
        self.estado = EstadoPallet.LISTO_PARA_TRASLADO

    @property
    def esta_completo(self):
        """Indica si el conteo alcanzó el límite configurado para el pallet."""
        return (
            self.limite_cajas is not None
            and self.cantidad_cajas is not None
            and self.cantidad_cajas >= self.limite_cajas
        )

    def registrar_cajas(self, cantidad=1):
        """Actualiza el conteo; el origen del dato podrá ser un sensor en el futuro."""
        if type(cantidad) is not int or cantidad < 1:
            raise ValueError("La cantidad de cajas debe ser un entero positivo.")
        if self.cantidad_cajas is None:
            self.cantidad_cajas = 0
        self.cantidad_cajas += cantidad
        return self.esta_completo

    def mover_a(self, ubicacion):
        """Actualiza la ubicación lógica del mismo pallet físico."""
        self.ubicacion = ubicacion

    def __str__(self):
        return (
            f"Pallet {self.id_pallet} | "
            f"{self.producto} | "
            f"{self.peso} kg | "
            f"{self.estado.value}"
        )
