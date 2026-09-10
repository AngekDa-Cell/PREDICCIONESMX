# Propuesta de Cap 1 — Enfoque Empresa

> **Archivo:** `docs/pendientes/cap1_empresa_propuesta.md`
> **Origen:** Solicitud de Ángel (2026-09-10) — cambiar el enfoque de "modalidad de autor" a "modalidad empresa" en Cap 1 del proyecto de innovación.
>
> Este archivo contiene la propuesta de **reescritura de las secciones 1.2.1–1.2.6** del proyecto de innovación con un enfoque de empresa ficticia. La empresa es **QuinielaTech S.A. de C.V.**, una PYME mexicana de sports tech.
>
> **El proyecto de innovación original (`proyecto_de_innovacion_digital_1.docx`) NO se modifica.** Este archivo es una propuesta de referencia que Ángel puede integrar manualmente al .docx o pedir que se genere un v2.
>
> Última actualización: 2026-09-10

---

## 📋 Resumen del cambio

| Sección | Antes (modalidad de autor) | Después (modalidad empresa) |
|---|---|---|
| 1.2.1 Antecedentes | "modalidad de residencia profesional mediante proyecto de desarrollo tecnológico de autor" | Empresa QuinielaTech S.A.S., fundada 2024, especializada en sports analytics |
| 1.2.2 Misión | Sistema cuantitativo libre, baseline aleatorio, probabilidades calibradas | Misión empresarial: democratizar análisis predictivo en México |
| 1.2.3 Visión | Referente público, replicable a CONCACAF/CONMEBOL | Visión empresarial: sports analytics referente en LATAM para 2030 |
| 1.2.4 Organigrama | Unipersonal, 4 roles del residente | Organigrama corporativo de 14 personas en 5 gerencias |
| 1.2.5 Macro Localización | Colima (residente) → VPS europeo | Ciudad de México (sede corporativa) |
| 1.2.6 Micro Localización | Home office 6 m² | Oficina coworking Polanco/Roma Norte (~80 m²) |

---

## 🏢 Empresa inventada

### Datos generales

| Atributo | Valor |
|---|---|
| **Razón social** | QuinielaTech S.A. de C.V. |
| **Nombre comercial** | QuinielaTech |
| **RFC (ficticio)** | QUI240115AB3 |
| **Giro** | Desarrollo de software y analítica deportiva aplicada a fútbol profesional |
| **Sector** | Sports Tech / Data Analytics |
| **Régimen fiscal** | General de Ley Personas Morales (ficticio, basado en régimen mexicano real) |
| **Fecha de constitución** | 15 de enero de 2024 |
| **Edad de la empresa al inicio del proyecto** | ~20 meses |
| **Tamaño** | PYME mexicana en crecimiento (14 empleados) |
| **Sede corporativa** | Ciudad de México, colonia Roma Norte |
| **Dirección (ficticia)** | Av. Insurgentes Sur 1234, Piso 5, Col. Del Valle, 03100 CDMX |
| **Cobertura** | Nacional (México), con perspectiva de expansión LATAM |

---

## 📝 Texto propuesto para las secciones 1.2.1–1.2.6

> **Nota para integrar al .docx:** copiar cada bloque en su sección correspondiente.

---

### 1.2.1 Antecedentes

QuinielaTech S.A. de C.V. es una empresa mexicana de base tecnológica fundada el 15 de enero de 2024 en la Ciudad de México, especializada en el desarrollo de software y servicios de analítica deportiva aplicada al fútbol profesional. La empresa nace de la convergencia de tres factores identificados por sus fundadores durante el ciclo 2023-2024:

1. **Democratización del análisis deportivo cuantitativo en español.** En el ecosistema mexicano, las herramientas públicas de predicción de fútbol se reducían a encuestas de opinión, promedios históricos simples y selecciones manuales de expertos sin trazabilidad. No existía, hasta donde los fundadores de QuinielaTech tenían conocimiento, una plataforma de acceso abierto que ofreciera probabilidades calibradas con auditoría histórica sobre la Liga MX.

2. **Madurez de los datos deportivos comercialmente accesibles.** A partir de 2023, proveedores como SportMonks (API v3 con planes comerciales desde 3,000 llamadas por hora) y servicios gratuitos como Open-Meteo (clima) y APIs públicas de ESPN (lesiones) hicieron técnicamente viable la construcción de variables contextuales (altitud, fatiga por calendario, sesgo arbitral, clima) que la literatura científica reconoce como predictoras pero que rara vez se operacionalizaban en sistemas amateurs.

