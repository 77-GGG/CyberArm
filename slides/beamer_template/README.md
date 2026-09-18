# CaseStudy Beamer Template

A Beamer theme distilled from the visual logic of the supplied architectural case-study PDF.
It is intentionally **not** a pixel-level replica. The goal is to preserve the deck's core design language:

- 16:9 white canvas with unusually generous empty space;
- very small identification block in the upper-left;
- first line in black, architect/studio name in a restrained warm red;
- image-led pages with one dominant photograph and one or two supporting plans / drawings;
- asymmetrical but carefully aligned compositions;
- no decorative header/footer, no boxes, no shadows, no visible slide numbers;
- technical drawings can be pale / low-contrast while photographs remain visually dominant.

## Files

- `beamerthemeCaseStudy.sty` — reusable theme.
- `demo.tex` — six-slide working example.
- `demo.pdf` — compiled preview.
- `assets/` — self-generated placeholder images used only by the demo.

## Compile

Use **XeLaTeX**:

```bash
xelatex demo.tex
xelatex demo.tex
```

The theme defaults to `Noto Sans` + `Noto Sans CJK SC` for reliable XeLaTeX compilation.
The reference PDF itself is close to a `Calibri` + `Microsoft YaHei / DengXian` combination, so you can swap those font names in `beamerthemeCaseStudy.sty` when available.

## Fast usage

```tex
\documentclass[aspectratio=169,10pt]{beamer}
\usetheme{CaseStudy}
\graphicspath{{images/}}

\begin{document}

\CaseTitleSlide
  {CaseStudyTypos}{Museum 100 +}
  {Studio Wang Lu 2026}{School of Architecture, Tsinghua University}
  {Prof. Wang Lu}{TA: Wang Zijun}{202609}

\begin{caseframe}{大英博物馆}{Norman Foster}{ The British Museum 2000}
  \CaseImage{0.38cm}{1.50cm}{4.55cm}{small.jpg}
  \CaseImage{5.85cm}{1.50cm}{9.65cm}{hero.jpg}
\end{caseframe}

\end{document}
```

## Core positioning commands

All coordinates use the **top-left of the slide** as the origin.

```tex
\CaseImage{x}{y}{width}{file}
\CaseImageH{x}{y}{height}{file}
\CaseDrawing{x}{y}{width}{opacity}{file}
\CaseTextBlock{x}{y}{width}{text}
\CaseNote{x}{y}{width}{text}
\CaseKeyword{x}{y}{text}
```

For this theme, it is usually better to manually tune 2–4 image positions per slide than to force everything into a rigid grid. That looseness is part of the reference deck's character.
