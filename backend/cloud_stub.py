"""Servidor local que suplanta los servicios AUXILIARES de la nube de Cecotec.

Con esto, Clean Assistant hace al robot INDEPENDIENTE de la nube: aunque Cecotec apague sus
servidores, el robot sigue funcionando. Verificado por ingeniería inversa del Conga 8090.

- OTA (puerto 8001, HTTPS): el robot pregunta al arrancar "¿hay firmware nuevo y DÓNDE están
  los servicios?". Respondemos "sin actualización" + el DIRECTORIO (targetUrls) apuntando al
  control LOCAL. Es la pieza CLAVE: sin esta respuesta el robot no sabe a dónde conectar y se
  queda en bucle de reconexión. Así nunca depende de la nube ni descarga firmware.
- Historial (8006 HTTP, 8002 HTTPS): el robot sube informes de cada limpieza
  (PUT /sweeper-report/robot/sweeping_img|data). Los aceptamos (para que no reintente) y los
  pasamos al historial de Clean Assistant, para tener el histórico sin nube.

Requiere redirigir por DNS (AdGuard/Pi-hole) estos dominios a este servidor:
  tcp-cecotec / web-eu / cecotec-ota / eu-ota / web-cecotec (.3irobotix.net)
  cecotec.das / cecotec-das / eu.das / eu-log (das/log NO son necesarios).
"""
from __future__ import annotations
import socket
import ssl
import threading
from urllib.parse import urlparse, parse_qs

# El directorio devuelto apunta al hostname del control; el DNS lo resuelve a ESTE servidor,
# así el robot conecta al control local (9090) en vez de a la nube.
CONTROL_HOST = "tcp-cecotec.3irobotix.net"
PORTS = (8001, 8002, 8006)


def _parse_report(path: str) -> dict:
    """Extrae los datos de un informe de limpieza de la query del PUT /sweeper-report/..."""
    q = parse_qs(urlparse(path).query)

    def gi(k, d=0):
        try:
            return int(q.get(k, [d])[0])
        except (TypeError, ValueError):
            return d

    return {"taskId": gi("taskId"), "beginTime": gi("beginTime"), "endTime": gi("endTime"),
            "cleanTime": gi("cleanTime"), "cleanType": gi("cleanType"),
            "totalArea": gi("totalArea"), "waterCtrl": gi("waterCtrl"),
            "mapId": gi("mapId"), "taskStatus": gi("taskStatus"),
            "repeatClean": gi("repeatClean"),
            "is_img": "sweeping_img" in path}


class LocalCloud:
    """Suplanta OTA + subida de informes. `on_report(dict)` se llama por cada informe."""

    def __init__(self, cert_path, key_path, on_report=None, logger=print):
        self.cert_path = cert_path
        self.key_path = key_path
        self.on_report = on_report
        self.log = logger

    def start(self):
        for p in PORTS:
            threading.Thread(target=self._serve, args=(p,), daemon=True).start()

    def _serve(self, port):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            s.listen(20)
        except Exception as e:
            self.log(f"[cloud-local] no pude escuchar en {port}: {e}")
            return
        self.log(f"[cloud-local] escuchando en {port} (OTA/historial local)")
        while True:
            try:
                c, _ = s.accept()
                threading.Thread(target=self._handle, args=(c,), daemon=True).start()
            except Exception:
                pass

    def _handle(self, conn):
        try:
            conn.settimeout(15)
            # detecta TLS (0x16) sin consumir el byte; envuelve si hace falta (8001/8002 = HTTPS)
            try:
                peek = conn.recv(1, socket.MSG_PEEK)
            except Exception:
                peek = b""
            if peek[:1] == b"\x16":
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.load_cert_chain(self.cert_path, self.key_path)
                try:
                    ctx.set_ciphers("ALL:@SECLEVEL=0")
                except Exception:
                    pass
                conn = ctx.wrap_socket(conn, server_side=True)
            data = conn.recv(65536)
            if not data:
                return
            path = ""
            try:
                path = data.split(b"\r\n", 1)[0].split(b" ")[1].decode("latin1")
            except Exception:
                pass
            if "/upgrade/try_upgrade" in path:            # OTA: sin update + directorio local
                body = ('{"code":0,"result":{"targetUrls":['
                        f'"wss://{CONTROL_HOST}:9090",'
                        '"https://web-cecotec.3irobotix.net:8002",'
                        '"http://web-eu.3irobotix.net:8006"]}}').encode()
            else:
                if "/sweeper-report/" in path and self.on_report:
                    try:
                        self.on_report(_parse_report(path))
                    except Exception:
                        pass
                body = b'{"code":0,"result":true}'
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json;charset=UTF-8\r\n"
                         b"Content-Length: " + str(len(body)).encode()
                         + b"\r\nConnection: close\r\n\r\n" + body)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