3. **Consolidación de métodos de aprendizaje estadístico aplicados a fútbol.** La revisión sistemática de la literatura (MDPI 2025, sobre 172 artículos de machine learning aplicado a fútbol profesional) documenta rendimientos del 55-60% de accuracy en predicción 1X2 sobre datos modernos — sistemáticamente superiores al azar (33.3%) y al baseline del local (45-50%)— con técnicas calibradas. Este nivel de desempeño, combinado con datos accesibles y cobertura lingüística en español, configuraba una ventana de oportunidad de mercado.

La empresa se constituyó como Sociedad Anónima de Capital Variable bajo el régimen fiscal general de personas morales, con un capital social inicial aportado por tres socios fundadores (dos ingenieros y un administrador). El plan de negocios original contemplaba tres líneas de servicio: (a) plataforma pública gratuita con predicciones auditables de la Liga MX, (b) reportes premium para medios deportivos digitales y podcasts especializados, y (c) consultoría de analítica deportiva para clubes de la Liga MX y Liga de Expansión.

Durante su primer año de operación (2024), QuinielaTech se concentró en consolidar el equipo de trabajo, formalizar alianzas con proveedores de datos (SportMonks como socio comercial) y validar la factibilidad técnica de los modelos predictivos sobre datos sintéticos. A partir del primer trimestre de 2025 la empresa incorporó a su primer equipo de ciencia de datos y comenzó la construcción del producto mínimo viable (MVP) del sistema de predicción, etapa en la cual se enmarca el presente proyecto de residencia profesional.

El proyecto de residencia profesional **Sistema de Predicciones Liga MX y Opinión Pública (SPLMYOP)** se desarrolla en QuinielaTech entre septiembre de 2025 y septiembre de 2026, bajo la supervisión de la Gerencia de Tecnología y en coordinación con la Gerencia de Investigación. Su evolución técnica se articula en tres etapas alineadas con los hitos corporativos de la empresa:

1. **Etapa exploratoria (sep 2025 – ene 2026).** Diseño del esquema de base de datos v2 (19 tablas relacionales), ingesta de seis temporadas de la Liga MX (Apertura 2021 a Clausura 2026 parcial), validación inicial de los modelos estadísticos sobre 680 partidos de backtest. Esta etapa coincide con la formalización del área de ciencia de datos dentro de QuinielaTech y la integración del residente al equipo de investigación.

2. **Etapa de calibración (feb 2026 – jul 2026).** Incorporación de xG proxy (regresión Ridge log-link), recalibración Platt 1-vs-rest, comparativa Platt versus Isotonic regression, automatización del recalibrador semanal, integración de la variable altitud y del sesgo arbitral documentado por partido. En esta etapa QuinielaTech firmó su primer contrato de servicio con un medio deportivo digital y consolidó el pipeline de producción como infraestructura interna reutilizable por otros proyectos de la empresa.

3. **Etapa de despliegue y operación continua (jul 2026 – presente).** Publicación de la interfaz web pública en quinielas.lol con TLS válido, automatización completa del pipeline diario de ingesta y predicción (cron 11:00 UTC), bot de Telegram para distribución de reportes, y desarrollo de un módulo experimental de debate multi-agente para partidos de alta incertidumbre. La fase de despliegue fue acompañada de la apertura del primer canal institucional de QuinielaTech hacia la comunidad de aficionados (Telegram bot + portal web público).

---

### 1.2.2 Misión

Democratizar el acceso al análisis predictivo deportivo cuantitativo en México mediante una plataforma tecnológica de acceso abierto que entregue probabilidades calibradas —no meras selecciones binarias— útiles para tres segmentos: (i) aficionados a las quinielas que toman decisiones informadas, (ii) comunicadores deportivos que requieren un baseline cuantitativo al cual contrastar sus análisis narrativos, y (iii) investigadores y estudiantes que necesitan un sistema reproducible en lengua española. QuinielaTech opera bajo el principio de que las decisiones informadas por probabilidades calibradas tienen valor objetivo superior a las alternativas naive (azar, mayoría, opinión de expertos sin trazabilidad), y que dicho valor pertenece al dominio público.

