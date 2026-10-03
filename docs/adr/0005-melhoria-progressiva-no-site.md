# Melhoria progressiva no site: JS puro, sem framework e sem build

A tabela do Ranking pode ser melhorada no navegador — busca, ordenação, filtros e paginação — com um único asset JavaScript vanilla (`assets/app.js`), carregado com `defer`. O HTML continua completo e funcional sem JS: o script só acrescenta controles sobre o que já veio renderizado, e nunca recalcula regra de negócio.

Isso não revoga o [ADR-0003](0003-sem-backend-no-mvp.md): continua não havendo SPA, framework de front-end nem etapa de build; o site segue estático, lendo apenas os dados derivados em JSON. A alternativa — trazer um framework ou um bundler — foi rejeitada por custo de manutenção desproporcional ao problema, que é só de apresentação. Um leitor futuro que veja JavaScript aqui deve tratá-lo como melhoria progressiva deliberada, não como migração para uma SPA.
