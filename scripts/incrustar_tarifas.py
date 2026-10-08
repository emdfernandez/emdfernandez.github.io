#!/usr/bin/env python3
"""Copia www/tarifas.json dentro de www/index.html (etiqueta "tarifas-embebido").
Sirve como último recurso cuando la app se abre como archivo suelto, donde el navegador no deja leer tarifas.json.
Uso: python3 scripts/incrustar_tarifas.py"""
import json, os, re
aqui = os.path.dirname(os.path.abspath(__file__))
www = os.path.join(aqui, '..', 'www')
datos = json.load(open(os.path.join(www, 'tarifas.json'), encoding='utf-8'))
texto = json.dumps(datos, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
ruta = os.path.join(www, 'index.html')
html = open(ruta, encoding='utf-8').read()
patron = re.compile(r'(<script id="tarifas-embebido" type="application/json">).*?(</script>)', re.S)
assert patron.search(html), 'no encontré la etiqueta tarifas-embebido en index.html'
html = patron.sub(lambda m: m.group(1) + texto + m.group(2), html, count=1)
open(ruta, 'w', encoding='utf-8').write(html)
print(f'incrustadas {len(datos["cabinas"])} cabinas ({len(texto)//1024} KB) en index.html')
