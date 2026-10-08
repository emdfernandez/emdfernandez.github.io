#!/usr/bin/env python3
"""Revisa las fuentes oficiales de cada cabina y actualiza www/tarifas.json.

La IA (Gemini, plan gratuito) solo LEE el documento y devuelve los precios que figuran en él.
Cada precio se acepta únicamente si:
  1. la IA cita un fragmento textual del documento,
  2. ese fragmento realmente está en el texto descargado,
  3. el número aparece dentro del fragmento citado, y
  4. el cambio respecto del valor actual es razonable (entre 0,5x y 3x).
Todo lo que no cumple se informa como "rechazado" y el valor anterior se conserva.

Uso:
  GEMINI_API_KEY=... python3 scripts/actualizar_tarifas.py --tarifas www/tarifas.json --informe cambios.md
  python3 scripts/actualizar_tarifas.py --mock tests/mock.json ...   (prueba sin red ni clave)
"""
import argparse, datetime, io, json, os, re, sys, time, unicodedata
import urllib.error, urllib.request
from html.parser import HTMLParser

MODELO = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
MAX_TEXTO = 60000      # caracteres del documento que se le pasan a la IA
LOTE = 40              # cabinas por consulta
PAUSA = 7              # segundos entre consultas (el plan gratuito limita por minuto)
RATIO_MIN, RATIO_MAX = 0.5, 3.0
CAMPOS = ('auto', 'telepase', 'pico')


# ---------- lectura de documentos ----------
class _Texto(HTMLParser):
    def __init__(self):
        super().__init__(); self.partes = []; self.saltar = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'): self.saltar += 1
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript') and self.saltar: self.saltar -= 1
    def handle_data(self, data):
        if not self.saltar: self.partes.append(data)


def descargar(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; CalculadoraPeajes/1.0)'})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read(), r.headers.get('Content-Type', '')


def a_texto(url, datos, ctype):
    if datos[:4] == b'%PDF' or 'pdf' in ctype.lower() or url.lower().endswith('.pdf'):
        from pypdf import PdfReader
        lector = PdfReader(io.BytesIO(datos))
        crudo = '\n'.join((p.extract_text() or '') for p in lector.pages)
    else:
        p = _Texto(); p.feed(datos.decode('utf-8', errors='replace')); crudo = ' '.join(p.partes)
    return re.sub(r'\s+', ' ', crudo).strip()


def norm(s):
    s = unicodedata.normalize('NFD', str(s)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', s).strip()


# ---------- verificación de lo que dice la IA ----------
def variantes(valor):
    """Formas en que puede aparecer un precio en un texto argentino."""
    v = round(float(valor), 2)
    ent, dec = divmod(round(v * 100), 100)
    miles = f'{ent:,}'.replace(',', '.')
    out = {f'{miles},{dec:02d}', f'{ent},{dec:02d}', f'{ent}.{dec:02d}', f'{ent:,}.{dec:02d}'}
    if dec == 0:
        out |= {f'{miles}', f'{ent}', f'{ent:,}', f'{miles},00'}
    return out


def numero_en_cita(valor, cita):
    for forma in variantes(valor):
        if re.search(r'(?<![\d.,])' + re.escape(forma) + r'(?![\d])', cita):
            return True
    return False


def validar(cabina, campo, nuevo, cita, texto_norm):
    """Devuelve (aceptado, motivo)."""
    if nuevo is None: return False, 'sin dato'
    try: nuevo = float(nuevo)
    except (TypeError, ValueError): return False, 'valor no numérico'
    if not (0 < nuevo < 100000): return False, 'fuera de rango'
    if not cita or len(cita) < 6: return False, 'sin cita'
    if norm(cita) not in texto_norm: return False, 'la cita no está en el documento'
    if not numero_en_cita(nuevo, cita): return False, 'el número no aparece en la cita'
    viejo = cabina.get(campo)
    if viejo:
        r = nuevo / viejo
        if not (RATIO_MIN <= r <= RATIO_MAX): return False, f'cambio sospechoso ({viejo:g} → {nuevo:g})'
    return True, ''


# ---------- consulta a la IA ----------
ESQUEMA = {
    'type': 'OBJECT',
    'properties': {'cabinas': {'type': 'ARRAY', 'items': {
        'type': 'OBJECT',
        'properties': {
            'id': {'type': 'STRING'},
            'auto': {'type': 'NUMBER', 'nullable': True},
            'telepase': {'type': 'NUMBER', 'nullable': True},
            'pico': {'type': 'NUMBER', 'nullable': True},
            'cita': {'type': 'STRING', 'nullable': True},
        },
        'required': ['id'],
    }}},
    'required': ['cabinas'],
}

PROMPT = """Sos un extractor de datos. Te paso el texto de un documento oficial de tarifas de peaje de Argentina y una lista de cabinas.
Para cada cabina buscá en el texto la tarifa vigente para AUTOMÓVIL / vehículo liviano de 2 ejes (sin acoplado).
- "auto": precio general o pago manual / sin beneficio.
- "telepase": precio con TelePASE o beneficio, si el documento lo indica.
- "pico": precio de horario pico, si el documento lo indica.
- "cita": copiá TEXTUALMENTE, sin cambiar nada, un fragmento del documento (máximo 160 caracteres) donde figure el precio que devolvés.
REGLAS: devolvé solo valores que figuren de forma explícita. Si la cabina no aparece o el precio no está claro, poné null en todo. Nunca estimes ni calcules. Los números van sin símbolo ni separador de miles (1834.95).

CABINAS (id | nombre | ruta | valores actuales):
{lista}

DOCUMENTO:
{texto}
"""


def consultar_ia(cabinas, texto):
    clave = os.environ.get('GEMINI_API_KEY')
    if not clave: raise RuntimeError('falta GEMINI_API_KEY')
    lista = '\n'.join(f"{c['id']} | {c['nombre']} | {c['ruta']} | auto={c.get('auto')} telepase={c.get('telepase')} pico={c.get('pico')}" for c in cabinas)
    cuerpo = {
        'contents': [{'parts': [{'text': PROMPT.format(lista=lista, texto=texto[:MAX_TEXTO])}]}],
        'generationConfig': {'temperature': 0, 'responseMimeType': 'application/json', 'responseSchema': ESQUEMA},
    }
    req = urllib.request.Request(
        f'https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent',
        data=json.dumps(cuerpo).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'x-goog-api-key': clave})
    for intento in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                j = json.load(r)
            return json.loads(j['candidates'][0]['content']['parts'][0]['text'])
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and intento < 2: time.sleep(30 * (intento + 1)); continue
            raise
    raise RuntimeError('la IA no respondió')


