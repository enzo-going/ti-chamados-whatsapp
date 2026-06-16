# Registro de decisões

Documento curto explicando as escolhas principais do projeto.

## 1. Projeto próprio em Python em vez de adaptar o fork do WhaTicket

**Contexto:** existe um fork de `whaticket-community` (Node.js/TypeScript + React +
MySQL) que resolve um problema parecido (WhatsApp → tickets, multi-atendente).

**Decisão:** construir um projeto próprio em Python.

**Por quê:**
- **Peso de portfólio.** Um fork aparece como "forked from..." e mostra pouco
  trabalho autoral. Um projeto próprio demonstra design e decisões minhas.
- **Stack.** Meu portfólio é majoritariamente Python; o WhaTicket é TS/JS/React.
  Manter coerência com o resto do perfil é mais forte do que carregar uma stack
  que não é a minha.
- **Escopo.** O WhaTicket é uma plataforma grande (755+ commits). Para o caso do
  setor de TI (helpdesk interno) eu não preciso de tudo aquilo — um núcleo enxuto
  e bem testado atende melhor e é viável de manter sozinho.
- **Risco de ToS.** O WhaTicket usa `whatsapp-web.js` (cliente não-oficial), que
  pode resultar em bloqueio da conta. Projetando com transporte plugável, posso
  usar a **Cloud API oficial** quando for integrar.

**O WhaTicket continua útil** como referência conceitual (ex.: a regra de reabrir
o último chamado quando a mesma pessoa escreve em seguida veio de lá).

## 2. Transporte de mensagens como interface plugável

O serviço depende de `MessagingTransport`, não de uma biblioteca de WhatsApp.
Em testes/demonstração uso `FakeTransport`. Isso mantém a regra de negócio 100%
testável e adia a integração real (que envolve credenciais e produção) sem
travar o desenvolvimento.

## 3. Triagem por palavras-chave (por enquanto)

Comecei com classificação por palavras-chave porque é transparente, rápida e sem
dependências — fácil de revisar e de explicar. A função está isolada em
`triage.py` para poder ser trocada por um modelo de ML/NLP depois sem afetar o
resto do sistema.

## 4. Repositório em memória primeiro

A persistência é uma interface (`TicketRepository`) com uma implementação em
memória. Quando fizer sentido, entra SQLite/SQLAlchemy (stack que já uso em
outros projetos) sem alterar o serviço.

> Concretizado na **Fase 1** — ver decisão 5 e o [roadmap](roadmap.md).

## 5. Persistência SQLite (Fase 1 — implementada em 2026-06-08)

A interface já previa SQLite (decisão 4); a Fase 1 a tornou real com
`SqliteTicketRepository`, **sem alterar a regra de negócio** — o serviço continua
falando apenas com o `Protocol`. Escolhas:

- **`sqlite3` da biblioteca padrão, não SQLAlchemy.** O modelo é praticamente uma
  entidade (`Ticket`); um ORM seria peso sem ganho agora. Mantém o projeto sem
  dependências de runtime. A interface continua permitindo migrar para SQLAlchemy
  depois, se a complexidade crescer.
- **Write-back explícito (`update()`).** O repositório em memória "enxergava" as
  mutações do `Ticket` por compartilhar a referência do objeto; uma persistência
  real não. Por isso o contrato ganhou `update()` e o serviço passou a chamá-lo
  após cada mutação (atribuição, reabertura, início, resolução, fechamento). Isso
  completa o padrão Repository sem acoplar o domínio ao banco.
- **`next_id()` via `MAX(id) + 1`.** Mantém o contrato (id conhecido antes do
  insert) e é naturalmente persistente: IDs não colidem após reinício. Como
  chamados nunca são apagados, não há risco de reuso de id.
- **Datas em ISO 8601 (UTC); histórico em JSON.** Para timestamps UTC a ordem
  lexicográfica coincide com a cronológica, então a busca pelo último chamado
  fechado usa `ORDER BY closed_at` diretamente.

**Deferido de propósito (não é dívida esquecida):** o estado do rodízio
(`round-robin`) continua em memória. Persisti-lo exigiria mover estado do
*serviço* para o *repositório* — uma decisão de design que prefiro discutir antes
de tomar. O efeito de não persistir é apenas cosmético (após um restart a
distribuição entre atendentes pode recomeçar do primeiro); não há perda de dados.
Registrado no [roadmap](roadmap.md).

## 6. Categoria de triagem para empréstimo de equipamento