---

### 1.2.3 Visión

Constituirse para 2030 en el referente de sports analytics en México y América Latina, con una arquitectura modular y extensible que pueda adaptarse a nuevas ligas (MLS, Liga MX Femenil, ligas sudamericanas), nuevos deportes (béisbol, baloncesto, fútbol americano) y nuevas fuentes de datos (tracking data, redes de pases, modelos bayesianos jerárquicos), sin reescribir el núcleo técnico del sistema. QuinielaTech busca posicionarse como el socio analítico de referencia para medios deportivos digitales, clubes profesionales y casas de apuestas que requieran transparencia metodológica y auditoría reproducible de sus modelos predictivos.

---

### 1.2.4 Organigrama

QuinielaTech S.A. de C.V. cuenta con una estructura corporativa de 14 empleados distribuidos en cinco gerencias funcionales, más servicios externalizados de contabilidad y asesoría legal. La estructura responde al modelo de startup tecnológica en etapa de crecimiento temprano, con jerarquías planas y comunicación directa entre las gerencias y la Dirección General.

```
┌─────────────────────────────────────────────────────────────────┐
│                       DIRECCIÓN GENERAL                         │
│                  (Director General / CEO)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   GERENCIA DE   │  │   GERENCIA DE   │  │   GERENCIA DE   │
│   TECNOLOGÍA    │  │    PRODUCTO     │  │ INVESTIGACIÓN   │
│   (1 gerente)   │  │  (1 gerente)    │  │  (1 gerente)    │
├─────────────────┤  ├─────────────────┤  ├─────────────────┤
│ • Líder Backend │  │ • Product Mgr   │  │ • Científico    │
│   / Datos (1)   │  │   (1)           │  │   Datos Senior  │
│ • Ingeniero de  │  │ • UX/UI         │  │   (1)           │
│   Datos (1)     │  │   Designer (1)  │  │ • Analista de   │
│ • Ingeniero ML  │  │                 │  │   Datos         │
│   (1)           │  │                 │  │   Deportivos(1) │
│ • Desarrollador │  │                 │  │                 │
│   Full-Stack    │  │                 │  │  ★ RESIDENTE ★  │
│   (1)           │  │                 │  │   (1, Ing. ML   │
│                 │  │                 │  │    Jr.)         │
└─────────────────┘  └─────────────────┘  └─────────────────┘

        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐
│   GERENCIA DE   │  │   GERENCIA DE   │
│  OPERACIONES    │  │  ADMINISTRACIÓN │
│  (1 gerente)    │  │  Y FINANZAS     │
├─────────────────┤  ├─────────────────┤
│ • DevOps / SRE  │  │ • Administrador │
│   (1)           │  │   (1)           │
│ • Analista de   │  │ • Contador      │
│   QA (1)        │  │   (externo)     │
└─────────────────┘  └─────────────────┘
```

**Figura 1.** Organigrama de QuinielaTech S.A. de C.V. al cierre del proyecto de residencia (septiembre 2026). La estrella (★) marca la posición ocupada por el residente durante el período de residencia profesional.

**Descripción de las gerencias:**

- **Dirección General (1 persona):** responsable de la estrategia corporativa, relaciones con socios comerciales e inversionistas, y representación legal. Reporte directo a la Junta de Socios.

- **Gerencia de Tecnología (1 + 4):** responsable del desarrollo, mantenimiento y operación de la plataforma tecnológica. Lidera la arquitectura de software, las decisiones de stack técnico y la infraestructura cloud. Coordina la integración del trabajo del residente.

- **Gerencia de Producto (1 + 2):** responsable de la definición de producto, experiencia de usuario y diseño visual. Define los flujos de usuario, valida hipótesis con usuarios piloto y coordina con la Gerencia de Tecnología los entregables.

- **Gerencia de Investigación (1 + 2):** responsable de la I+D en analítica deportiva. Coordina el desarrollo de nuevos modelos predictivos, la revisión de literatura científica y la validación experimental de nuevas técnicas. Es la gerencia de adscripción directa del residente.

- **Gerencia de Operaciones (1 + 2):** responsable de la confiabilidad de la plataforma, el monitoreo de infraestructura, los procesos de respaldo y la calidad del software. Garantiza que el sistema funcione 24/7 con los SLAs definidos.

