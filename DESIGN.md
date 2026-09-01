---
name: Player Feedback
description: Sistema visual Databricks para análise reutilizável de feedback de jogos mobile.
colors:
  brand-red: "#FF3621"
  brand-red-deep: "#D62C1A"
  brand-red-soft: "#FFF0ED"
  lakehouse-ink: "#1B3139"
  deep-slate: "#10272F"
  workspace-canvas: "#F7F8FA"
  surface: "#FFFFFF"
  divider: "#DCE0E2"
  muted: "#5D6B72"
  success: "#227A52"
  warning: "#A86403"
  danger: "#C1352B"
typography:
  headline:
    fontFamily: "Aptos, Segoe UI Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  body:
    fontFamily: "Aptos, Segoe UI Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Aptos, Segoe UI Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.4
rounded:
  control: "8px"
  icon: "12px"
  surface: "16px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.brand-red}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.brand-red-deep}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.lakehouse-ink}"
    rounded: "{rounded.surface}"
    padding: "24px"
---

# Design System: Player Feedback

## Overview

**Creative North Star: "The Lakehouse Workspace"**

O sistema traduz a identidade de produto Databricks para uma solução analítica reutilizável: superfícies claras, densidade controlada, tipografia direta e vermelho reservado para marca, orientação e ações importantes. A experiência deve parecer nativa de um workspace de dados sem alterar a arquitetura de informação, os textos ou os fluxos existentes.

A antiga linguagem editorial associada à Wildlife foi removida. O design privilegia confiança, operação e leitura comparativa; expressão visual aparece na faixa analítica escura, no ritmo das superfícies e no uso preciso da cor de marca.

**Key Characteristics:**

- Estrutura original preservada: resumo, comparação e detalhe.
- Superfícies brancas sobre canvas cinza frio.
- Vermelho Databricks usado com parcimônia.
- Estados comunicados por cor, texto e forma.
- Densidade confortável para demonstração e trabalho recorrente.

## Colors

A paleta combina o vermelho Databricks com neutros frios inspirados no workspace e cores semânticas acessíveis.

### Primary

- **Databricks Red** (`#FF3621`): ações primárias, foco de marca e seleção ativa.
- **Databricks Deep Red** (`#D62C1A`): estado hover da ação primária.
- **Databricks Soft Red** (`#FFF0ED`): fundo de mensagens de erro sem saturar a tela.

### Neutral

- **Lakehouse Ink** (`#1B3139`): texto principal e ícones.
- **Deep Slate** (`#10272F`): superfície analítica de alto contraste.
- **Workspace Canvas** (`#F7F8FA`): fundo da aplicação.
- **Surface White** (`#FFFFFF`): controles e superfícies de conteúdo.
- **Divider Gray** (`#DCE0E2`): divisores e bordas estruturais.
- **Muted Slate** (`#5D6B72`): texto secundário.

### Named Rules

**The Red Means Direction Rule.** O vermelho orienta marca, ação ou seleção; nunca colore dados sem significado.

## Typography

**Display Font:** Aptos, com Segoe UI Variable e fontes de sistema como fallback.
**Body Font:** A mesma família para continuidade e clareza operacional.

**Character:** Contemporânea, neutra e precisa. A hierarquia vem de peso, tamanho e espaço, não de caixa alta decorativa ou itálico editorial.

### Hierarchy

- **Headline** (600, 24px, 1.25): títulos de página e entidades selecionadas.
- **Title** (600, 18–20px): títulos de seção e superfície.
- **Body** (400, 14–15px, 1.6): explicações, relatórios e conteúdo operacional.
- **Label** (600, 12–14px): controles, metadados e estados.

### Named Rules

**The Quiet Hierarchy Rule.** Use peso e proximidade antes de caixa alta ou espaçamento entre letras.

## Layout

O container principal tem largura máxima de 1280px, padding de 24px e blocos verticais separados por 48px. A composição original é preservada: indicadores agregados em linha, comparação entre jogos em grade e detalhe do jogo selecionado abaixo. Grades se tornam coluna única em telas menores.

## Elevation & Depth

O sistema é plano por padrão. Profundidade vem da diferença tonal entre canvas e superfícies, com bordas de 1px. Sombra aparece somente na aba ativa da navegação para indicar elevação funcional.

## Shapes

Controles usam raio de 8px, ícones e avatares usam 12px e superfícies principais usam 16px. Chips de estado podem ser totalmente arredondados por serem elementos pequenos e compactos. Bordas são finas e neutras; seleção pode trocar a borda neutra pela cor de marca.

## Components

### Buttons

- **Primary:** fundo vermelho, texto branco, raio de 8px e peso 600.
- **Secondary:** superfície branca com borda neutra; no hover, borda e texto adotam vermelho.
- **Focus:** anel vermelho translúcido de 3px com offset.
- **Disabled:** mantém estrutura e reduz opacidade.

### Surfaces / Containers

- **Corner Style:** superfícies de conteúdo permanecem retas; raios ficam concentrados em controles e ícones.
- **Background:** branco e cinza frio alternam para separar conteúdo sem criar cartões adicionais.
- **Shadow Strategy:** sem sombra em repouso.
- **Border:** 1px Divider Gray.
- **Internal Padding:** preserva os espaçamentos definidos pela composição original.

### Inputs / Fields

- **Style:** fundo branco, borda neutra, raio de 8px e altura confortável para operação.
- **Focus:** borda vermelha e anel global visível.

### Navigation

A navegação fica em um trilho cinza claro. A aba ativa usa superfície branca, texto escuro e sombra discreta; abas inativas usam texto secundário. Cada item combina ícone Lucide e rótulo textual.

### Sentiment Composition Bar

Barra horizontal segmentada e arredondada. Verde, cinza, âmbar e vermelho representam sentimento positivo, neutro, misto e negativo; a legenda textual é obrigatória para não depender apenas de cor.

## Do's and Don'ts

### Do:

- **Do** contextualize KPIs com unidade, fonte e atualização.
- **Do** use vermelho para ação, seleção e identidade.
- **Do** mantenha estados vazios e erros com orientação de recuperação.
- **Do** preserve a leitura comparativa entre jogos.

### Don't:

- **Don't** reintroduza a tipografia condensada, itálica e editorial da identidade anterior.
- **Don't** use vermelho como preenchimento decorativo em grandes áreas.
- **Don't** comunique saúde ou sentimento apenas pela cor.
- **Don't** transforme seções existentes em cartões ou altere sua disposição para aplicar a marca.