Adicionada a categoria `emprestimo_equipamento` (nome público: **empréstimo de
equipamento**) para solicitações de notebook de apoio do setor de TI.

**Ambiguidade tratada:** "notebook" já era gatilho de `hardware` (equipamento com
defeito). Para distinguir *solicitar* de *defeito*, a categoria usa **gatilhos por
frase** ("preciso de um notebook", "notebook emprestado", "reserva de notebook",
"notebook para reunião", "equipamento temporário"…) e fica **antes de `hardware`**
na ordem de classificação. Assim, frases de solicitação vencem, enquanto
"meu notebook não liga" continua em `hardware`. Há teste de regressão garantindo
esse comportamento, além de um teste que verifica que toda categoria tem rótulo
público em `replies.py`.

## 7. Entrada local e idempotente (início da Fase 2)

A Fase 2 começou por uma **camada de entrada local e testável**, sem qualquer
integração externa real (sem WhatsApp, sem Cloud API, sem webhook público).

- **Payload neutro.** `helpdesk/inbound.py` define um formato JSON genérico
  (`event_id`, `sender`, `text`, `sender_name?`, `timestamp?`), independente de
  plataforma. `parse_payload()` valida e converte em `Message`; o `MessageGateway`
  encaminha ao serviço. Assim, a borda real (Fase 3) só precisará traduzir o
  formato dela para esse payload.
- **Idempotência persistente.** Entregas "pelo menos uma vez" são comuns, então o
  mesmo evento pode chegar repetido. Cada `event_id` processado é registrado na
  tabela `processed_events` (SQLite); uma reentrega devolve o chamado existente,
  sem duplicar. Sobrevive a reinícios. O schema subiu para a versão 2 (criação
  idempotente via `IF NOT EXISTS`).
- **Servidor HTTP local.** `helpdesk/http_app.py` (biblioteca padrão) liga apenas
  em `127.0.0.1`, para exercitar a entrada de ponta a ponta com payloads próprios.
  Não é exposto à internet.

**Pendente nesta frente:** anexar follow-up a um chamado **aberto** (hoje uma nova
mensagem de chamado aberto ainda abre outro) e o transporte/borda reais, que
dependem das decisões da Fase 3.

## 8. Wallboard da sala de TI (consideração de produto)

Há a possibilidade (ainda não confirmada) de exibir os chamados numa TV na sala
de TI. Direção registrada para orientar o design futuro:

- **Painel interno somente leitura, com atualização automática**, em vez de
  deixar o WhatsApp Web aberto na TV — mais profissional, controlável e seguro.
- **Mínimo de dados, foco operacional:** número, categoria, prioridade, status,
  responsável e tempo em aberto.
- **Privacidade:** não expor telefone, texto completo das mensagens, nomes
  desnecessários nem dados sensíveis. Tecnicamente, o wallboard consumiria uma
  **projeção restrita** do `Ticket` (apenas os campos acima), não o objeto
  inteiro — mantendo a separação entre dados internos e a tela exibida.

Sem implementação por enquanto (apenas documentação). Tende a se apoiar na Fase 4
(interface de atendentes) e/ou na Fase 5 (observabilidade).

## 9. Follow-up em chamado aberto

Quando a mesma pessoa continua escrevendo sobre o mesmo problema, a mensagem é
**anexada ao chamado aberto** em vez de abrir outro — evitando duplicação.

- O serviço busca o chamado **aberto** mais recente do remetente (`last_open_for`)
  e anexa a mensagem ao histórico se a última atividade estiver dentro da **mesma
  janela de continuidade** usada na reabertura (comparada com `updated_at`). Fora
  da janela, trata como assunto novo e abre outro chamado.
- O follow-up **não reatribui** o chamado (mantém o responsável) e **não muda o
  status**; apenas registra a mensagem e desliza a janela.
- Ordem em `handle_message`: follow-up (aberto) → reabertura (fechado recente) →
  novo chamado.

Interação com a idempotência: a deduplicação por `event_id` continua valendo
antes de tudo, então a reentrega do mesmo evento nunca chega a virar follow-up.

## 10. Atendentes: papéis genéricos e cadastro configurável (futuro)

O repositório é público, então os arquivos **não** registram nomes reais de
funcionários: os atendentes de exemplo usam papéis genéricos ("Atendente 1"…).

Como a equipe tem rotatividade, o quadro **não deve ser fixado no código**. Fica
previsto (futuro) um cadastro configurável de atendentes, com estado
**ativo/inativo** (apenas ativos entram no rodízio) e **papéis/cargos**.

