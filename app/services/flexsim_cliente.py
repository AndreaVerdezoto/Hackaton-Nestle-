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

    def ejecutar_mision(self, id_agv, origen, destino):
        comando = f"MISION|{id_agv}|{origen}|{destino}"

        return self.enviar_comando(comando)

    def obtener_estado(self, id_agv):
        comando = f"ESTADO|{id_agv}"

        return self.enviar_comando(comando)