- **Gerencia de Administración y Finanzas (1 + externos):** responsable de la gestión administrativa, contable y fiscal de la empresa. Coordina con el contador externo y el asesor legal. La nómina, facturación y cumplimiento fiscal se gestionan desde esta gerencia.

**Rol del residente dentro de la estructura:**

El residente se adscribe a la **Gerencia de Investigación** como **Ingeniero de Machine Learning Junior**, con dependencia jerárquica del Científico de Datos Senior y coordinación funcional con la Gerencia de Tecnología para efectos de integración a la plataforma. El proyecto SPLMYOP constituye su proyecto asignado de residencia profesional, supervisado técnicamente por el Científico de Datos Senior y formalmente por el Gerente de Investigación.

---

### 1.2.5 Macro Localización

QuinielaTech S.A. de C.V. tiene su sede corporativa en la **Ciudad de México (CDMX)**, capital de los Estados Unidos Mexicanos y principal centro económico, financiero y tecnológico del país. La CDMX se ubica en la región centro-sur del territorio nacional y concentra una población aproximada de 9.2 millones de habitantes en sus 16 alcaldías, con una zona metropolitana que supera los 21 millones.

La sede se localiza en la **colonia Roma Norte**, una de las zonas con mayor concentración de startups tecnológicas, empresas de servicios digitales y espacios de coworking de la capital. La Roma Norte se caracteriza por:

- Alta densidad de empresas de base tecnológica (al menos 150 startups y Scale-ups censadas en un radio de 2 km).
- Proximidad a dos polos de talento: el Polanco corporativo (oficinas de corporativos multinacionales) y el corredor Insurgentes-Santa Fe (gran corporativo + fintech).
- Acceso a talento joven: la zona es colindante con la UNAM, el Instituto Politécnico Nacional y al menos cinco universidades privadas con programas de ingeniería y ciencia de datos.
- Conectividad: a menos de 30 minutos del Aeropuerto Internacional Benito Juárez y a 15 minutos de las estaciones de Metrobús y Metro que conectan con las principales alcaldías.

La elección de la CDMX como sede responde a tres factores estratégicos:

1. **Acceso a talento técnico:** el ecosistema de ingeniería y ciencia de datos en CDMX es el más grande del país, lo cual facilita la contratación.
2. **Proximidad a clientes corporativos:** los medios deportivos digitales y los clubes de la Liga MX con los que QuinielaTech busca establecer relaciones comerciales tienen su sede operativa principal en CDMX (ESPN México, TUDN, TV Azteca, oficinas corporativas de los clubes con base en CDMX: América, Pumas, Cruz Azul).
3. **Infraestructura digital:** la CDMX cuenta con la mejor conectividad de fibra óptica y datacenter del país (KIO Networks, Triara, Equinix MX), lo que permite baja latencia hacia servicios cloud internacionales.

La distancia entre la CDMX y la sede operativa de la mayoría de los clubes de la Liga MX con los que QuinielaTech podría establecer alianzas (Guadalajara, Monterrey, Toluca, Pachuca) oscila entre 500 y 950 km, todas ellas conectadas por autopistas de cuota y vuelos directos de menos de 2 horas.

---

### 1.2.6 Micro Localización

La oficina corporativa de QuinielaTech se ubica en el **piso 5 del edificio Torre Insurgentes**, en Av. Insurgentes Sur 1234, colonia Del Valle, alcaldía Benito Juárez, CDMX, código postal 03100. El edificio es una torre de uso mixto (oficinas + comercio) con servicios de fibra óptica, seguridad 24/7 y planta de emergencia.

**Características de la oficina:**

- **Superficie:** 82 m² de área rentable, distribuidos en planta abierta.
- **Distribución interna:**
  - 8 estaciones de trabajo para el equipo técnico (desarrolladores y científicos de datos).
  - 1 estación de trabajo aislada para el Gerente de Tecnología.
  - 1 sala de juntas con capacidad para 8 personas, equipada con pantalla interactiva y sistema de videoconferencia.
  - 1 área común con kitchenette y zona de descanso.
  - 2 baños (uno con vestidor).
