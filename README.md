# Calculadora de Peajes

App para calcular el peaje de un viaje en Argentina. Es una página web (carpeta `www`) que se empaqueta como APK con Capacitor. Las tarifas viven en `www/tarifas.json` y se actualizan una vez por semana con ayuda de IA.

## Qué hay en la carpeta

| Archivo | Para qué sirve |
|---|---|
| `www/index.html` | La app completa |
| `www/tarifas.json` | Tarifas y ubicación de cada cabina |
| `scripts/build_tarifas.py` | Convierte tu Excel de tarifas en `tarifas.json` |
| `scripts/ubicaciones.json` | Ubicaciones estimadas de respaldo para cabinas que el Excel no ubique |
| `scripts/actualizar_tarifas.py` | Revisa las fuentes oficiales con IA y propone cambios |
| `.github/workflows/` | Tres tareas automáticas en GitHub: construir el APK, actualizar tarifas cada semana y publicarlas |
| `capacitor.config.json`, `package.json` | Configuración para generar el APK |

## 1. Subir el proyecto a GitHub

Creá una cuenta en github.com y un repositorio nuevo (por ejemplo `calculadora-peajes`). Desde una terminal, dentro de esta carpeta:

```
git init
git add .
git commit -m "Primera versión"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/calculadora-peajes.git
git push -u origin main
```

Si preferís no usar terminal, GitHub Desktop hace lo mismo. Subí también la carpeta oculta `.github`: sin ella no funcionan las tareas automáticas.

## 2. Conseguir el APK (sin instalar Android Studio)

1. En tu repositorio: pestaña **Actions** → **Construir APK** → **Run workflow**.
2. Esperá unos 5 a 10 minutos. Al terminar, abrí la ejecución y bajá `calculadora-peajes-apk` desde **Artifacts**.
3. Descomprimí el zip y pasá `app-debug.apk` a tu celular. Para instalarlo, Android te pide permitir "instalar apps de origen desconocido".

Ese APK sirve para probar. Para publicar en Google Play hace falta una versión firmada (ver el final).

**Alternativa en tu computadora:** instalá Node.js 22 y Android Studio, y ejecutá `npm install`, `npx cap add android`, `npx cap sync android` y `npx cap open android`. En Android Studio: Build → Build APK(s).

## 3. Actualización semanal de tarifas

Cada lunes a las 8:00 (hora de Argentina), GitHub ejecuta `scripts/actualizar_tarifas.py`. El script:

1. Descarga cada fuente oficial que figura en `tarifas.json`.
2. Le pide a Gemini (plan gratuito) que lea el documento y devuelva los precios, con una cita textual.
3. Acepta un precio solo si la cita existe en el documento, el número está dentro de la cita y el cambio no es exagerado (entre 0,5 y 3 veces el valor actual).
4. Abre un **Pull Request** con la tabla de cambios, los rechazos y las fuentes que no pudo leer. Nada se publica hasta que lo aceptás.

### Puesta en marcha (una sola vez)

1. Sacá una clave gratis en aistudio.google.com ("Get API key").
2. En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**. Nombre: `GEMINI_API_KEY`. Valor: tu clave.
3. **Settings → Actions → General → Workflow permissions**: marcá "Allow GitHub Actions to create and approve pull requests".
4. **Settings → Pages → Source**: elegí "GitHub Actions".
5. En **Actions → Publicar tarifas → Run workflow**. Al terminar, tus tarifas quedan en `https://TU_USUARIO.github.io/calculadora-peajes/tarifas.json`.
6. En `www/index.html`, buscá `TOLLS_URLS`, sacá las barras de la línea de ejemplo y poné esa dirección. La app la usa primero y deja `tarifas.json` (incluido en el APK) como respaldo sin conexión.
7. Probá la actualización: **Actions → Actualizar tarifas → Run workflow**. Si hay cambios, aparece un Pull Request. Al aceptarlo, "Publicar tarifas" se ejecuta solo y la app recibe los valores nuevos sin que tengas que generar otro APK.

### Qué esperar

- Algunas fuentes (por ejemplo páginas que cargan los datos con JavaScript) no se pueden leer con este método. El informe las lista y esas cabinas conservan su valor anterior.
- La IA solo mira auto o vehículo liviano de 2 ejes.
- Las ubicaciones no se actualizan solas. Si cambia una cabina de lugar o se agrega una nueva, hay que cargarla en el Excel.

## 4. Actualizar a mano desde el Excel

Cuando tengas una planilla nueva con las mismas columnas:

```
pip install openpyxl
python3 scripts/build_tarifas.py Peajes_Argentina.xlsx
```

Eso regenera `www/tarifas.json`. Subilo a GitHub y se publica solo. Las cabinas con latitud y longitud en el Excel se toman como **verificadas** si tienen fuente de coordenadas y como **estimadas** si no la tienen. La app marca las estimadas con "ubicación estimada".

## 5. Antes de lanzar al público

- **Servicios de mapas:** la búsqueda de lugares (Nominatim), las rutas (OSRM) y el mapa de fondo (OpenStreetMap) son gratuitos pero tienen política de uso limitado. Con muchos usuarios hay que pasar a un proveedor con plan propio (por ejemplo OpenRouteService o MapTiler).
- **IA dentro de la app:** hoy la app entiende frases simples de forma local. Para que entienda cualquier frase hay que armar un pequeño servidor que guarde la clave de IA y completar `AI_ENDPOINT` en `index.html`. La clave nunca debe ir dentro del APK.
- **Google Play:** hace falta una cuenta de desarrollador (pago único), una versión firmada (AAB), ícono, capturas y una política de privacidad. La app envía a servicios externos los lugares que escribe la persona.
- **Datos:** las tarifas y ubicaciones vienen de tu Excel. Contrastalas con las fuentes oficiales y con viajes reales antes de cobrar por la app.
