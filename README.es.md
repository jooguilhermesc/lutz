# Lutz

<p align="center">
  <img src="https://raw.githubusercontent.com/jooguilhermesc/lutz/main/lutz.png" alt="Lutz logo" width="160"/>
</p>

**Idiomas:** [English](README.md) | [Português](README.pt-BR.md) | **Español**

> Extracción validada para revisiones sistemáticas: cada celda de la tabla de extracción trae la cita, la página y un nivel de confianza medido, y un informe de confiabilidad listo para la sección de Métodos y el checklist PRISMA 2020.

![Version](https://img.shields.io/badge/Version-1.0.0a1-blueviolet)

Lutz 1.0 es una reescritura y no abre proyectos 0.5.x. Para seguir con 0.5: `pip install "lutz-research<1"`.

```bash
pip install --pre lutz-research
lutz init mi-revision && cd mi-revision
lutz load ~/articulos/
lutz codebook new
lutz codebook freeze
lutz extract
lutz report
lutz web
```

La interfaz y el informe están en portugués e inglés. Documentación completa: [README en inglés](README.md) y [especificación](docs/spec-1.0.md).

## Licencia

MIT
