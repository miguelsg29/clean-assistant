"""Ejecuta todas las pruebas (tests/test_*.py), cada una en su propio proceso.

    python tests/run.py            # todas
    python tests/run.py tuya mqtt  # solo las que contengan esas palabras

Las pruebas son scripts con `assert`: usan robots simulados (Tuya, legacy, MockRobot) y datos
inventados. No llevan capturas de usuarios ni datos de ninguna casa real.
"""
import glob
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TIMEOUT_S = 180


def main(filters):
    tests = sorted(glob.glob(os.path.join(HERE, "test_*.py")))
    if filters:
        tests = [t for t in tests if any(f in os.path.basename(t) for f in filters)]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", MQTT_HOST="")
    failed = []
    for t in tests:
        name = os.path.basename(t)
        t0 = time.time()
        try:
            p = subprocess.run([sys.executable, t], cwd=HERE, env=env, capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_S)
            ok, out = p.returncode == 0, p.stdout + p.stderr
        except subprocess.TimeoutExpired:
            ok, out = False, f"(más de {TIMEOUT_S} s)"
        print(f"{'ok   ' if ok else 'FALLA'} {name} ({time.time() - t0:.1f} s)", flush=True)
        if not ok:
            failed.append(name)
            print("\n".join("      " + line for line in out.strip().splitlines()[-25:]), flush=True)
    print(f"\n{len(tests) - len(failed)}/{len(tests)} pruebas correctas")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