> Implementado — ver decisão 11.

## 11. Quadro de atendentes configurável (JSON local)

Concretiza a decisão 10: o quadro de atendentes sai do código e vira um
**arquivo JSON local** (`helpdesk/attendants.py`), apontado por
`HELPDESK_ATTENDANTS_PATH` — seguindo o mesmo padrão de configuração por
variável de ambiente do banco (`config.py`). Escolhas:

- **JSON puro, sem dependências.** Uma lista de objetos com `id`, `name`,
  `role` (opcional; padrão `"atendente"`) e `active` (opcional; padrão `true`).
  O formato está versionado em `atendentes.exemplo.json`; o arquivo real
  (`atendentes.json`) está no `.gitignore`, porque pode conter nomes reais e o
  repositório é público.
- **Papel é texto livre, não enum.** Os cargos variam com a rotatividade da
  equipe (supervisor, efetivo, estagiário, aprendiz, suporte…); um enum exigiria
  mudança de código a cada cargo novo, contrariando o objetivo da decisão.
- **Validação estrita, falha alta.** Campo desconhecido é erro (um typo como
  `"ativo"` em vez de `"active"` deixaria alguém no rodízio sem querer), assim
  como id duplicado, quadro vazio ou tipos errados. E se há um caminho
  configurado, o arquivo é obrigatório: erro de leitura interrompe a
  inicialização em vez de cair silenciosamente no quadro de exemplo.
- **Fallback genérico para demo/testes.** Sem configuração, entra um quadro de
  exemplo com papéis genéricos ("Atendente 1"… — nunca nomes reais).
- **Só ativos no rodízio; chamado guarda o responsável.** O serviço valida que
  há ao menos um atendente ativo e atribui novos chamados apenas entre ativos.
  O chamado persiste a própria referência do responsável (id + nome), então
  inativar alguém **não altera** chamados já atribuídos — afeta somente novas
  atribuições. Papel e atividade são propriedades do **quadro**, não do chamado.
- **Quadro fixo por instância (sem recarga em runtime).** Mudanças no arquivo
  são aplicadas ao reiniciar o processo — suficiente para o volume atual.
  Recarga dinâmica fica para a interface de atendentes (Fase 4), se necessária.

**Continua deferido:** o ponteiro do rodízio (round-robin) segue em memória,
como na decisão 5 — após um reinício a distribuição recomeça do primeiro ativo.
Persisti-lo continua sendo uma decisão futura, agora com um motivo a mais para
ser revisitada junto da Fase 4 (a ordem do rodízio passa a depender do arquivo
de quadro).

## 12. Painel local somente leitura (base do wallboard)

Primeira concretização da direção registrada na decisão 8: uma página HTML em
``/dashboard``, servida pelo servidor HTTP local já existente
(`helpdesk/http_app.py`), listando os chamados em aberto. Escolhas:

- **Projeção restrita como código, não como convenção.** `helpdesk/dashboard.py`
  define um `PanelRow` (dataclass congelada) com exatamente os campos
  operacionais — número, categoria, prioridade, status, responsável, horário de
  abertura e tempo em aberto. Telefone, nome do solicitante, assunto e
  histórico **não passam pela projeção**, então não têm como chegar à página.
  Um teste fixa a lista de campos: adicionar dado novo ao painel exige mudança
  consciente no contrato.
- **Aproveita o servidor existente, stdlib pura.** Nada de framework ou
  dependência nova: rota `GET /dashboard` no `http.server` local, HTML gerado
  por template de string com `html.escape` em todo valor dinâmico (há teste de
  escape). Continua ligado apenas a `127.0.0.1`.
- **Sem autenticação, por ser local de desenvolvimento.** Documentado como
  painel de desenvolvimento, não de produção. Quando o wallboard real (TV)
  for confirmado, acesso e exposição serão revisitados junto das Fases 4/5.
- **Atualização simples.** `<meta http-equiv="refresh">` a cada 15s — suficiente
  para um painel de parede, sem JavaScript nem polling sofisticado.
- **Ordenação operacional.** Prioridade alta primeiro; dentro da mesma
  prioridade, o mais antigo primeiro (quem espera há mais tempo aparece no topo).

O responsável é exibido só pelo **nome** (sem papel/cargo), seguindo o princípio
de mínimo de dados da decisão 8; o papel pode entrar depois se houver uso real.

## 13. Servidor local com threads e acesso serializado ao SQLite

