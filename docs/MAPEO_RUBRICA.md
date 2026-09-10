# Mapeo Rúbrica ↔ Documentación Técnica

> Guía de qué documento técnico alimenta qué sección de la **Memoria de Residencia Profesional** (Normativo Académico-Administrativo 2015, TECNM).
>
> **Fuentes:**
> - Rúbrica completa: [`docs/RUBRICA_DE_ING._EN_SISTEMAS_2019.docx`](./RUBRICA_DE_ING._EN_SISTEMAS_2019.docx)
> - Proyecto de innovación digital: [`docs/pendientes/proyecto_de_innovacion_digital_1.docx`](./pendientes/proyecto_de_innovacion_digital_1.docx)
>
> Última actualización: 2026-09-10

---

## 🎯 Cómo usar este documento

Para cada sección de la rúbrica, este archivo lista:
- **Qué doc técnico** alimenta la sección (✅ ya listo)
- **Qué falta generar** (📝 pendiente)
- **Notas** sobre cómo adaptar el contenido técnico al formato académico

**Reglas generales:**
1. Los docs técnicos están en formato Markdown informal (código + decisiones). El doc de residencia debe reescribirse en prosa académica, citando los docs como bibliografía.
2. Todos los diagramas UML deben regenerarse (los docs técnicos tienen diagramas ASCII, insuficientes para Cap 2).
3. Las comparaciones numéricas (accuracy, Brier) son ORO para Cap 4 (45 pts).

---

## 📋 Mapeo por sección

### Pre-rúbrica

| Sección | Puntos | Fuente | Estado |
|---|---|---|---|
| Portada | 2 | Generar | 📝 Pendiente |
| Agradecimientos | 2 | Generar | 📝 Pendiente |
| Resumen | 2 | Generar (síntesis del proyecto_innovacion doc + estado actual) | 📝 Pendiente |
| Índice general | — | Auto-generar (Word/LaTeX) | 📝 Pendiente |
| Índice de tablas | — | Auto-generar | 📝 Pendiente |
| Índice de figuras | — | Auto-generar | 📝 Pendiente |
| Índice de fórmulas | — | Listar: Platt scaling, Poisson bivariado, Elo update, xG Ridge | 📝 Pendiente |

---

### CAPÍTULO 1 — GENERALIDADES DEL PROYECTO

| Sección rúbrica | Puntos | Fuente técnica | Estado |
|---|---|---|---|
| 1.1 Introducción | — | [`docs/pendientes/proyecto_de_innovacion_digital_1.docx`](./pendientes/proyecto_de_innovacion_digital_1.docx) § 1.1 | ✅ Listo (ya escrito en proyecto) |
| 1.2 Descripción de la empresa | — | Modalidad "desarrollo tecnológico de autor" (Normativo 2015). Sin empresa externa. Generar texto desde [`docs/pendientes/proyecto_de_innovacion_digital_1.docx`](./pendientes/proyecto_de_innovacion_digital_1.docx) § 1.2 | ✅ Listo |
| 1.2.1 Antecedentes | — | Mismo doc § 1.2.1 (3 etapas: exploratoria, calibración, despliegue) | ✅ Listo |
| 1.2.2 Misión | — | Mismo doc § 1.2.2 | ✅ Listo |
| 1.2.3 Visión | — | Mismo doc § 1.2.3 | ✅ Listo |
| 1.2.4 Organigrama | — | Mismo doc § 1.2.4 (4 roles unipersonales: backend, frontend, datos, despliegue). **Generar diagrama UML de organigrama** | 📝 Diagrama pendiente |
| 1.2.5 Macro Localización | — | Mismo doc § 1.2.5 (Colima, México → VPS europeo) | ✅ Listo |
| 1.2.6 Micro Localización | — | Mismo doc § 1.2.6 (home office 6m²) | ✅ Listo |
| 1.3.1 Planteamiento del problema | 5 | Mismo doc § 1.3.1 (3 actores: aficionados, analistas, investigadores) | ✅ Listo |
| 1.3.2 Alcances | 5 | Mismo doc § 1.3.2 (9 entregables numerados) | ✅ Listo |
| 1.3.3 Limitaciones | 5 | Mismo doc § 1.3.3 (8 limitaciones) | ✅ Listo |
| 1.4.1 Objetivo General | 5 | Mismo doc § 1.4.1 | ✅ Listo |
| 1.4.2 Objetivos Específicos (OE1-OE7) | 5 | Mismo doc § 1.4.2 (7 OE numerados) | ✅ Listo |
| 1.5 Justificación | — | Mismo doc § 1.5 (técnica + pertinencia + impacto) | ✅ Listo |