# ---------- proceso principal ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tarifas', default='www/tarifas.json')
    ap.add_argument('--informe', default='cambios.md')
    ap.add_argument('--mock', help='JSON {url: {"texto": "...", "respuesta": {"cabinas": [...]}}} para probar sin red')
    args = ap.parse_args()

    datos = json.load(open(args.tarifas, encoding='utf-8'))
    cabinas = datos['cabinas']
    mock = json.load(open(args.mock, encoding='utf-8')) if args.mock else None

    por_fuente = {}
    for c in cabinas:
        if c.get('fuente', '').startswith('http'): por_fuente.setdefault(c['fuente'], []).append(c)

    aplicados, rechazados, sin_leer, sin_dato = [], [], [], []
    fuentes_ok = 0
    for url, grupo in por_fuente.items():
        try:
            if mock is not None:
                if url not in mock: sin_leer.append((url, 'no está en el mock')); continue
                texto = mock[url]['texto']
            else:
                crudo, ctype = descargar(url); texto = a_texto(url, crudo, ctype)
            if len(texto) < 200: sin_leer.append((url, 'documento vacío o sin texto legible (¿necesita JavaScript?)')); continue
        except Exception as e:
            sin_leer.append((url, f'{type(e).__name__}: {e}')); continue
        fuentes_ok += 1
        texto_norm = norm(texto)
        for i in range(0, len(grupo), LOTE):
            lote = grupo[i:i + LOTE]
            try:
                resp = mock[url]['respuesta'] if mock is not None else consultar_ia(lote, texto)
            except Exception as e:
                sin_leer.append((url, f'error de la IA: {e}')); continue
            if mock is None: time.sleep(PAUSA)
            por_id = {c['id']: c for c in lote}
            vistos = set()
            for item in resp.get('cabinas', []):
                c = por_id.get(item.get('id'))
                if not c: continue
                vistos.add(c['id'])
                hubo = False
                for campo in CAMPOS:
                    nuevo = item.get(campo)
                    if nuevo is None: continue
                    hubo = True
                    ok, motivo = validar(c, campo, nuevo, item.get('cita'), texto_norm)
                    if not ok: rechazados.append((c, campo, c.get(campo), nuevo, motivo)); continue
                    nuevo = round(float(nuevo), 2)
                    if c.get(campo) is None or abs(c[campo] - nuevo) > 0.005:
                        aplicados.append((c, campo, c.get(campo), nuevo, item.get('cita')))
                        c[campo] = nuevo
                if not hubo: sin_dato.append(c)
            sin_dato += [c for c in lote if c['id'] not in vistos]

    if aplicados:   # la fecha solo cambia si hubo cambios reales, para no abrir Pull Requests vacíos
        datos['actualizado'] = datetime.date.today().strftime('%d/%m/%Y')
    json.dump(datos, open(args.tarifas, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    # ---------- informe ----------
    L = ['## Actualización de tarifas', '',
         f'Fuentes leídas: **{fuentes_ok}** de {len(por_fuente)}. Cambios aplicados: **{len(aplicados)}**. Rechazados: **{len(rechazados)}**.', '',
         'Revisá cada cambio contra la fuente antes de aceptar este Pull Request.', '']
    if aplicados:
        L += ['### Cambios aplicados', '', '| Cabina | Ruta | Campo | Antes | Ahora | Texto de la fuente |', '|---|---|---|---|---|---|']
        L += [f"| {c['nombre']} | {c['ruta']} | {campo} | {v if v is not None else '—'} | {n} | {(cita or '').replace('|', '/')} |" for c, campo, v, n, cita in aplicados]
        L.append('')
    if rechazados:
        L += ['### Rechazados (se conservó el valor anterior)', '', '| Cabina | Ruta | Campo | Actual | Propuesto | Motivo |', '|---|---|---|---|---|---|']
        L += [f"| {c['nombre']} | {c['ruta']} | {campo} | {v if v is not None else '—'} | {n} | {m} |" for c, campo, v, n, m in rechazados]
        L.append('')
    if sin_leer:
        L += ['### Fuentes que no se pudieron leer', ''] + [f'- {u}: {m}' for u, m in sin_leer] + ['']
    if sin_dato:
        L += [f'### Cabinas sin dato en su fuente ({len(sin_dato)})', '', 'Se conservó el valor anterior: ' + ', '.join(f"{c['nombre']} ({c['ruta']})" for c in sin_dato[:60]) + (' …' if len(sin_dato) > 60 else ''), '']
    open(args.informe, 'w', encoding='utf-8').write('\n'.join(L))
    print(f'fuentes {fuentes_ok}/{len(por_fuente)} · aplicados {len(aplicados)} · rechazados {len(rechazados)} · sin dato {len(sin_dato)}')


if __name__ == '__main__':
    main()
