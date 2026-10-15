# Contribuindo

Pull requests são bem-vindos. Para mudanças grandes, abra uma issue antes para
discutir o que você pretende alterar.

Antes de abrir o PR, rode o mesmo que o CI roda:

```bash
python -m pip install -e ".[dev,dashboard]"
ruff check src tests scripts
ruff format --check src tests scripts
python -m pytest
```

O executável do Windows sai do `build.ps1`, que precisa do extra `build`. O CI
gera e testa esse executável em todo push e PR. A release é publicada pelo
workflow quando uma tag `vX.Y.Z` é enviada, então não crie release à mão.
