# Aprimoramento — holograma, TARDIS, voz, Protocolo ULTRON operacional e JARVIS WEB ORB

Análise feita no código atual (branch `claude/adoring-brahmagupta-vcejpt`) antes de qualquer mudança, como pedido no
item 7. Nada aqui recria o NeuralCore, duplica a memória ou apaga dados do usuário.

## 1. O que existe e será reaproveitado

| Pedido | Peça existente | Como será usada |
|---|---|---|
| Holograma humanoide | `ultron/hud/scene3d/web/js/avatar.js` (Three.js r170): esqueleto com ossos, *skinning* na GPU, rosto com olhos/íris/joia, linhas anatômicas, circuitos, boca pela trilha labial real, estados reais | o MESMO rig e os mesmos estados; ganha superfícies sólidas holográficas, roupas, cabelo e expressões |
| TARDIS | `web/js/room.js` (sala, rotor, console de seis painéis ligados às tarefas reais), `exterior.js` (cabine), `deck.js` | mais detalhe na sala, no rotor e na cabine; o holograma passa a ficar DENTRO da sala, junto ao console |
| ORBE | `web/js/orb.js` + `ultron/hud/orb.py` (janela flutuante que pega a mesma cena emprestada) | o mesmo módulo `orb.js` é a base da ORBE do site |
| Voz | `ultron/voice/tts.py` (Piper 1.8, voz `pt_BR-faber-medium`), `dsp.py` (altura, graves, rouquidão, camada, sala), `lipsync.py`, perfis em `personality/voice_profile.py` | camada de prosódia (pausas, ritmo, variação por frase, parâmetros de expressividade do Piper) e perfis `JARVIS_VOICE_PROFILE`/`ULTRON_VOICE_PROFILE` |
| Som | `ultron/audio/neural_audio.py` (sons sintetizados da interface), `ambient_sound`, `sfx_volume` | efeitos da TARDIS ORIGINAIS sintetizados + pasta para arquivos autorizados do usuário |
| Protocolo ULTRON | `ultron/hud/ultron_protocol.py` (lógica), controlador, cena 3D | passa a trocar também voz, personalidade e o perfil de permissões |
| Execução | `agent/execution.py`, `autonomy.py` (risco + autorização), `permissions.py` (cinco categorias), histórico de atividades | `ULTRON_OPERATOR` é uma POLÍTICA aplicada a esse mesmo executor — não um segundo executor |
| Rede remota | inexistente (o módulo `ultron/network` é o inventário da rede LOCAL) | novo: gateway + agente local + site da ORBE |

## 2. Decisões que precisam ficar claras

* **Visão (Marvel):** inspiração de estilo (androide sintético, placas faciais, gema na testa), com desenho e
  paleta próprios do JARVIS — sem reproduzir o personagem.
* **Som oficial da TARDIS:** é obra protegida. O JARVIS NÃO inclui esse áudio. Os efeitos distribuídos são
  originais (sintetizados no próprio programa); se você tiver um arquivo com licença, basta colocá-lo na pasta de
  sons do usuário (nomes no README) que ele substitui o efeito original — sem ir para o repositório.
* **ULTRON operacional:** este pedido substitui a restrição anterior ("o ULTRON não executa nada"). A partir dele,
  o ULTRON usa as MESMAS ferramentas, o MESMO executor e o MESMO sistema de autorização, com o perfil
  `ULTRON_OPERATOR`. Continua valendo: categorias bloqueadas continuam bloqueadas; apagar dados sempre pede
  confirmação; risco alto sempre pede confirmação; nada contorna o UAC ou desativa proteções do Windows; toda ação
  vai para ATIVIDADES e pode ser interrompida (PARAR, Esc, tecla de emergência). O rótulo na tela deixa de dizer
  "nenhuma ação real" e passa a dizer, com honestidade, que há um operador ativo sob as suas permissões.
  A ativação **ocasional** troca só a identidade (aparência, voz, personalidade): o perfil operacional relaxado
  vale na ativação pedida por você, a menos que você ligue a opção correspondente.
* **Voz:** só dá para afirmar melhora com amostras ouvidas por você — cada etapa gera arquivos WAV de comparação.
  Alternativas avaliadas: outras vozes Piper pt-BR (offline), Kokoro (offline, mais pesada) e vozes neurais na
  nuvem (melhor qualidade, mas o texto falado sai do computador — só como opção explícita).
* **JARVIS WEB ORB:** o site é só uma janela; o cérebro continua no computador. Publicar na internet exige
  hospedagem e domínio seus: o código, o Docker e o guia ficam prontos e testados localmente; nada é declarado
  publicado sem estar.

## 3. Etapas (cada uma com testes executados antes do commit)

1. **ULTRON operador + identidade completa**: persona no núcleo (voz, personalidade, permissões), perfil
   `ULTRON_OPERATOR` configurável, tecla de emergência, restauração que também interrompe o que o ULTRON estiver
   fazendo, rótulo honesto, estado publicado para a interface e o site.
2. **Voz**: camada de prosódia, ajuste de expressividade do Piper, `JARVIS_VOICE_PROFILE` e
   `ULTRON_VOICE_PROFILE` (grave, frio, ritmo deliberado, textura metálica), amostras WAV para avaliação.
3. **Sons da TARDIS**: materialização, desmaterialização, portas, rotor, alertas e ambiente — originais, com volume
   e desligamento; arquivos autorizados do usuário têm prioridade.
4. **Holograma humanoide**: superfícies sólidas holográficas, rosto expressivo (pálpebras, sobrancelhas, lábios,
   olhar), cabelo com volume e movimento, jaqueta/calça/calçados, detalhes metálicos e circuitos; ULTRON com
   olhos vermelhos e acabamento metálico.
5. **TARDIS**: paredes, roundels, colunas, consoles, rotor com cilindros/anéis/peças internas, iluminação,
   mobiliário integrado e cabine; o holograma dentro da sala, junto ao console, olhando os painéis e
   acompanhando as operações reais.
6. **JARVIS WEB ORB**: gateway (HTTPS/WSS, contas, pareamento por QR/código, revogação, limites, auditoria),
   agente local de saída (sem abrir portas) ligado ao MESMO NeuralCore, site só com a ORBE (estados reais,
   conversa, voz, autorização, ULTRON), testes ponta a ponta locais e guia de publicação.