**Contexto (bug real da demonstração):** com o painel aberto no navegador, o
`demo send` estourava timeout de forma intermitente — e o evento ainda era
processado depois, fora de hora. Causa raiz: o servidor usava o ``HTTPServer``
de **thread única** da stdlib, e navegadores mantêm conexões TCP abertas sem
enviar nada (keep-alive/preconnect especulativo). Uma única conexão ociosa
ocupava o servidor inteiro; os POSTs ficavam na fila até o cliente desistir.

**Decisão:** trocar para ``ThreadingHTTPServer`` (uma thread daemon por
conexão), com duas salvaguardas:

- **Um ``Lock`` no handler serializa o trabalho real** (serviço + banco). As
  threads existem só para que conexões ociosas não bloqueiem ninguém — o
  volume de um helpdesk interno não pede paralelismo de verdade, e serializar
  evita qualquer corrida no serviço.
- **SQLite com ``check_same_thread=False``, por opt-in explícito**
  (``SqliteTicketRepository(..., allow_cross_thread=True)``). A conexão passa a
  ser usada pelas threads de requisição; o lock acima garante um uso por vez.
  O padrão continua estrito para os demais usos.

Um teste de regressão fixa o cenário: com uma conexão ociosa aberta, um POST
deve responder normalmente. O CLI da demonstração também passou a tratar erros
de conexão com mensagem curta e orientação (sem traceback em uso normal).

## 14. Borda da integração de mensagens (Cloud API), testável sem rede

Concretização da Fase 3 **sem conectar nada**: `helpdesk/whatsapp.py` implementa
as peças que a integração oficial exige, todas exercitadas por testes com HTTP
fake e sem credenciais. Escolhas:

- **API oficial (Cloud API), não cliente não-oficial.** Baileys/whatsapp-web.js
  e similares violam os termos e arriscam banir o número; a Cloud API é a via
  suportada. A contrapartida (janela de 24h, formato de payload) é aceita.
- **Recebimento separado em três responsabilidades puras:** verificação do
  webhook (`verify_webhook`, handshake GET com comparação de token em tempo
  constante), validação de assinatura (`valid_signature`, HMAC-SHA256 do corpo
  bruto) e conversão (`extract_inbound_payloads`, payload da plataforma →
  payload neutro do `/inbound`). Cada uma é função pura, testável isolada.
- **Reaproveita a idempotência existente:** o id da mensagem da plataforma vira
  o `event_id`, então reentregas (a plataforma garante "ao menos uma vez") não
  duplicam chamado. Recibos de status e tipos não-texto são ignorados com um
  **motivo** (nunca com conteúdo), e o webhook responde 200 mesmo assim —
  formato que a plataforma espera para não reentregar.
- **Envio como `CloudApiTransport` com HTTP injetável.** A função HTTP entra
  pelo construtor: testes passam um fake e nenhuma chamada externa acontece. O
  token só entra no cabeçalho `Authorization` e nunca aparece em `repr`/erros.
- **Fail closed.** As rotas `/webhook` respondem 503 sem `WHATSAPP_VERIFY_TOKEN`/
  `WHATSAPP_APP_SECRET`, e 403 sem assinatura válida. O envio real só é ativado
  por `--transport cloud-api`, que exige as variáveis e falha citando apenas os
  **nomes** ausentes. O servidor continua ligado só em `127.0.0.1`; a exposição
  pública (túnel HTTPS) é decisão à parte, fora do código.
- **Escopo consciente — janela de 24h.** Hoje todo envio é **reativo** (resposta
  a uma mensagem recebida), portanto sempre dentro da janela de 24h da
  plataforma; não há, por ora, tratamento de *templates* para envio ativo fora
  da janela. Quando houver mensagem proativa (ex.: notificar prioridade alta),
  isso entra junto.

A conexão real continua **bloqueada por decisão** (estratégia do número); o
roteiro do dia da validação está em [pré-integração](pre-integracao.md).

## 15. Separar "processar o evento" de "entregar a resposta" (resiliência) + log mínimo

**Contexto:** na borda real, o envio da resposta automática pode falhar (API
instável, token expirado) **depois** de o chamado já ter sido criado e
persistido. Se essa falha subisse até a rota, o webhook responderia erro e a
plataforma **reentregaria o evento em laço**, repetindo follow-ups e tentativas
de envio.

**Decisão:** o servidor embrulha o transporte em um `BestEffortTransport`. A
falha de envio é registrada em log e **não** interrompe o fluxo: o chamado fica
gravado, o evento é marcado como processado (a reentrega não duplica) e a rota
responde 200. Registrar o pedido nunca depende de a resposta ser entregue.

