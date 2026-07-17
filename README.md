# Clean Assistant

Aplicación **local y sin nube** para gestionar el robot aspirador **Cecotec Conga
8090 Ultra**: mapa, limpieza por habitaciones, zonas, horarios y todos los ajustes,
con una interfaz web propia y bonita. En la línea de Valetudo/Congatudo, pero para
la generación 8000 (que usa TLS + WebSocket + JSON + Protobuf, no soportada por
aquellos proyectos).

> Se apoya en la ingeniería inversa del repo de documentación:
> [conga_8090_mqtt_bridge](https://github.com/miguelsg29/conga_8090_mqtt_bridge).

## Estado: v0.1 — base funcional 🚧

Esta versión ya **arranca y se ve**, con un **robot simulado** para poder
desarrollar la interfaz sin un Conga real:

- ✅ `conga_core`: constructores de todos los comandos confirmados, modelo de estado
  y mapa (de ejemplo).
- ✅ Backend **FastAPI**: API REST + WebSocket en vivo + sirve el frontend.
- ✅ Frontend cableado en vivo: mapa, selección de habitaciones, dock de control
  (iniciar/pausar/base/localizar), modos, succión/agua/mopa, y ajustes (voz, no
  molestar, OTA, vaciar base…).
- ⬜ **Robot real** (servidor TLS+WS que suplanta la nube) — misma interfaz que el mock.
- ⬜ **Mapa real** (decodificador zlib+Protobuf del robot).
- ⬜ Edición de **zonas** dibujando en el mapa; editor visual de **horarios**.
- ⬜ Puente **MQTT** opcional para Home Assistant.

## Arquitectura

```
   Conga 8090
       │  (DNS: tcp-cecotec → este servidor)
       ▼
┌──────────────────────────────────────────────┐
│           Clean Assistant (backend)            │
│   conga_core   → protocolo + estado + mapa     │
│   backend/app  → FastAPI: REST + WebSocket     │
│                  sirve el frontend estático    │
└───────────────────────┬────────────────────────┘
                        ▼
              Navegador / móvil (interfaz web)
```

En v0.1, `backend/app.py` usa `MockRobot`. El robot real implementará la misma
interfaz (`.state`, `command(control)`, `tick()`) y se enchufará en el mismo sitio.

## Puesta en marcha

```bash
pip install -r requirements.txt
uvicorn backend.app:app --reload --port 8000
```

Abre **http://localhost:8000**. Verás la interfaz con el robot simulado: pulsa
*Iniciar* y observa cómo cambia el estado en vivo (por WebSocket).

## Estructura

```
clean-assistant/
├── conga_core/          # núcleo del protocolo (fuente de la verdad, compartible)
│   ├── commands.py      # constructores de comandos (set_mode, set_preference, …)
│   ├── state.py         # RobotState desde report_data
│   └── map.py           # mapa estructurado (de ejemplo; luego el real)
├── backend/
│   ├── app.py           # FastAPI: REST + WebSocket + estáticos
│   ├── mock.py          # robot simulado
│   └── static/          # frontend (index.html)
└── requirements.txt
```

## Hoja de ruta

1. **Robot real**: portar el servidor TLS+WebSocket (del puente) como `RealRobot`.
2. **Mapa real**: portar el decodificador (`decodificar_mapa.py`) → datos en vivo.
3. **Zonas**: dibujar prohibidas / sin fregona / de limpieza sobre el mapa
   (transformación rejilla↔metros, con los datos ya capturados para calibrar).
4. **Horarios** visuales (`setOrder6090`).
5. **MQTT** opcional para Home Assistant.
6. Empaquetado (Docker / add-on de HA con ingress).
