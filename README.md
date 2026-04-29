# SentinelDrive

Aplicación web para la gestión de flotas y obtención de datos considerados riesgosos.

## Descripción
SentinelDrive es una aplicación web desarrollada como tesis para la **Universidad Nacional de Loja**. El sistema permite la gestión integral de flotas de transporte y la obtención de datos considerados riesgosos mediante monitoreo y análisis en tiempo real.

## Características
- Gestión integral de flotas de buses
- Obtención y análisis de datos considerados riesgosos
- Monitoreo y seguimiento GPS en tiempo real
- Registro y gestión de eventos operativos
- Módulo de mantenimientos preventivos y correctivos
- Reportes y analíticas de operación
- Gestión de usuarios con roles de acceso
- Panel de control con métricas clave

## Autor
**Gerardo Gonza**  
Universidad Nacional de Loja  
Loja, Ecuador

## Requisitos
- Python 3.8+
- pip

## Instalación y Uso

1. Clona el repositorio:
   ```bash
   git clone https://github.com/tu-usuario/sentinelDrive.git
   cd sentinelDrive
   ```

2. Crea y activa un entorno virtual:
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # macOS/Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Instala las dependencias:
   ```bash
   pip install -r requirements.txt
   ```

4. Configuración inicial:
   La aplicación genera automáticamente una clave secreta al iniciar. Si deseas configurar una manualmente, crea un archivo `.env` en la raíz:
   ```
   SECRET_KEY=tu_clave_secreta_muy_segura
   ```

5. Ejecuta la aplicación:
   ```bash
   python run.py
   ```

6. Accede a la aplicación en:
   ```
   http://localhost:5000
   ```

## Licencia
Este proyecto está bajo la Licencia MIT. Consulta [LICENSE.txt](LICENSE.txt) para más detalles.
