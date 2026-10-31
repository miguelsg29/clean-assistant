"""Backend 'robeye' para robots con plataforma RobArt «RobEye» (Rowenta X-plorer Serie 80…).

Estos robots exponen una API HTTP local y abierta en el puerto 8080 (la misma que usa la
integración ROMY de Home Assistant): `get/...` para leer (estado, mapa en polígonos, pose)
y `set/...` para mandar órdenes, que devuelven un `cmd_id`. No hay nube que suplantar:
Clean Assistant consulta al robot directamente.

`RobEyeRobot` expone la MISMA interfaz que `RealRobot`/`LegacyRobot` (`start()`,
`command(control)`, `tick()`, `.state`, `.map`, `.pose` + callbacks), así que app.py, MQTT
y la interfaz no cambian. API capturada de la web local del robot (31-oct-2026).
"""
