document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;

  const confirmation = form.dataset.confirm;
  if (confirmation && !window.confirm(confirmation)) {
    event.preventDefault();
    return;
  }

  const loadingLabel = form.dataset.loading;
  if (!loadingLabel) return;
  const button = form.querySelector("button[type='submit']");
  if (!(button instanceof HTMLButtonElement) || button.disabled) {
    event.preventDefault();
    return;
  }
  button.disabled = true;
  button.dataset.originalLabel = button.textContent || "";
  button.textContent = loadingLabel;
});

// --- Apoio ao preenchimento do IP ----------------------------------------
// A correção e o teste consultam o servidor em vez de reimplementar a regra
// aqui: assim o que a página avisa nunca discorda do que será salvo.

const ipForm = document.querySelector("[data-ip-check]");
if (ipForm) {
  const campoIp = ipForm.querySelector("[data-ip-field]");
  const aviso = ipForm.querySelector("[data-ip-feedback]");
  const botaoTeste = ipForm.querySelector("[data-ip-test]");
  const statusTeste = ipForm.querySelector("[data-test-status]");
  const csrf = ipForm.dataset.csrf || "";

  const consultar = (rota, ip) => {
    const corpo = new URLSearchParams({ ip, _csrf_token: csrf });
    return fetch(rota, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: corpo,
    }).then((resposta) => resposta.json());
  };

  const definirAviso = (texto, estado) => {
    aviso.textContent = texto;
    aviso.className = estado ? `field-hint ${estado}` : "field-hint";
  };

  let pendente;
  campoIp.addEventListener("input", () => {
    clearTimeout(pendente);
    definirAviso("", null);
    const valor = campoIp.value.trim();
    if (valor.length < 7) return;
    pendente = setTimeout(() => {
      consultar("/api/normalizar-ip", valor)
        .then((r) => {
          if (r.ok && r.ip !== valor) definirAviso(`Será salvo como ${r.ip}`, "is-ok");
          else if (!r.ok) definirAviso(r.erro, "is-error");
        })
        .catch(() => {});
    }, 350);
  });

  // Ao sair do campo, grava o IP já corrigido para o usuário ver o resultado.
  campoIp.addEventListener("blur", () => {
    const valor = campoIp.value.trim();
    if (!valor) return;
    consultar("/api/normalizar-ip", valor)
      .then((r) => {
        if (r.ok) campoIp.value = r.ip;
      })
      .catch(() => {});
  });

  const preencherSeVazio = (campo, valor) => {
    const alvo = ipForm.querySelector(`[data-fill='${campo}']`);
    if (alvo && !alvo.value && valor) alvo.value = valor;
  };

  botaoTeste.addEventListener("click", () => {
    const valor = campoIp.value.trim();
    if (!valor) {
      campoIp.focus();
      return;
    }
    botaoTeste.disabled = true;
    statusTeste.className = "section-note";
    statusTeste.textContent = `Consultando ${valor}…`;
    consultar("/api/testar", valor)
      .then((r) => {
        botaoTeste.disabled = false;
        if (r.ip) campoIp.value = r.ip;
        if (!r.ok) {
          statusTeste.className = "section-note is-error";
          statusTeste.textContent = r.erro || "Não respondeu.";
          return;
        }
        statusTeste.className = "section-note is-ok";
        const contador =
          r.contador !== null && r.contador !== undefined
            ? ` — contador em ${r.contador.toLocaleString("pt-BR")} páginas`
            : "";
        statusTeste.textContent = `Respondeu: ${r.nome || "equipamento encontrado"}${contador}`;
        // Preenche o que estiver vazio com o que o equipamento informou.
        preencherSeVazio("nome", r.nome);
        preencherSeVazio("modelo", r.modelo);
        preencherSeVazio("serie", r.serie);
        preencherSeVazio("local", r.local);
      })
      .catch(() => {
        botaoTeste.disabled = false;
        statusTeste.className = "section-note is-error";
        statusTeste.textContent = "Não foi possível testar agora.";
      });
  });
}
