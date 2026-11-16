# 4 JUSTIFICATIVA

**Relevância tecnológica.** A execução local de modelos de linguagem, de reconhecimento e de síntese de fala
tornou viável construir assistentes que funcionam sem enviar dados a terceiros. O ganho de privacidade e de
autonomia, porém, transfere ao desenvolvedor problemas que os serviços em nuvem escondem: concorrência entre
componentes pesados num mesmo computador, falhas parciais, consumo de recursos e, principalmente, o controle
do que o sistema pode fazer na máquina do usuário. Documentar como esses problemas foram enfrentados num
sistema real — com as decisões, os erros encontrados e as medições — produz conhecimento aplicável a outros
sistemas integrados.

**Relevância para o desenvolvimento de sistemas.** O SAFRA exercita, num único projeto, conteúdos centrais
da formação técnica em Desenvolvimento de Sistemas: modelagem de requisitos, arquitetura em camadas e
orientada a eventos, programação concorrente, persistência com migrações de esquema, interfaces gráficas,
integração com serviços externos, segurança da aplicação, testes automatizados e integração contínua. O
histórico do repositório registra a passagem de um código que crescia por acréscimo de fases — com 38 % das
linhas em cópias de backup e o caminho principal de inicialização quebrado — para uma arquitetura com núcleo
único e 471 testes automatizados, o que torna o projeto um estudo de caso de reengenharia.

**Relevância para interfaces inteligentes.** A combinação de voz, avatar humanoide e sincronização labial é
estudada há décadas na área de agentes conversacionais corporificados. O trabalho contribui com uma
implementação aberta e local, em que a animação é guiada pelo áudio real e pelos estados reais do sistema,
e com um método de verificação dessa coerência.

**Relevância para a segurança.** Dar a um modelo de linguagem a capacidade de executar ações no computador
cria riscos conhecidos — injeção de instruções por conteúdo externo, execução de ferramentas indevidas,
ações irreversíveis. O SAFRA aplica e testa um conjunto de camadas de controle (recusa antecipada,
permissões por categoria, autorização explícita, verificação e auditoria) que pode ser reaproveitado.

**Relevância educacional.** O projeto foi desenvolvido por um estudante com o apoio de um assistente de
programação por IA. Registrar com transparência esse modo de trabalho — o que foi especificado, revisado,
testado e decidido pelo autor — contribui para a discussão sobre o uso responsável dessas ferramentas na
formação técnica.

**Viabilidade.** O protótipo já existe e é funcional em grande parte (ver `INVENTARIO_FUNCIONALIDADES.md`);
os componentes usados são gratuitos e de código aberto; os testes podem ser executados num computador
pessoal; e o cronograma reserva o ano de 2027 para medição, análise e redação.