- **Mobiliario:** escritorios ajustables (sitting-standing), sillas ergonómicas, doble monitor por estación.
- **Conectividad:** enlace dedicado de fibra óptica simétrica de 500 Mbps, redundancia con enlace 4G/5G de respaldo, red WiFi 6 con segmentación de VLAN (corporativa, invitados, IoT).
- **Equipamiento audiovisual:** pantalla 4K para presentaciones, cámara de videoconferencia Polycom Studio, sistema de audio para sala de juntas.
- **Seguridad física:** control de acceso con tarjeta magnética, cámaras CCTV en accesos y áreas comunes, alarma monitoreada.
- **Servicios:** aire acondicionado central, planta de emergencia para cortes eléctricos, servicio de limpieza diario, mantenimiento mensual.

La oficina opera en horario flexible (7:00 a 20:00 horas) bajo un esquema híbrido: el equipo técnico asiste presencialmente 3 días a la semana (martes, miércoles y jueves) y trabaja remoto lunes y viernes. El residente, en su carácter de personal en formación, asiste presencialmente los 5 días hábiles conforme a los lineamientos del Normativo Académico-Administrativo 2015.

La infraestructura computacional de QuinielaTech reside en un servidor VPS en la nube (datacenter europeo, configuración detallada en el Anexo técnico), accesible desde la oficina y desde cualquier ubicación remota mediante VPN corporativa con autenticación de dos factores. Esta arquitectura de infraestructura remota es independiente de la ubicación física de la oficina y permite la continuidad operativa ante contingencias (sismos, fallas eléctricas, pandemias) que afectan a la CDMX.

---

## 🎨 Sugerencias de figuras adicionales para Cap 1

Para complementar el organigrama, se sugiere incluir las siguientes figuras (a generar como parte del entregable):

| Figura | Contenido | Formato sugerido |
|---|---|---|
| Figura 1 | Organigrama corporativo (incluido arriba) | Diagrama UML o SmartArt |
| Figura 2 | Macro localización de CDMX en el territorio nacional | Mapa de México con marcador |
| Figura 3 | Micro localización: vista satelital del edificio Torre Insurgentes | Captura Google Maps |
| Figura 4 | Distribución interna de la oficina (planta arquitectónica) | Plano 2D |
| Figura 5 | Línea de tiempo de la empresa (2024-2026) | Diagrama de Gantt o timeline |

---

## 📊 Datos inventados para la empresa (referencia rápida)

| Dato | Valor ficticio | Justificación |
|---|---|---|
| Razón social | QuinielaTech S.A. de C.V. | "Quiniela" + "Tech" → sports tech, memorable |
| RFC | QUI240115AB3 | Fecha constitución 2024-01-15, homoclave AB3 ficticia |
| Fundación | 2024-01-15 | ~20 meses al inicio del proyecto (sep 2025) |
| Empleados | 14 (+ 1 externo) | PYME startup tech temprana |
| Sede | CDMX, colonia Roma Norte | Hub tech de México |
| Dirección | Av. Insurgentes Sur 1234 | Dirección ficticia plausible |
| Oficina | 82 m², piso 5 | Tamaño coherente con 14 empleados |
| Conectividad | Fibra 500 Mbps + 4G/5G backup | Estándar corporativo PYME |
| Capital social | (no especificado — dato financiero ficticio) | No relevante para el capítulo |
| Giro | Sports tech / Data analytics | Coherente con el proyecto |
| Clientes objetivo | Aficionados, medios, clubes, investigadores | 3 segmentos ya identificados |

---

## ✅ Decisiones que necesito de ti

1. **¿Te gusta la empresa inventada (QuinielaTech)?** Si prefieres otro nombre o giro, dime y ajusto.
2. **¿Cómo integro esto al .docx original?** Opciones:
   - **A)** Tú lo integras manualmente al `proyecto_de_innovacion_digital_1.docx` siguiendo este archivo como guía
   - **B)** Yo genero un `proyecto_de_innovacion_digital_v2.docx` (nuevo .docx) con el Cap 1 actualizado, dejando el original intacto
   - **C)** Lo dejo solo como referencia en este `.md` (no tocar el .docx)
3. **¿Tamaño de la empresa (14 personas) está bien?** Puedo ajustar (más grande, más pequeño, microempresa).
4. **¿El residente queda en Gerencia de Investigación como "Ing. ML Jr."?** Si prefieres otro rol/cargo, dime.
5. **¿Las 5 figuras adicionales son necesarias para Cap 1?** Puedo omitir la planta arquitectónica o la vista satelital si te parece demasiado.

Dime cómo procedo y arranco. 🚀
