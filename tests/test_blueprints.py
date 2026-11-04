"""Blueprints (blueprints/automation/...) y frases de Assist (assist/): YAML válido, cada !input
declarado y usado, y los campos que pide Home Assistant."""
import glob
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor("!input", lambda loader, node: ("!input", loader.construct_scalar(node)))


def inputs_used(x, acc):
    if isinstance(x, tuple) and x[0] == "!input":
        acc.add(x[1])
    elif isinstance(x, dict):
        for v in x.values():
            inputs_used(v, acc)
    elif isinstance(x, list):
        for v in x:
            inputs_used(v, acc)
    return acc


bps = sorted(glob.glob(os.path.join(ROOT, "blueprints", "automation", "clean_assistant", "*.yaml")))
assert len(bps) >= 3, bps
for path in bps:
    name = os.path.basename(path)
    d = yaml.load(open(path, encoding="utf-8"), Loader=Loader)
    bp = d["blueprint"]
    assert bp["domain"] == "automation" and bp["name"] and bp["description"], name
    assert bp["source_url"].endswith("/blueprints/automation/clean_assistant/" + name), name
    declared = set(bp["input"])
    used = inputs_used({k: v for k, v in d.items() if k != "blueprint"}, set())
    assert declared == used, (name, "sin usar", declared - used, "sin declarar", used - declared)
    assert d.get("triggers") and d.get("actions"), name
    print("ok", name)

for path in glob.glob(os.path.join(ROOT, "assist", "custom_sentences", "*", "*.yaml")):
    d = yaml.safe_load(open(path, encoding="utf-8"))
    lang = os.path.basename(os.path.dirname(path))
    assert d["language"] == lang and d["intents"]["CleanAssistantRoom"]["data"][0]["sentences"], path
    assert all("{room}" in s for s in d["intents"]["CleanAssistantRoom"]["data"][0]["sentences"]), path
    assert d["lists"]["room"]["wildcard"] is True, path
script = yaml.safe_load(open(os.path.join(ROOT, "assist", "intent_script.yaml"), encoding="utf-8"))
assert "CleanAssistantRoom" in script["intent_script"]
print("ok assist")
