# -*- coding: utf-8 -*-
"""Valida que cada entrada del diccionario STR es un objeto JS {ident:"...",...} bien formado
   y que todas tienen los 8 idiomas además del español. Parser consciente de \\\" y \\\\."""
import io, os, sys
PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "static", "index.html")
LANGS_EXPECT = {"en","pt","fr","pl","de","it","nl","ca"}

with io.open(PATH, encoding="utf-8") as f:
    lines = f.read().split("\n")
start = next(i for i,l in enumerate(lines) if l.strip()=="var STR={")
end   = next(i for i,l in enumerate(lines) if l.strip()=="};" and i>start)

def parse_obj(s, i):
    """s[i]=='{'. Devuelve (dict_de_claves, indice_tras_'}')."""
    assert s[i]=='{'; i+=1
    keys={}
    n=len(s)
    while True:
        # saltar espacios
        while i<n and s[i] in ' \t': i+=1
        if i<n and s[i]=='}':
            return keys, i+1
        # leer identificador
        j=i
        while i<n and (s[i].isalnum() or s[i]=='_'): i+=1
        ident=s[j:i]
        if not ident: raise ValueError("ident vacio en pos %d"%i)
        if i>=n or s[i]!=':': raise ValueError("falta ':' tras %r"%ident)
        i+=1
        while i<n and s[i] in ' \t': i+=1
        if i>=n or s[i]!='"': raise ValueError("falta '\"' de valor tras %r"%ident)
        i+=1
        # leer string con escapes
        while i<n:
            c=s[i]
            if c=='\\': i+=2; continue
            if c=='"': break
            i+=1
        if i>=n: raise ValueError("string sin cerrar tras %r"%ident)
        i+=1  # tras la comilla de cierre
        keys[ident]=True
        while i<n and s[i] in ' \t': i+=1
        if i<n and s[i]==',': i+=1; continue
        if i<n and s[i]=='}': return keys, i+1
        raise ValueError("esperaba ',' o '}' tras %r (pos %d, char %r)"%(ident,i,s[i:i+1]))

errors=0; checked=0
for idx in range(start+1, end):
    line=lines[idx]
    st=line.lstrip()
    if not st.startswith('"') or '":{' not in line: continue
    obj_start=line.index('":{')+2  # posicion del '{'
    try:
        keys,after=parse_obj(line, obj_start)
    except Exception as e:
        errors+=1; print("LINEA %d ERROR: %s"%(idx+1, e)); print("   ", line[:120]); continue
    checked+=1
    faltan=LANGS_EXPECT-set(keys)
    if faltan:
        errors+=1; print("LINEA %d faltan idiomas %s"%(idx+1, faltan))
    # tras el objeto solo puede haber ',' o fin de linea
    rest=line[after:].strip()
    if rest not in ("",","):
        errors+=1; print("LINEA %d resto inesperado tras objeto: %r"%(idx+1, rest))

print("\nentradas validadas:", checked, "| errores:", errors)
sys.exit(1 if errors else 0)