**Total Cap 1:** 25 pts (5+5+5+5+2+2+1) — TODO basado en proyecto_innovacion doc.

---

### CAPÍTULO 2 — MARCO TEÓRICO (10 pts, 20-25 cuartillas)

| Sección rúbrica | Fuente técnica | Estado |
|---|---|---|
| 2.1 Introducción | Generar | 📝 Pendiente |
| 2.2 Estado del arte | [`docs/pendientes/proyecto_de_innovacion_digital_1.docx`](./pendientes/proyecto_de_innovacion_digital_1.docx) § "Estado del arte" (10 papers tabulados con URLs) + [`docs/RESEARCH_SYNTHESIS.md`](./RESEARCH_SYNTHESIS.md) | ✅ Listo |
| 2.3 Conceptos relacionados | [`docs/RESEARCH_SYNTHESIS.md`](./RESEARCH_SYNTHESIS.md) + [`docs/ARTICLES_INVENTORY.md`](./ARTICLES_INVENTORY.md) | ✅ Listo |
| 2.4 Conceptos técnicos | | |
| → 2.4.1 Sistemas de Información | Proyecto_innovacion doc § intro + [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) | ✅ Listo |
| → 2.4.2 Base de Datos | [`docs/SCHEMA_V2.md`](./SCHEMA_V2.md) — 19 tablas, ER, normalización 3FN, SGBD (SQLite) | ✅ Listo |
| → 2.4.2.1 Modelo Entidad-Relación | [`docs/SCHEMA_V2_VISUAL.txt`](./SCHEMA_V2_VISUAL.txt) + [`docs/SCHEMA_V2.md`](./SCHEMA_V2.md) | ⚠️ Diagrama ER formal pendiente (regenerar en UML/lucidchart) |
| → 2.4.2.2 Proceso de Normalización | [`docs/SCHEMA_V2.md`](./SCHEMA_V2.md) § normalización | ✅ Listo (texto) |
| → 2.4.2.3 Modelo relacional | [`docs/SCHEMA_V2.md`](./SCHEMA_V2.md) | ✅ Listo |
| → 2.4.2.4 Diccionario de Datos | [`docs/SCHEMA_V2.md`](./SCHEMA_V2.md) § diccionario | ⚠️ Regenerar en formato académico |
| → 2.4.2.5 SGBD | [`docs/SCHEMA_V2.md`](./SCHEMA_V2.md) + `lib/db/client.ts` (justificación SQLite) | ✅ Listo |
| → 2.4.2.6 Justificación del SGBD | [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) § "Decisiones de diseño" punto 1 | ✅ Listo |
| → 2.4.3 Lenguajes de programación | `requirements.txt` (Python 3.12) + `package.json` (TypeScript 5.5) | ✅ Listo |
| → 2.4.3.1 Justificación del lenguaje | [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) § decisiones + [`docs/ARCHITECTURE_FRONTEND.md`](./ARCHITECTURE_FRONTEND.md) § stack | ✅ Listo |
| → 2.4.4 Arquitectura que se aplica | [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) + [`docs/ARCHITECTURE_FRONTEND.md`](./ARCHITECTURE_FRONTEND.md) + [`docs/DEPLOY_DOKPLOY.md`](./DEPLOY_DOKPLOY.md) | ✅ Listo (texto + diagramas ASCII) — regenerar en UML |
| → 2.4.5 Metodología de desarrollo | [`docs/METHODOLOGY.md`](./METHODOLOGY.md) (modelo de predicción, no metodología de software). Para metodología de software: **escoger entre cascada, iterativo, ágil, XP, Scrum, etc. y justificar** | 📝 Decisión pendiente (recomiendo: iterativo-incremental con sprints) |
| → 2.4.6 UML | — | 📝 **TODO el capítulo UML pendiente** |
| → 2.4.6.1 Casos de uso | — | 📝 Generar diagramas de casos de uso del sistema completo |
| → 2.4.6.2 Diagramas de Clases | — | 📝 Generar diagrama de clases del backend + frontend |
| → 2.4.6.3 Diagramas de Estados | — | 📝 Generar (ej: estado de una predicción: pending → live → finished → reconciled) |
| → 2.4.6.4 Diagrama de Colaboración/Comunicación | — | 📝 Generar (ej: pipeline diario con sus componentes) |
| → 2.4.6.5 Diagramas de Secuencia | — | 📝 Generar (ej: flujo de voto en /api/votes/[token]) |
| → 2.4.7 Modelo de Costos | — | 📝 **Generar tabla de costos** (APIs: $0 SportMonks custom, hosting VPS ~$5/mes, dominio ~$10/año, tiempo de desarrollo ~N horas × costo/hora) |
| 2.5 Conclusiones del marco teórico | Generar | 📝 Pendiente |

