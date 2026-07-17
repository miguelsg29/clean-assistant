"""Robot simulado — permite desarrollar y ver Clean Assistant sin un Conga real.

Implementa la misma interfaz que tendrá el robot real (`command()` + `tick()` +
`.state`), así que el backend no distingue entre mock y robot físico.
"""
from __future__ import annotations
from conga_core.state import RobotState


class MockRobot:
    def __init__(self):
        self.state = RobotState(
            online=True, state="docked", battery=99, charging=True,
            map_head_id=1700000000, map_name="Interior",
            quiet={"is_open": 1, "begin_time": 1350, "end_time": 420},   # 22:30-07:00
            voice={"voiceMode": 1, "volume": 7},
            consumables={"main_brush": 74, "side_brush": 68, "filter": 22, "dishcloth": 81},
            auto_upgrade=0,
        )
        self.on_update = None      # interfaz común con RealRobot (sin uso en el mock)
        self.on_map = None
        self.map = None            # el mock no tiene mapa real -> se usa sample_map()

    def start(self):
        pass                       # el mock no arranca ningún servidor

    # --- recibe el objeto `control` ya construido y simula su efecto ---
    def command(self, control: dict) -> dict:
        c = control.get("control")
        st = self.state
        if c == "set_mode":
            t, v = control.get("type"), control.get("value")
            if v == 4:
                pass                       # seleccionar modo, no cambia estado
            elif (t, v) == (0, 1) or (t, v) == (2, 1):
                self._go("cleaning")
            elif (t, v) == (2, 2):
                self._go("paused")
            elif (t, v) == (3, 1):
                self._go("returning")
            elif (t, v) == (3, 0):
                self._go("cleaning")
        elif c == "setRoomClean":
            self._go("cleaning")
        elif c == "set_quiet":
            q = (control.get("quiet_list") or [{}])[0]
            st.quiet = {k: q.get(k) for k in ("is_open", "begin_time", "end_time")}
        elif c == "set_voice":
            st.voice = {"voiceMode": control.get("voiceMode"), "volume": control.get("volume")}
        elif c == "set_upgrade_config":
            st.auto_upgrade = control.get("auto_upgrade")
        # set_preference, set_dust_action, set_virwall, set_area, setOrder6090...
        # se aceptan (result:0) sin efecto visible en el mock.
        return {"result": 0}

    def _go(self, s: str):
        self.state.state = s
        self.state.charging = (s == "docked")

    # --- avance del tiempo (lo llama el backend cada par de segundos) ---
    def tick(self) -> RobotState:
        st = self.state
        if st.state == "cleaning":
            st.charging = False
            if st.battery:
                st.battery = max(0, st.battery - 1)
            st.area = round((st.area or 0) + 0.6, 1)
            st.clean_time = (st.clean_time or 0) + 1
            if st.battery == 0:
                self._go("returning")
        elif st.state == "returning":
            self._go("docked")
        elif st.state == "docked":
            st.charging = True
            if st.battery is not None and st.battery < 100:
                st.battery += 1
            st.area = None
            st.clean_time = None
        return st
