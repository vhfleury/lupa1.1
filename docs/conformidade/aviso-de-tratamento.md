# Aviso de tratamento de dados pessoais

> **MINUTA para revisão de advogado; não é parecer jurídico.** Versão 0.1 · 21 de outubro de 2026 · subetapa 8.2. Trechos marcados "a confirmar pelo advogado" dependem de decisão jurídica.

**Controlador:** Victor Hugo Fleury Barreto, fornecedor do Lupa.
**Encarregado (canal de atendimento):** [a indicar]. A LGPD (art. 41) exige que o controlador indique encarregado e divulgue seu contato; eventual dispensa por porte depende de norma da ANPD: a confirmar pelo advogado. Contato: [a preencher].

O tribunal não é controlador nem operador deste tratamento e não tem acesso ao sistema.

---

## Parte A. Para os usuários (desembargador e assessores)

| Item | Conteúdo |
| --- | --- |
| Dados | nome de usuário, nome de exibição, papel, gabinete; hash da senha; segredo do autenticador (cifrado); sessões; IP e localização aproximada derivada do IP; registros de uso (o que foi aberto, buscado, perguntado — sem o texto da pergunta —, anotado, corrigido, quando e de onde) |
| Não coletamos | e-mail, CPF, telefone ou documentos pessoais do usuário |
| Finalidade | autenticar, controlar acesso por gabinete e processo, garantir a segurança, permitir auditoria e o relatório de uso que o magistrado entrega ao tribunal |
| Base legal | descrição: execução do acordo de uso firmado com o usuário (LGPD, art. 7º, V) e legítimo interesse do controlador em segurança e prevenção de fraude (art. 7º, IX). Enquadramento final: a confirmar pelo advogado |
| Compartilhamento | nenhum dado de conta vai ao fornecedor do modelo; provedor de hospedagem, se houver, guarda os dados cifrados |
| Retenção | conta: enquanto ativa; após a desativação, mantém-se o registro mínimo para a auditoria. Auditoria: prazo maior que o dos processos (prazo exato a confirmar pelo advogado) |
| Direitos | os do art. 18 da LGPD, pelo canal acima |
| Segurança | MFA obrigatório, bloqueio progressivo de login, auditoria com encadeamento de hash, TLS, cifra em repouso |

## Parte B. Para as pessoas citadas nos autos (réus, vítimas, testemunhas e outros)

Essas pessoas não usam o sistema. Este aviso fica disponível a quem pedir (forma de publicidade: a confirmar pelo advogado).

| Item | Conteúdo |
| --- | --- |
| Dados | os que já constam de processos **públicos** enviados pelo gabinete: nomes, qualificação, CPF e outros identificadores, endereços, datas, fatos narrados. Pode haver dados sensíveis (saúde, por exemplo) e dados sobre infrações penais |
| Origem | autos exportados do sistema do tribunal pelo próprio gabinete |
| Finalidade | apoiar o gabinete na conferência do processo: localizar peças, montar linha do tempo, rodar validações objetivas (tempestividade, prescrição) e responder perguntas de localização com citação de página. Não há perfilamento de pessoas, decisão automatizada nem treino de modelo |
| Base legal | descrição: tratamento ligado ao exercício regular de direitos em processo judicial (LGPD, art. 7º, VI; para dados sensíveis, art. 11, II, "d"). Como o controlador é um particular que apoia o magistrado, a adequação dessa base, a alternativa do legítimo interesse (art. 7º, IX, que não cobre dados sensíveis) e o tratamento de dados de natureza penal são **a confirmar pelo advogado** |
| Pseudonimização | nomes e identificadores do réu são substituídos por pseudônimos na camada analítica, nos logs e no que vai ao modelo; a tabela que liga pseudônimo e identidade fica separada e cifrada, e cada leitura é registrada |
| Compartilhamento | **Fornecedor do modelo (Anthropic, por API).** Vai: trechos dos autos pseudonimizados necessários para responder a pergunta ou gerar o resumo. Não vai: nome e CPF do réu, a tabela de identidades, arquivos inteiros, dados dos usuários. O contrato do fornecedor do modelo deve vedar treinamento com esses dados (conferência pendente, ver `checklist-piloto.md`). Nomes de vítimas e testemunhas que apareçam no trecho: verificar se a pseudonimização os cobre antes do piloto (a confirmar com o responsável técnico). O processamento pode ocorrer fora do Brasil; a hipótese legal para a transferência internacional é a confirmar pelo advogado. **Provedor de hospedagem**, se houver: guarda só dados cifrados |
| Retenção e descarte | enquanto o gabinete precisar do processo para a finalidade; descarte pela destruição da chave do processo; backups cifrados expiram em 30 dias. No fornecedor do modelo: conforme o contrato (conferir). Registros de auditoria (sem conteúdo dos autos) ficam por mais tempo |
| Direitos | confirmação, acesso, correção, anonimização, bloqueio ou eliminação de dados desnecessários, informação sobre compartilhamento e demais direitos do art. 18 da LGPD, observados os limites próprios de dados em processo judicial (a confirmar pelo advogado). A correção do conteúdo dos autos se faz no próprio processo judicial, não no Lupa |
| Canal | encarregado indicado acima. O pedido não precisa e não deve conter cópia de autos |
| Segurança (LGPD, art. 46) | só processos públicos; arquivo cifrado antes de qualquer leitura; chave por processo derivada da chave do gabinete em cofre próprio (Vault); texto extraído também cifrado; TLS; acesso com MFA e restrito ao gabinete; auditoria append-only; logs sem conteúdo dos autos |
