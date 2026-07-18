"""Configuración e identidad del robot para el servidor local (RealRobot)."""
from __future__ import annotations
import base64
import json
import os
from dataclasses import dataclass

# GUID mágico del handshake WebSocket (RFC 6455) que usa el firmware del robot.
WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def load_env(path: str = ".env"):
    """Lector simple de .env; prioridad: variable de entorno > .env > default."""
    env = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")

    def get(key, default=None):
        return os.environ.get(key, env.get(key, default))
    return get


def make_synthetic_jwt(did, factory_id) -> str:
    """JWT con estructura válida, firma FALSA y SIN caducidad. El robot no valida
    la firma (solo necesita code:0 y respuesta bien formada)."""
    def b64url(d):
        return base64.urlsafe_b64encode(d).decode().rstrip("=")
    header = {"typ": "JWT", "alg": "HS256"}
    payload = {"value": json.dumps({"data": {"FACTORY_ID": str(factory_id)},
               "clientType": "ROBOT", "id": str(did), "resetCode": 0}),
               "version": None, "scope": None, "timestamp": None}
    h = b64url(json.dumps(header, separators=(",", ":")).encode())
    p = b64url(json.dumps(payload, separators=(",", ":")).encode())
    return f"{h}.{p}.SYNTHETIC0SIGNATURE0NO0VALIDATION0NEEDED000000000000000000000"


@dataclass
class RobotConfig:
    """Identificadores de TU Conga (salen del login capturado con el MITM) y
    parámetros del servidor. Los valores por defecto son de EJEMPLO."""
    did: int = 123456
    userid: int = 654321
    sn: str = "500400000000"
    mac: str = "12:34:56:78:9A:BC"
    factory_id: str = "1003"
    project_type: str = "CECOTECCRL350-1001"
    listen_port: int = 9090
    cert_path: str = "cert.pem"
    key_path: str = "key.pem"
    auth_jwt: str = ""     # vacío -> se genera un JWT sintético
    # enlace: "local" (impersonador) o "cloud" (pasarela robot<->nube real, la app oficial funciona)
    link_mode: str = "local"
    cloud_ip: str = "43.158.121.228"          # IP real de tcp-cecotec.3irobotix.net
    cloud_host: str = "tcp-cecotec.3irobotix.net"
    cloud_port: int = 9090

    @property
    def jwt(self) -> str:
        return self.auth_jwt or make_synthetic_jwt(self.did, self.factory_id)

    @property
    def configured(self) -> bool:
        """True si hay una identidad real (no los ejemplos ni el 0 del add-on)."""
        return self.did not in (0, 123456)

    @classmethod
    def from_env(cls, path: str = ".env") -> "RobotConfig":
        e = load_env(path)
        cfg = cls(
            did=int(e("ROBOT_DID", "123456")),
            userid=int(e("ROBOT_USERID", "654321")),
            sn=e("ROBOT_SN", "500400000000"),
            mac=e("ROBOT_MAC", "12:34:56:78:9A:BC"),
            factory_id=e("FACTORY_ID", "1003"),
            project_type=e("PROJECT_TYPE", "CECOTECCRL350-1001"),
            listen_port=int(e("LISTEN_PORT", "9090")),
            cert_path=e("CERT_PATH", "cert.pem"),
            key_path=e("KEY_PATH", "key.pem"),
            auth_jwt=(e("AUTH_JWT", "") or "").strip(),
            link_mode=(e("CONGA_LINK", "local") or "local").lower(),
            cloud_ip=e("CLOUD_IP", "43.158.121.228"),
            cloud_host=e("CLOUD_HOST", "tcp-cecotec.3irobotix.net"),
            cloud_port=int(e("CLOUD_PORT", "9090")),
        )
        cfg.apply_identity(load_identity())   # identidad capturada de la nube (si existe) manda
        return cfg

    def apply_identity(self, ident: dict):
        """Aplica una identidad capturada (auto-provisión) sobre los IDs del robot."""
        if not ident:
            return
        for k in ("did", "userid"):
            if ident.get(k) is not None:
                setattr(self, k, int(ident[k]))
        for k in ("sn", "mac", "factory_id", "project_type"):
            if ident.get(k):
                setattr(self, k, str(ident[k]))


# Identidad capturada de la nube (auto-provisión). Se guarda en DATA_DIR (en el
# add-on, /data) para que persista y NO haya que volver a la nube en cada arranque.
IDENTITY_PATH = os.path.join(os.environ.get("DATA_DIR", "."), "identity.json")


def load_identity(path: str = IDENTITY_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_identity(ident: dict, path: str = IDENTITY_PATH):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ident, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
