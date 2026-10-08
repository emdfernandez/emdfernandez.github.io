#!/usr/bin/env python3
"""Convierte la planilla de tarifas (xlsx) en tarifas.json.
Uso: python3 scripts/build_tarifas.py Peajes_Argentina.xlsx   (escribe www/tarifas.json)
Ubicación de cada cabina, en orden de prioridad:
  1. LATITUD / LONGITUD de la planilla con FUENTE COORDENADAS  -> ubic = "verificada" (radio 3 km)
  2. LATITUD / LONGITUD de la planilla sin fuente               -> ubic = "estimada"  (radio 4 o 5 km; 2 km si cuesta $10.000 o más)
  3. ubicaciones.json (estimaciones sobre la ruta, con radio en km) -> ubic = "estimada"
  4. sin ubicación: la cabina queda en el archivo pero no se suma al calcular.
Las cabinas de CABA usan siempre radio 1,5 km para no cobrar autopistas urbanas que la ruta solo roza.
Cada semana se puede volver a correr con la planilla nueva; las estimaciones ya cargadas se conservan."""
import sys, json, re, unicodedata, os
import openpyxl

def slug(s):
    s = unicodedata.normalize('NFD', str(s)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')

def coord(v, lim):
    """Convierte a número y repara valores sin la coma decimal (p. ej. -345320640182912 -> -34.5320640182912)."""
    if v is None or v == '': return None
    x = float(v)
    while abs(x) > lim: x /= 10
    return round(x, 6)

def num(v):
    if v is None or v == '': return None
    return round(float(v), 2)

src = sys.argv[1]
here = os.path.dirname(os.path.abspath(__file__))
ws = openpyxl.load_workbook(src, data_only=True)['Peajes Argentina']
notas = {r[0]: r[1] for r in openpyxl.load_workbook(src, data_only=True)['Notas'].iter_rows(min_row=2, values_only=True) if r[0]}
try: ubic = json.load(open(os.path.join(here, 'ubicaciones.json'), encoding='utf-8'))
except FileNotFoundError: ubic = {}

CABA = {'lat': -34.6037, 'lon': -58.3816}
cabinas, ids = [], set()
for r in ws.iter_rows(min_row=2, values_only=True):
    prov, nombre, ruta, auto, tele, pico, vig, fuente, xlat, xlon, xfuente, xobs = (list(r) + [None]*12)[:12]
    if not nombre: continue
    sentido = ref = None
    m = re.match(r'^(.*?)\s*-\s*(CABA → La Plata|La Plata → CABA)$', str(nombre))
    if m:
        nombre = m.group(1)
        sentido = 'ida' if m.group(2).startswith('CABA') else 'vuelta'   # ida = se aleja de CABA
        ref = CABA
    cid = slug(nombre) + '-' + slug(ruta) + ('-' + sentido if sentido else '')
    assert cid not in ids, 'id repetido: ' + cid
    ids.add(cid)
    c = {'id': cid, 'provincia': prov, 'nombre': nombre, 'ruta': ruta,
         'auto': num(auto), 'telepase': num(tele), 'pico': num(pico), 'vigencia': str(vig), 'fuente': fuente}
    if sentido: c['sentido'] = sentido; c['ref'] = ref
    u = ubic.get(cid)
    lat, lon = coord(xlat, 90), coord(xlon, 180)
    if lat is not None and lon is not None:
        c['lat'], c['lon'] = lat, lon
        if xfuente:
            c['ubic'], c['fuente_ubic'] = 'verificada', xfuente; c['radio'] = 3
        else:
            urbana = str(ruta).startswith(('Acceso', 'AU', 'Autopista'))
            c['ubic'] = 'estimada'; c['radio'] = 4 if urbana else 5
            if c['auto'] and c['auto'] >= 10000: c['radio'] = 2   # puentes y cruces caros: radio chico para no cobrarlos por error
        if prov == 'CABA': c['radio'] = 1.5
    elif u and u.get('lat') is not None:
        c['lat'], c['lon'], c['ubic'] = u['lat'], u['lon'], 'estimada'
        c['radio'] = u.get('radio', 10)
    cabinas.append(c)

out = {'actualizado': notas.get('Fecha de corte', ''), 'vehiculo': notas.get('Vehículo', ''), 'cabinas': cabinas}
destino = os.path.join(here, '..', 'www', 'tarifas.json')
json.dump(out, open(destino, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
ver = sum(1 for c in cabinas if c.get('ubic') == 'verificada'); est = sum(1 for c in cabinas if c.get('ubic') == 'estimada')
print(f'{len(cabinas)} cabinas: {ver} verificadas, {est} estimadas, {len(cabinas)-ver-est} sin ubicación')

import subprocess
subprocess.run([sys.executable, '-I', os.path.join(here, 'incrustar_tarifas.py')], check=True)
