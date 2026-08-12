# Contribuindo

Pull requests são bem-vindos. Para mudanças grandes, abra uma issue antes para
discutir o que você pretende alterar.

Antes de abrir o PR:

```bash
python -m unittest discover -s tests
python -m compileall battle_simulator tests
```

Convenção de idioma: o código-fonte mantém identificadores em inglês (`attack`,
`Soldier`, `BalancedBot`); documentação e interface web ficam em pt-BR.