Junto entrou **observabilidade mínima**: log operacional nas rotas (evento novo
vs. reentrega com número do chamado, contagens do webhook, payload recusado,
assinatura inválida). Regra firme: telefone, nome do solicitante e texto da
mensagem **nunca** entram no log (há teste garantindo). O log é ligado apenas no
executável (`basicConfig` no `main`), então importar o módulo não altera o
logging de quem usa o pacote como biblioteca.

## 16. Robustez de horário e de reset para a borda real

Dois ajustes pequenos que evitam falhas chatas quando a entrada deixa de ser só
a demonstração:

- **Timestamp sem fuso é assumido como UTC.** A entrada aceita um `timestamp`
  ISO opcional; sem fuso, ele virava um `datetime` "naive" e quebrava o cálculo
  de tempo do painel e a janela de follow-up (não dá para subtrair *naive* de
  *aware*). Como toda a base trabalha em UTC e o webhook entrega com fuso,
  normalizar o ausente para UTC é a escolha consistente.
- **`demo seed --reset` limpa via SQL, não apagando o arquivo.** Apagar o
  `.sqlite3` falhava no Windows enquanto o servidor o mantinha aberto
  (`PermissionError`/WinError 32). Um `clear()` no repositório esvazia as
  tabelas pela própria conexão, funcionando com o banco em uso.

## 17. Painel: leitura rápida em tela compartilhada (extensão da decisão 12)

Para o cenário de wallboard, o painel ganhou **resumos por categoria e por
status** (contagens) e **destaque visual de idade** (borda amarela a partir de
~4h, vermelha a partir de ~8h). São **heurísticas de leitura**, não um SLA
formal. A projeção restrita da decisão 12 é mantida intacta: as contagens e o
destaque derivam apenas de campos já projetados, sem trazer telefone, nome do
solicitante ou texto — com teste de não-vazamento cobrindo o caso.

## 18. Local/modo de atendimento (presencial × remoto)

Alguns chamados se resolvem **à distância**; outros exigem ir a uma **sala,
setor ou evento** específico. Para registrar isso, o `Ticket` ganhou dois campos
opcionais: `service_mode` (`ServiceMode`: `presencial`/`remoto`) e `location`
(texto livre — ex.: "Sala 203", "Recepção", "Auditório"). Escolhas:

- **Metadado operacional, não dado do solicitante.** Define *para onde o
  atendente vai*, então é definido por um **atendente** (`set_attendance` no
  serviço), não inferido da mensagem do funcionário. Por isso entra na **projeção
  do painel** (ajuda o wallboard: "para onde preciso ir") sem ferir a privacidade
  da decisão 8 — não é telefone, nome nem texto do solicitante.
- **Texto livre para o local, enum só para o modo.** Salas/eventos variam demais
  para um enum; já presencial/remoto é uma escolha fechada e útil para filtros
  futuros. `location` costuma acompanhar o presencial, mas os campos são
  independentes (um pode existir sem o outro).
- **Migração de schema (v3) idempotente.** As duas colunas são nuláveis e
  adicionadas por `ALTER TABLE` apenas quando faltam (bancos anteriores ao v3),
  sem backfill — chamados antigos ficam "sem definição". Há teste de migração de
  um banco no formato antigo.
- **Sem ajuste interativo ao vivo por enquanto.** O setter já existe e é testado;
  a forma de acioná-lo em produção (atendente marcando pela interface) entra com
  a **Fase 4**. Na demonstração, o `seed` já marca alguns exemplos para o painel
  exibir a coluna **Local** preenchida.

## 19. Comando de demonstração para esvaziar o banco

`python -m helpdesk.demo clear [--db ...]` apaga **todos** os chamados sem
recriar o roteiro (diferente do `seed --reset`, que limpa e repovoa). Reaproveita
o `SqliteTicketRepository.clear()` (limpeza via SQL, funciona com o servidor da
demo aberto — decisão 16) e os ids voltam a começar em `#1`. Pensado para zerar o
painel durante uma apresentação ou teste.

---

## Em aberto (a confirmar com o contexto do setor de TI)

- Quais categorias fazem mais sentido no dia a dia do setor?
- A equipe tem 4 atendentes fixos? O rodízio simples basta ou precisa considerar
  quem está disponível?
- Faz sentido notificar os atendentes (ex.: por outro canal) quando entra um
  chamado de prioridade alta?
- Qual o tom desejado nas mensagens automáticas?
