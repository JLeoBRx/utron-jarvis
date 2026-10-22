// Reprodução do núcleo do firmware no PC: lê um roteiro da entrada padrão e escreve na saída tudo o que o
// robô enviaria. Usado pelo teste que compara o firmware com o modelo do simulador do JARVIS.
//
// Roteiro, uma instrução por linha:
//   C                         conectar (HELLO, STA, PAR)
//   D                         desconectar
//   B <texto>                 bytes recebidos do PC (\n ao fim; "\!" vira o byte de parada)
//   T <ms> <s0> ... <s7> <x>  um ciclo do laço: tempo, 8 leituras brutas (0..4095) e o pino de cruzamento
//   L <escala>                escala do cão de guarda (só o simulador acelerado usa)
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../src/noct_core.h"

class Stdout : public noct::Output {
 public:
  void line(const char* text) override { printf("%s\n", text); }
};

int main() {
  Stdout out;
  noct::Core core(out, "simulador-1.0");
  char buf[1024];
  while (fgets(buf, sizeof(buf), stdin) != nullptr) {
    size_t n = strlen(buf);
    while (n > 0 && (buf[n - 1] == '\n' || buf[n - 1] == '\r')) buf[--n] = '\0';
    if (n == 0) continue;
    if (buf[0] == 'C') {
      core.connect(0);
    } else if (buf[0] == 'D') {
      core.disconnect();
    } else if (buf[0] == 'L') {
      core.linkScale = atof(buf + 2);
    } else if (buf[0] == 'B') {
      const char* text = n > 2 ? buf + 2 : "";
      for (const char* c = text; *c; ++c) {
        if (c[0] == '\\' && c[1] == '!') {
          core.feed('!', 0);
          ++c;
        } else {
          core.feed((uint8_t)*c, 0);
        }
      }
      core.feed('\n', 0);
    } else if (buf[0] == 'T') {
      long long now = 0;
      unsigned raw[8] = {0};
      int cross = 0;
      if (sscanf(buf + 2, "%lld %u %u %u %u %u %u %u %u %d", &now, &raw[0], &raw[1], &raw[2], &raw[3], &raw[4],
                 &raw[5], &raw[6], &raw[7], &cross) != 10) {
        fprintf(stderr, "linha de roteiro inválida: %s\n", buf);
        return 2;
      }
      uint16_t values[8];
      for (int i = 0; i < 8; ++i) values[i] = (uint16_t)raw[i];
      int left = 0, right = 0;
      core.tick(now, values, cross != 0, left, right);
      printf("PWM %d %d\n", left, right);
    }
  }
  return 0;
}
