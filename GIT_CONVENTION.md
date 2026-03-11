# Git Convention

Para manter o histórico do projeto organizado, usamos o padrão **Conventional Commits**.

## Formato do commit

Todos os commits devem seguir este formato:

```
tipo: descrição curta da mudança
```

Exemplo:

```
feat: cria questionario nutricional
fix: corrige cálculo de macros
docs: adiciona documentação da API
```

## Tipos de commits

**feat**
Nova funcionalidade no projeto.

```
feat: cria questionario nutricional
feat: implementa geração de dieta com IA
```

**fix**
Correção de bugs ou erros.

```
fix: corrige cálculo de macros
fix: resolve erro no login
```

**docs**
Mudanças apenas na documentação.

```
docs: adiciona documentação da API
docs: atualiza README
```

**refactor**
Melhoria ou reorganização do código sem mudar o funcionamento.

```
refactor: reorganiza serviços de autenticação
refactor: melhora estrutura das rotas
```

## Boas práticas

* use mensagens **curtas e claras**
* escreva em **minúsculo**
* cada commit deve representar **uma mudança específica**
