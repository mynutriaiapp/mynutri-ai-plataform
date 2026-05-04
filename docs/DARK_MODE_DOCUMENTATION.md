# Sistema de Dark Mode — MyNutri AI

## 📋 Visão Geral

Foi implementado um sistema completo, profissional e acessível de **Dark Mode** na aplicação MyNutri AI. O sistema respeta as preferências do usuário e do sistema operacional, com transições suaves e sem dependências externas.

---

## ✨ Funcionalidades

### 1. **Botão Toggle Inteligente**
- Localizado no canto superior direito do header
- Ícone de **sol** quando o tema é escuro (indica mudança para claro)
- Ícone de **lua** quando o tema é claro (indica mudança para escuro)
- Animações suaves de rotação (200-300ms)
- Acessível via teclado e screen readers
- Hover effects intuitivos

### 2. **Persistência de Preferência**
- Salva a escolha do usuário em `localStorage` (chave: `mynutri_theme`)
- Restaura o tema ao recarregar a página
- Sincroniza entre abas do navegador

### 3. **Detecção de Preferência do Sistema**
```javascript
// Respeita prefers-color-scheme do SO
window.matchMedia('(prefers-color-scheme: dark)')
```
- Se o usuário não tiver salvo uma preferência, a aplicação detecta automaticamente
- Segue mudanças de tema do sistema operacional em tempo real

### 4. **Variáveis CSS Completas**
Criadas variáveis genéricas que mudam com o tema:
- `--bg-primary` — Background principal
- `--bg-secondary` — Background secundário
- `--text-primary` — Texto principal
- `--text-secondary` — Texto secundário
- `--border-color` — Cores de borda

Paletas completas para **luz** e **escuro**:
- Cores verdes adaptadas
- Neutros (cinzas) invertidos
- Gradientes remapeados
- Sombras aumentadas no dark mode

### 5. **Transições Suaves**
- Duração de **0.35s** para mudanças de cor
- Easing suave com `cubic-bezier(.16,1,.3,1)`
- Sem "flashes" ou mudanças abruptas

### 6. **Acessibilidade (WCAG)**
- ✅ `aria-label` no botão toggle
- ✅ Navegação por teclado (Enter/Space)
- ✅ Contraste WCAG AA+ em ambos os temas
- ✅ Feedback visual claro
- ✅ Suporte a screen readers

---

## 🎨 Implementação Técnica

### Estrutura CSS

**Modo Claro (padrão):**
```css
:root {
  --bg-primary:      #ffffff;
  --bg-secondary:    #f9fafb;
  --text-primary:    #1f2937;
  --text-secondary:  #6b7280;
  --border-color:    rgba(0,0,0,.06);
}
```

**Modo Escuro:**
```css
html.dark {
  --bg-primary:      #0f172a;
  --bg-secondary:    #1e293b;
  --text-primary:    #f8fafc;
  --text-secondary:  #cbd5e1;
  --border-color:    rgba(255,255,255,.08);
}
```

### Aplicação da Classe

A classe `.dark` é adicionada ao elemento `<html>`:
```html
<html class="dark">  <!-- Dark mode ativo -->
```

Quando removida, o tema volta ao claro.

### JavaScript

Sistema auto-inicializável em Immediately Invoked Function Expression (IIFE):

```javascript
(function() {
  const THEME_KEY = 'mynutri_theme';
  const html = document.documentElement;

  // Prioridade: localStorage > system preference > light mode
  function initializeTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) {
      setTheme(saved);
    } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
      setTheme('dark');
    } else {
      setTheme('light');
    }
  }

  function setTheme(theme) {
    if (theme === 'dark') {
      html.classList.add('dark');
      localStorage.setItem(THEME_KEY, 'dark');
    } else {
      html.classList.remove('dark');
      localStorage.setItem(THEME_KEY, 'light');
    }
  }

  initializeTheme();
  // ... listeners
})();
```

---

## 🎯 Elementos Suportados

### Componentes com Dark Mode:

- ✅ Header e navbar
- ✅ Hero section
- ✅ Cards e containers
- ✅ Buttons (primary, secondary, outline)
- ✅ Forms e inputs
- ✅ Breadcrumbs e links
- ✅ Shadows e gradientes
- ✅ Footer
- ✅ Modais e dropdowns
- ✅ Tipografia
- ✅ Ícones SVG

---

## 📱 Páginas Implementadas

Todas as páginas suportam dark mode:

- ✅ `index.html` — Página inicial (landing)
- ✅ `auth.html` — Login/Signup
- ✅ `dieta.html`
- ✅ `perfil.html`
- ✅ `questionario.html`
- ✅ `contato.html`
- ✅ `termos.html`
- ✅ `privacidade.html`

O sistema reutiliza o mesmo CSS em todas as páginas.

---

## 🔧 Como Usar

### Para o Usuário Final:
1. Clique no ícone de **lua/sol** no header
2. O tema muda instantaneamente
3. A preferência é salva automaticamente