**Total Cap 2:** 10 pts + capítulo más largo (20-25 cuartillas).

**Trabajo pendiente crítico para Cap 2:**
1. **Diagrama ER formal** del schema v2 (usar draw.io / Lucidchart / PlantUML)
2. **Decidir metodología de desarrollo de software** (recomiendo iterativo-incremental justificado)
3. **Generar todos los diagramas UML**: casos de uso, clases, estados, colaboración, secuencia
4. **Modelo de costos**: infraestructura + tiempo de desarrollo + herramientas

---

### CAPÍTULO 3 — DESARROLLO (5 pts)

| Sección rúbrica | Fuente técnica | Estado |
|---|---|---|
| 3.1 Introducción | Generar | 📝 Pendiente |
| 3.2 Descripción de actividades según metodología | Bitácora del proyecto + commits del repo (`git log` desde 2025) | ⚠️ Bitácora dispersa en commits — consolidar |
| 3.3 Determinación de requerimientos | | |
| → 3.3.1 Requerimientos funcionales | [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) + [`docs/ARCHITECTURE_FRONTEND.md`](./ARCHITECTURE_FRONTEND.md) | ⚠️ Lista informal — formalizar |
| → 3.3.2 Requerimientos no funcionales | [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) § Seguridad + [`docs/QUINIELAS_SYSTEM.md`](./QUINIELAS_SYSTEM.md) § Seguridad | ⚠️ Lista informal — formalizar (performance, seguridad, usabilidad, mantenibilidad) |
| 3.4 Diseño de base de datos | | |
| → 3.4.1 Modelo Entidad-Relación | [`docs/SCHEMA_V2_VISUAL.txt`](./SCHEMA_V2_VISUAL.txt) | ⚠️ Regenerar diagrama ER formal |
| → 3.4.2 Modelo Relacional | [`docs/SCHEMA_V2.md`](./SCHEMA_V2.md) | ✅ Listo (texto) |
| → 3.4.3 Diccionario de Datos | [`docs/SCHEMA_V2.md`](./SCHEMA_V2.md) § diccionario | ⚠️ Regenerar en formato académico |
| 3.5 Diagramas de UML | | |
| → 3.5.1 Diagrama de Clases | — | 📝 Generar (backend Python + frontend TS) |
| → 3.5.2 Casos de uso (con descripción) | — | 📝 Generar (ej: "registrar voto", "consultar predicción", "recalibrar Platt") |
| → 3.5.3 Diagrama de Actividades | — | 📝 Generar (ej: pipeline diario, recalibración semanal) |
| → 3.5.4 Diagrama de Secuencia | — | 📝 Generar (ej: POST /api/votes/[token], pipeline step 7) |
| → 3.5.5 Diagrama de Estado | — | 📝 Generar (ej: estado de predicción: draft → live → finished → reconciled → archived) |
| → 3.5.6 Diagrama de Colaboración | — | 📝 Generar (ej: interacción entre agentes multi-agente) |
| → 3.5.7 Diagrama de Componentes | — | 📝 Generar (módulos del sistema: ingest → features → ensemble → calibrate → distribute) |
| → 3.5.8 Diagrama de Despliegue | [`docs/DEPLOY_DOKPLOY.md`](./DEPLOY_DOKPLOY.md) | ⚠️ Regenerar diagrama de despliegue UML formal |
| 3.6 Determinación de Costos | — | 📝 **Misma tabla que Cap 2.4.7** (referenciar) |
| 3.7 Modelo de Seguridad del Sistema | [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) § Seguridad + [`docs/QUINIELAS_SYSTEM.md`](./QUINIELAS_SYSTEM.md) § Seguridad + [`docs/ARCHITECTURE_FRONTEND.md`](./ARCHITECTURE_FRONTEND.md) § Seguridad | ✅ Listo |
| 3.8 Diseño de Interfaces | Screenshots de [predicciones.barberia.date](https://predicciones.barberia.date) | 📝 **Tomar screenshots y mockups** |
| 3.9 Plan de pruebas | | |
| → 3.9.1 Pruebas unitarias | `tests/` (257 tests Python) | ✅ Listo |
| → 3.9.2 Pruebas de integración | `tests/test_integration.py` | ⚠️ Documentar |
| → 3.9.3 Pruebas de regresión | CI/CD (pendiente Fase D.4) | ⚠️ Documentar el flujo actual + plan |
| → 3.9.4 Pruebas de carga | — | 📝 Pendiente |

**Total Cap 3:** 5 pts.

**Trabajo pendiente crítico para Cap 3:**
1. **Lista formal de requerimientos funcionales y no funcionales** (se puede extraer de [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md))
2. **Generar todos los diagramas UML** (mismos que Cap 2 pero aplicados al sistema desarrollado)
3. **Screenshots/mockups del frontend** (capturar de predicciones.barberia.date)
4. **Plan de pruebas documentado** (qué se prueba, cómo, con qué datos)

---

### CAPÍTULO 4 — RESULTADOS (45 pts) ⭐ EL MÁS IMPORTANTE

| Sección rúbrica | Fuente técnica | Estado |
|---|---|---|
| 4.1 Introducción | Generar | 📝 Pendiente |
| 4.2 Comparación proceso anterior vs automatizado | [`docs/BACKTESTING_RESULTS.md`](./BACKTESTING_RESULTS.md) | ✅ Listo |
| → Antes (sin modelo) | Baseline 33.3% azar, 45-50% mayoría local | ✅ Listo |
| → Después (con modelo) | Ensemble 52.21%, +Platt 51.1% acc, Brier 0.2009 | ✅ Listo |
| → Tabla comparativa de métricas | [`docs/BACKTESTING_RESULTS.md`](./BACKTESTING_RESULTS.md) + [`docs/ROADMAP.md`](./ROADMAP.md) § "Métricas live" | ✅ Listo |
| 4.3 Prototipo de Software | [predicciones.barberia.date](https://predicciones.barberia.date) LIVE | ✅ Listo |
| → Screenshots del prototipo | Tomar del sitio live | 📝 Tomar capturas |
| → URL pública | https://predicciones.barberia.date | ✅ Listo |
| → Descripción técnica del prototipo | [`docs/ARCHITECTURE_FRONTEND.md`](./ARCHITECTURE_FRONTEND.md) + [`docs/QUINIELAS_SYSTEM.md`](./QUINIELAS_SYSTEM.md) | ✅ Listo |
| 4.4 Manuales | | |
| → Manual de Instalación | [`docs/DEPLOY_DOKPLOY.md`](./DEPLOY_DOKPLOY.md) + [`deploy/DOKPLOY.md`](../deploy/DOKPLOY.md) | ⚠️ **Reescribir en formato manual** (paso a paso, screenshots) |
| → Manual Técnico | [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) + [`docs/METHODOLOGY.md`](./METHODOLOGY.md) + [`docs/FEATURES.md`](./FEATURES.md) + [`docs/SCHEMA_V2.md`](./SCHEMA_V2.md) | ⚠️ **Reescribir en formato manual** (operación, mantenimiento, troubleshooting) |
| → Manual de Usuario | — | 📝 **Generar desde cero** (cómo usar la web, cómo votar, cómo leer predicciones) |
| 4.5 Análisis estadístico / modelos matemáticos | [`docs/METHODOLOGY.md`](./METHODOLOGY.md) + [`docs/RESEARCH_SYNTHESIS.md`](./RESEARCH_SYNTHESIS.md) | ✅ Listo |
| 4.6 Conclusiones del capítulo | Generar | 📝 Pendiente |

**Total Cap 4:** 45 pts (la nota fuerte).

**Trabajo pendiente crítico para Cap 4:**
1. **Screenshots del prototipo** (tomar de predicciones.barberia.date)
2. **Manual de instalación** formal (basado en `docs/DEPLOY_DOKPLOY.md`)
3. **Manual técnico** formal (basado en arquitectura + methodology)
4. **Manual de usuario** desde cero (cómo votar, cómo leer predicciones, glosario de términos)

---

### CONCLUSIONES (15 pts) ⭐

| Sección rúbrica | Fuente técnica | Estado |
|---|---|---|
| Conclusiones del Proyecto | [`docs/ROADMAP.md`](./ROADMAP.md) § "Estado actual" + logros enumerados | ✅ Listo (síntesis) |
| Recomendaciones Técnicas | [`docs/ROADMAP.md`](./ROADMAP.md) § "Por hacer (Fase D)" | ✅ Listo |
| Experiencia personal profesional adquirida | Bitácora del proyecto (commits, deploys, incidentes resueltos) + memoria del agente | ⚠️ **Narrativa personal pendiente** (Ángel debe escribir) |
| Competencias desarrolladas y/o aplicadas | [`docs/pendientes/proyecto_de_innovacion_digital_1.docx`](./pendientes/proyecto_de_innovacion_digital_1.docx) § "Justificación de pertinencia" | ✅ Listo (5 competencias: BD, ingeniería software, ciencia de datos, despliegue, documentación) |

**Total Conclusiones:** 15 pts + 3 pts (competencias).

**Trabajo pendiente crítico:**
1. **Narrativa personal** de Ángel (experiencia vivida, dificultades, aprendizajes)

---

### POST-RÚBRICA

| Sección | Puntos | Fuente | Estado |
|---|---|---|---|
| Fuentes de Información | 2 | [`docs/RESEARCH_SYNTHESIS.md`](./RESEARCH_SYNTHESIS.md) + [`docs/ARTICLES_INVENTORY.md`](./ARTICLES_INVENTORY.md) + papers tabulados en proyecto_innovacion doc | ✅ Listo (formato APA) |
| Glosario | — | Generar desde términos técnicos (Elo, xG, Platt, Brier, calibration, etc.) | ⚠️ Recopilar |
| Glosario de abreviaturas | — | Generar (API, BD, SQL, ORM, LLM, NLP, MDPI, etc.) | ⚠️ Recopilar |
| Anexos | — | | |
| → Manual de Instalación | — | Ver Cap 4.4 | (mismo) |
| → Manual Técnico | — | Ver Cap 4.4 | (mismo) |
| → Manual de Usuario | — | Ver Cap 4.4 | (mismo) |
| → Carta de autorización | — | Generar (modalidad de autor → no requiere) | ✅ N/A |
| → Registros de Productos | — | Repositorio GitHub público | ✅ Listo (URL del repo) |

---

## 🎯 Resumen de pendientes por sección

### Trabajo pesado (mucho tiempo)

1. **Diagramas UML** (Cap 2 + Cap 3):
   - Diagrama ER formal del schema v2
   - Diagrama de clases (backend + frontend)
   - Diagramas de casos de uso
   - Diagramas de secuencia (voto, pipeline, recalibración)
   - Diagramas de estado (predicción, voto)
   - Diagramas de actividades (pipeline diario)
   - Diagramas de componentes
   - Diagrama de despliegue UML formal
   - Diagramas de colaboración (multi-agente)
   - **Herramientas recomendadas:** PlantUML, Mermaid (Markdown), draw.io, Lucidchart

2. **Screenshots del prototipo** (Cap 4):
   - Home dashboard
   - Página de partido
   - Página de equipo
   - Calendario
   - Track record
   - Sistema de quinielas (voto individual + batch)
   - API healthcheck

3. **Manuales** (Cap 4):
   - Manual de instalación (paso a paso con screenshots)
   - Manual técnico (operación + mantenimiento + troubleshooting)
   - Manual de usuario (cómo usar la web, cómo votar, glosario)

### Trabajo mediano

4. **Lista formal de requerimientos** (Cap 3):
   - Requerimientos funcionales
   - Requerimientos no funcionales (performance, seguridad, usabilidad)

5. **Modelo de costos** (Cap 2 + Cap 3):
   - Costos de infraestructura (VPS, dominio)
   - Costos de APIs (SportMonks $X/mes)
   - Costo de tiempo de desarrollo (N horas × tarifa)
   - ROI (vs. costo de un analista humano equivalente)

6. **Plan de pruebas documentado** (Cap 3):
   - Tipos de pruebas (unitarias, integración, regresión, carga)
   - Estrategia (qué se prueba, cómo, con qué datos)
   - Resultados (257 tests passing, tiempo de ejecución)

7. **Decisión de metodología de desarrollo de software** (Cap 2):
   - Opciones: cascada, iterativo-incremental, ágil (Scrum/Kanban), XP
   - **Recomendación:** iterativo-incremental con fases claras (Fase 1-D ya documentadas en ROADMAP)
   - Justificar: la naturaleza del proyecto (predicción → calibración → despliegue) encaja con iterativo

### Trabajo liviano

8. **Bitácora consolidada del proyecto** (Cap 3):
   - Extraer de `git log --oneline` desde 2025-09
   - Organizar por fase
   - Destacar hitos (deploy Dokploy, merge frontend, recalibración, etc.)

9. **Narrativa personal** (Conclusiones):
   - Ángel debe escribir: dificultades, aprendizajes, momentos clave, satisfacción

10. **Glosarios** (Post-rúbrica):
    - Glosario técnico (Elo, xG, Brier, Platt, etc.)
    - Glosario de abreviaturas

---

## 📊 Resumen por puntaje de la rúbrica

| Sección | Puntos | % del total | Estado |
|---|---:|---:|---|
| Pre-rúbrica (portada, etc.) | 4 | 4% | 📝 Pendiente |
| Cap 1 — Generalidades | 25 | 25% | ✅ **Listo** (basado en proyecto_innovacion doc) |
| Cap 2 — Marco Teórico | 10 | 10% | ⚠️ **70% listo** (faltan UMLs + costos + metodología) |
| Cap 3 — Desarrollo | 5 | 5% | ⚠️ **30% listo** (faltan reqs formales + UMLs + interfaces + plan pruebas) |
| Cap 4 — Resultados | 45 | 45% | ⚠️ **70% listo** (faltan screenshots + manuales) |
| Conclusiones | 18 | 18% | ⚠️ **80% listo** (falta narrativa personal) |
| Post-rúbrica (fuentes, glosario) | 2 | 2% | ⚠️ **80% listo** (falta glosario) |
| **TOTAL** | **100** | 100% | ⚠️ **~65% listo** |

**Conclusión:** la base documental es sólida. Lo que falta es trabajo de **diagramación UML + manuales + screenshots**, que se puede paralelizar.

---

## 🛠️ Herramientas recomendadas

- **Diagramas UML:** PlantUML (texto → imagen), Mermaid (Markdown), draw.io, Lucidchart
- **Screenshots:** navegador + Lightshot / ShareX / GIMP
- **Redacción:** LaTeX (Overleaf) o Word — el proyecto_innovacion doc usa Word
- **Gestión de bibliografía:** Zotero (formato APA)
- **Edición de PDF/Docx:** LibreOffice (gratis) o Word

---

## 📅 Workflow sugerido

1. **Fase A (1-2 días):** generar todos los diagramas UML con PlantUML/Mermaid (insertarlos en `docs/UML/` o como sección nueva en `docs/`)
2. **Fase B (1 día):** tomar screenshots del prototipo y organizar en `docs/screenshots/`
3. **Fase C (2-3 días):** redactar los manuales (instalación, técnico, usuario) en formato académico
4. **Fase D (1 día):** escribir narrativa personal + decisión metodología + modelo de costos
5. **Fase E (1-2 días):** redactar Cap 1-4 del doc final en Word/LaTeX, citando los docs como bibliografía
6. **Fase F (1 día):** revisión final + corrección de estilo + bibliografía APA

**Total estimado:** 7-10 días de trabajo full-time.

---

## 📚 Ver también

- [`docs/RUBRICA_DE_ING._EN_SISTEMAS_2019.docx`](./RUBRICA_DE_ING._EN_SISTEMAS_2019.docx) — rúbrica completa
- [`docs/pendientes/proyecto_de_innovacion_digital_1.docx`](./pendientes/proyecto_de_innovacion_digital_1.docx) — proyecto de innovación (Cap 1 ya escrito)
- [`README.md`](../README.md) — overview del proyecto
- [`ARCHITECTURE.md`](../ARCHITECTURE.md) — arquitectura completa
- [`docs/ROADMAP.md`](./ROADMAP.md) — roadmap con todas las fases
- [`docs/METHODOLOGY.md`](./METHODOLOGY.md) — metodología del modelo
- [`docs/ARCHITECTURE_FRONTEND.md`](./ARCHITECTURE_FRONTEND.md) — frontend
- [`docs/QUINIELAS_SYSTEM.md`](./QUINIELAS_SYSTEM.md) — sistema de quinielas
- [`docs/DEPLOY_DOKPLOY.md`](./DEPLOY_DOKPLOY.md) — deploy Dokploy
- [`docs/SCHEMA_V2.md`](./SCHEMA_V2.md) — diseño BD
- [`docs/FEATURES.md`](./FEATURES.md) — catálogo de features
- [`docs/BACKTESTING_RESULTS.md`](./BACKTESTING_RESULTS.md) — métricas empíricas
- [`docs/RESEARCH_SYNTHESIS.md`](./RESEARCH_SYNTHESIS.md) — papers
- [`docs/ARTICLES_INVENTORY.md`](./ARTICLES_INVENTORY.md) — inventario bibliográfico
- [`docs/SOURCES_AUDIT.md`](./SOURCES_AUDIT.md) — auditoría de fuentes
