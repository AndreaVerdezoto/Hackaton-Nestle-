import socket


class FlexSimCliente:

    def __init__(self, host="127.0.0.1", puerto=5056):
        self.host = host
        self.puerto = puerto

    def enviar_comando(self, comando):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as cliente:

            cliente.settimeout(30)

            cliente.connect(
                (self.host, self.puerto)
            )

            cliente.sendall(
                comando.encode("utf-8")
            )

            respuesta = cliente.recv(1024)

            return respuesta.decode("utf-8").strip()

    def mover_agv(self, id_agv, destino):
        comando = f"MOVER|{id_agv}|{destino}"

        return self.enviar_comando(comando)

    def ejecutar_mision(
        self,
        id_agv,
        origen,
        destino,
        id_pallet,
        estacion_origen,
        estacion_destino
    ):
        comando = (
            f"MISION|{id_agv}|{origen}|{destino}|"
            f"{id_pallet}|{estacion_origen}|{estacion_destino}"
        )

        return self.enviar_comando(comando)

    def obtener_estado(self, id_agv):
        comando = f"ESTADO|{id_agv}"

        return self.enviar_comando(comando)

    def crear_pallet(self, id_pallet, estacion):
        for valor in (id_pallet, estacion):
            if not valor or any(c in valor for c in "|\r\n"):
                raise ValueError("ID y estación deben ser campos TCP no vacíos.")
        respuesta = self.enviar_comando(f"CREAR_PALLET|{id_pallet}|{estacion}")
        if respuesta != "OK|PALLET_CREADO":
            raise RuntimeError(f"FlexSim rechazó crear el pallet: {respuesta}")
        return respuesta