### Para Desenvolvedores:

**Adicionar estilo em dark mode:**
```css
html.dark .elemento {
  color: var(--text-primary);
  background: var(--bg-secondary);
}
```

**Usar variáveis genéricas (recomendado):**
```css
.meu-elemento {
  color: var(--text-primary);
  background: var(--bg-primary);
  transition: background-color var(--duration) ease;
}
```

**Verificar tema via JavaScript:**
```javascript
const isDark = document.documentElement.classList.contains('dark');
```

**Alterar tema via JavaScript:**
```javascript
function setTheme(theme) {
  if (theme === 'dark') {
    document.documentElement.classList.add('dark');
    localStorage.setItem('mynutri_theme', 'dark');
  } else {
    document.documentElement.classList.remove('dark');
    localStorage.setItem('mynutri_theme', 'light');
  }
}
```

---

## 🎨 Paleta de Cores

### Luz (Light Mode)

| Uso | Cor |
|-----|-----|
| Background primário | `#ffffff` |
| Background secundário | `#f9fafb` |
| Texto primário | `#1f2937` (gray-800) |
| Texto secundário | `#6b7280` (gray-500) |
| Borda | `rgba(0,0,0,.06)` |
| Verde primário | `#22c55e` |

### Escuro (Dark Mode)

| Uso | Cor |
|-----|-----|
| Background primário | `#0f172a` |
| Background secundário | `#1e293b` |
| Texto primário | `#f8fafc` (gray-800 invertido) |
| Texto secundário | `#cbd5e1` (gray-500 invertido) |
| Borda | `rgba(255,255,255,.08)` |
| Verde primário | `#22c55e` (mantido para destaque) |

---

## 🔄 Fluxo de Inicialização

```
┌─────────────────────────────────────────┐
│  Página carrega                         │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  Script de Dark Mode executa (IIFE)     │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────────────────┐
│  Verifica localStorage.getItem('mynutri_theme')       │
└────────────────┬────────────────────────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
    [SIM]            [NÃO]
      │                │
      │                ▼
      │        Verifica window.matchMedia
      │        ('prefers-color-scheme: dark')
      │                │
      │         ┌──────┴──────┐
      │         │             │
      │         ▼             ▼
      │      [SIM]       [NÃO]
      │       │            │
      │       │            ▼
      │       │         Light (padrão)
      │       │            │
      │       ▼            │
      │     Dark           │
      │       │            │
      └───────┴────────┬───┘
                       │
                       ▼
        ┌──────────────────────────────────┐
        │  setTheme() aplica classe .dark  │
        │  ao html + salva em localStorage │
        └──────────────────────────────────┘
```

---

## ⚙️ Configuração Avançada

### Mudar cor de transição:
```css
:root {
  --duration: 0.5s; /* Era 0.35s */
}
```

### Desabilitar transições:
```css
html.dark * {
  transition: none !important;
}
```

### Forçar modo escuro:
```javascript
setTheme('dark');
```

### Forçar modo claro:
```javascript
setTheme('light');
```

### Limpar preferência (volta a usar sistema):
```javascript
localStorage.removeItem('mynutri_theme');
location.reload();
```

---

## 📊 Performance

- ✅ **Sem dependências externas** — JavaScript puro
- ✅ **Transições GPU-aceleradas** — Suave em todos os dispositivos
- ✅ **Sem FOUC** (Flash of Unstyled Content) — Script roda antes do render
- ✅ **localStorage otimizado** — Leitura rápida
- ✅ **CSS otimizado** — Variáveis compiladas

---

## 🐛 Troubleshooting

### Tema não persiste
**Solução:** Verificar se localStorage está habilitado no navegador.
```javascript
console.log(localStorage.getItem('mynutri_theme'));
```

### Transições muito lentas
**Solução:** Reduzir `--duration` em `:root`.

### Brilho incorreto no dark mode
**Solução:** Verificar se há estilos inline que sobrescrevem variáveis CSS.

### Sistema operacional muda, aplicação não acompanha
**Solução:** Limpar localStorage para reativar detecção automática.
```javascript
localStorage.removeItem('mynutri_theme');
```

---

## 📝 Checklist de Qualidade

- ✅ Acessibilidade WCAG AA
- ✅ Transições suaves (200-300ms)
- ✅ Persistência com localStorage
- ✅ Detecção de preferência do sistema
- ✅ Sem dependências externas
- ✅ Contraste adequado (4.5:1 mínimo)
- ✅ Suporte a todas as páginas
- ✅ Navegação por teclado
- ✅ Sem FOUC
- ✅ Performance otimizada

---

## 🎓 Referências

- [MDN: prefers-color-scheme](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-color-scheme)
- [WCAG: Color Contrast](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html)
- [CSS Variables](https://developer.mozilla.org/en-US/docs/Web/CSS/--*)
- [localStorage API](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage)

---

**Desenvolvido com ❤️ para MyNutri AI**
