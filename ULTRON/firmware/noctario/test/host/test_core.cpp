// Testes do núcleo do firmware no PC (g++): protocolo, parada, calibração, PD, cruzamentos, perda de linha,
// cão de guarda, teste de bancada e limites. Não é teste do robô real: não há motor, sensor nem rádio aqui.
#include <stdio.h>
#include <string.h>

#include <string>
#include <vector>

#include "../../src/noct_core.h"

static int failures = 0;
#define CHECK(cond, msg)                                                   \
  do {                                                                     \
    if (!(cond)) {                                                         \
      fprintf(stderr, "FALHOU (%s:%d): %s\n", __FILE__, __LINE__, msg);    \
      failures++;                                                          \
    }                                                                      \
  } while (0)

class Capture : public noct::Output {
 public:
  std::vector<std::string> lines;
  void line(const char* text) override { lines.push_back(text); }
  bool has(const char* prefix) const {
    for (const auto& l : lines) {
      if (l.compare(0, strlen(prefix), prefix) == 0) return true;
    }
    return false;
  }
  std::string last(const char* prefix) const {
    for (auto it = lines.rbegin(); it != lines.rend(); ++it) {
      if (it->compare(0, strlen(prefix), prefix) == 0) return *it;
    }
    return "";
  }
  void clear() { lines.clear(); }
};

struct Rig {
  Capture out;
  noct::Core core{out, "teste"};
  long long now = 0;
  int left = 0, right = 0;

  void send(const char* text) {
    for (const char* c = text; *c; ++c) core.feed((uint8_t)*c, now);
    core.feed('\n', now);
  }
  // linha branca sob o sensor "center" (0..7); cross=true representa a marca ativa (pino LOW).
  void tick(double center, bool cross = false, int ms = 2) {
    now += ms;
    uint16_t raw[8];
    for (int i = 0; i < 8; ++i) {
      double d = i - center;
      double strength = center < 0 ? 0.0 : (d * d < 0.25 ? 1.0 : (d * d < 2.25 ? 0.4 : 0.0));
      raw[i] = (uint16_t)(3400 - (3400 - 450) * strength);
    }
    core.tick(now, raw, !cross, left, right);  // nível bruto HIGH em repouso; LOW sobre a marca
  }
  void calibrate() {
    send("CMD 90 CAL ms=500");
    for (int i = 0; i < 300; ++i) tick((i % 40) / 5.0);  // a barra passa sobre a linha e o fundo
    send("CMD 91 SET hb=0");
  }
};

static void test_protocol() {
  Rig r;
  r.core.connect(0);
  CHECK(r.out.has("HELLO fw=teste proto=1 st=IDLE cal=0"), "HELLO ao conectar");
  CHECK(r.out.has("PAR kp=0.0125 kd=0.1 base=220 max=220"), "PAR com os valores iniciais");
  CHECK(r.out.has("deb=150 xact=0 thr=200"), "sensor de cruzamento ativo em LOW");
  CHECK(r.out.has("tel=20 loop=100 white=1"), "laço de controle confirmado em 100 Hz");
  r.out.clear();
  r.send("CMD 1 PING");
  CHECK(r.out.last("ACK 1").find("pong=1") != std::string::npos, "PING responde");
  r.send("CMD 2 VOAR");
  CHECK(r.out.has("NAK 2 code=UNKNOWN"), "verbo desconhecido");
  r.send("bom dia");
  CHECK(r.out.has("NAK 0 code=SYNTAX"), "linha malformada");
  r.send("CMD 3 SET kp");
  CHECK(r.out.has("NAK 3 code=SYNTAX"), "argumento sem valor");
  std::string longa(300, 'x');
  r.send(longa.c_str());
  CHECK(r.out.last("NAK 0").find("linha_longa_demais") != std::string::npos, "linha longa descartada inteira");
}

static void test_limits() {
  Rig r;
  r.core.connect(0);
  r.send("CMD 1 SET kp=0.5");
  CHECK(r.out.has("NAK 1 code=RANGE"), "Kp acima do limite");
  r.send("CMD 2 SET base=240");
  CHECK(r.out.has("NAK 2 code=RANGE"), "base maior que o máximo");
  r.send("CMD 3 SET kd=0,12 adapt=0.3");
  CHECK(r.out.has("ACK 3 kd=0.12 adapt=0.3"), "vírgula decimal aceita e eco dos valores");
  CHECK(r.core.params().kd > 0.1199 && r.core.params().kd < 0.1201, "Kd aplicado");
  r.send("CMD 4 SET ldir=0");
  CHECK(r.out.has("NAK 4 code=RANGE"), "sentido do motor só -1 ou 1");
  r.send("CMD 5 SET onlink=continue");
  CHECK(!r.core.params().onlinkStop, "política sem link ajustável");
  r.send("CMD 6 TEL hz=60");
  CHECK(r.out.has("NAK 6 code=RANGE"), "telemetria acima de 50 Hz");
}

static void test_calibration_and_start() {
  Rig r;
  r.core.connect(0);
  r.send("CMD 1 START");
  CHECK(r.out.has("NAK 1 code=NOCAL"), "sem calibração não parte");
  r.send("CMD 2 CAL ms=500");
  for (int i = 0; i < 300; ++i) r.tick(3.5);                  // parado sobre a linha: sem contraste nos extremos
  CHECK(r.out.has("EVT cal ok=0"), "calibração recusada sem contraste");
  CHECK(r.core.state() == noct::State::IDLE, "volta a IDLE");
  r.calibrate();
  CHECK(r.out.has("EVT cal ok=1"), "calibração aceita com a barra passando sobre a linha");
  CHECK(r.core.state() == noct::State::READY, "pronto");
  r.out.clear();
  r.send("CMD 3 START");
  CHECK(r.out.has("ACK 3 st=RUN"), "partida confirmada");
  CHECK(r.core.motorsEnabled(), "STBY alto em percurso");
}

static void test_pd_and_estop() {
  Rig r;
  r.core.connect(0);
  r.calibrate();
  r.send("CMD 1 START");
  for (int i = 0; i < 400; ++i) r.tick(3.5);                  // reta: os dois motores sobem pela rampa
  CHECK(r.left > 150 && r.left == r.right, "na reta, PWM igual nos dois lados");
  for (int i = 0; i < 20; ++i) r.tick(6.0);                   // linha à direita
  CHECK(r.left > r.right, "linha à direita: motor esquerdo mais rápido");
  CHECK(r.left <= 220 && r.right >= 0, "dentro de [mínimo, máximo]");
  r.out.clear();
  r.send("CMD 2 SET k");                                     // linha parcial interrompida pela parada:
  r.core.feed('C', r.now);
  r.core.feed('!', r.now);                                   // "!" no meio da linha corta tudo
  CHECK(r.core.state() == noct::State::ESTOP, "parada de emergência imediata");
  CHECK(!r.core.motorsEnabled(), "STBY baixo na emergência");
  CHECK(r.out.has("EVT estop src=bt"), "evento da parada");
  r.tick(3.5);
  CHECK(r.left == 0 && r.right == 0, "motores parados");
  r.send("CMD 3 START");
  CHECK(r.out.has("NAK 3 code=ESTOP"), "não parte em emergência");
  r.send("CMD 4 CLEAR");
  CHECK(r.out.has("ACK 4 st=READY"), "CLEAR libera, parado e pronto");
}

static void test_crossings_and_destination() {
  Rig r;
  r.core.connect(0);
  r.calibrate();
  r.send("CMD 1 START");
  for (int i = 0; i < 200; ++i) r.tick(3.5);
  for (int k = 0; k < 4; ++k) {
    for (int i = 0; i < 10; ++i) r.tick(3.5, true);           // faixa de cruzamento por 20 ms
    r.tick(3.5, false);
    for (int i = 0; i < 20; ++i) r.tick(3.5, i % 4 == 0);     // repique dentro do filtro: não conta
    for (int i = 0; i < 200; ++i) r.tick(3.5);
  }
  CHECK(r.out.has("EVT cross n=4"), "quatro cruzamentos contados");
  CHECK(!r.out.has("EVT cross n=5"), "repique filtrado");
  for (int i = 0; i < 400; ++i) r.tick(3.5);
  CHECK(r.out.has("EVT done lap_ms="), "destino: para no quarto cruzamento");
  CHECK(r.core.state() == noct::State::DONE, "estado DONE");
}

static void test_lost_and_recovery() {
  Rig r;
  r.core.connect(0);
  r.calibrate();
  r.send("CMD 1 START");
  for (int i = 0; i < 200; ++i) r.tick(5.0);                  // última vez vista à direita
  for (int i = 0; i < 200; ++i) r.tick(-1.0);                 // sumiu
  CHECK(r.out.has("EVT lost"), "perda de linha anunciada");
  CHECK(r.core.state() == noct::State::LOST, "recuperando");
  CHECK(r.left > 0 && r.right == 0, "gira para o lado da linha (PWM mínimo 0: pivô sobre a roda direita)");
  Rig reverse;                                                // com ré permitida, gira no lugar
  reverse.core.connect(0);
  reverse.calibrate();
  reverse.send("CMD 1 SET minpwm=-200");
  reverse.send("CMD 2 START");
  for (int i = 0; i < 200; ++i) reverse.tick(5.0);
  for (int i = 0; i < 200; ++i) reverse.tick(-1.0);
  CHECK(reverse.left > 0 && reverse.right < 0, "com PWM mínimo negativo, giro no lugar");
  for (int i = 0; i < 5; ++i) r.tick(4.0);
  CHECK(r.out.has("EVT found"), "linha reencontrada");
  CHECK(r.core.state() == noct::State::RUN, "volta ao percurso");
  for (int i = 0; i < 1500; ++i) r.tick(-1.0);                // sumiu de vez
  CHECK(r.out.has("EVT stop reason=lost"), "para depois do tempo máximo de recuperação");
  CHECK(r.core.state() == noct::State::STOP, "estado STOP");
}

static void test_watchdog_policy() {
  Rig r;
  r.core.connect(0);
  r.calibrate();
  r.send("CMD 1 SET hb=300");
  r.send("CMD 2 START");
  for (int i = 0; i < 400; ++i) r.tick(3.5);                  // 800 ms sem nenhuma linha do PC
  CHECK(r.out.has("EVT stop reason=link"), "política stop: para sem link");
  Rig c;
  c.core.connect(0);
  c.calibrate();
  c.send("CMD 1 SET hb=300 onlink=continue");
  c.send("CMD 2 START");
  for (int i = 0; i < 400; ++i) c.tick(3.5);
  CHECK(c.core.state() == noct::State::RUN, "política continue: segue o percurso");
}

static void test_bench() {
  Rig r;
  r.core.connect(0);
  r.send("CMD 1 MOTOR l=100 r=-100 ms=200");
  CHECK(r.out.has("ACK 1 st=TEST"), "teste de bancada aceito parado");
  r.tick(3.5);
  CHECK(r.left == 100 && r.right == -100, "PWM do teste");
  for (int i = 0; i < 120; ++i) r.tick(3.5);
  CHECK(r.left == 0 && r.core.state() == noct::State::IDLE, "acaba sozinho no tempo");
  r.send("CMD 2 MOTOR l=300 r=0");
  CHECK(r.out.has("NAK 2 code=RANGE"), "PWM do teste limitado");
  r.send("CMD 3 SET ldir=-1 rdir=-1");
  r.send("CMD 4 MOTOR l=50 r=60 ms=200");
  r.tick(3.5);
  CHECK(r.left == -50 && r.right == -60, "sentido de cada motor ajustável (a confirmar na bancada)");
  r.send("CMD 5 MOTOR l=80 r=80 ms=3000");
  r.tick(3.5);
  r.send("CMD 6 STOP");
  CHECK(r.out.has("ACK 6 st=IDLE") && !r.core.motorsEnabled(), "STOP encerra o teste de bancada na hora");
  r.tick(3.5);
  CHECK(r.left == 0 && r.right == 0, "motores parados");
  CHECK(!r.out.has("EVT stop"), "teste de bancada não é volta");
}

static void test_interrupted_calibration() {
  Rig r;
  r.calibrate();
  CHECK(r.core.calibrated(), "calibrado");
  r.send("CMD 1 CAL ms=3000 auto=1");
  for (int i = 0; i < 50; ++i) r.tick(3.5);
  r.core.feed('!', r.now);                 // emergência no meio da calibração
  r.send("CMD 2 CLEAR");
  CHECK(!r.core.calibrated() && r.core.state() == noct::State::IDLE, "calibração interrompida não vale");
  r.send("CMD 3 START");
  CHECK(r.out.has("NAK 3 code=NOCAL"), "sem calibração completa, sem partida");

  Rig s;
  s.calibrate();
  s.send("CMD 1 CAL ms=3000");
  s.tick(3.5);
  s.send("CMD 2 STOP");
  CHECK(s.out.has("ACK 2 st=IDLE") && !s.core.calibrated(), "STOP interrompe a calibração: fica sem calibração");
}

static void test_restore() {
  uint16_t mins[8], maxs[8];
  for (int i = 0; i < 8; ++i) {
    mins[i] = 450;
    maxs[i] = 3400;
  }
  noct::Params good;
  good.kp = 0.02;
  good.base = 200;
  good.max = 230;
  Rig a;
  a.core.restore(good, mins, maxs, true);
  CHECK(a.core.state() == noct::State::READY && a.core.calibrated(), "NVS válida: pronto, calibrado");
  CHECK(a.core.params().kp == 0.02 && a.core.params().base == 200, "parâmetros gravados valem");

  noct::Params bad = good;
  bad.loop = 0;                            // memória corrompida: laço a 0 Hz dividiria por zero
  bad.base = 300;
  Rig b;
  b.core.restore(bad, mins, maxs, true);
  CHECK(b.core.params().loop == 100 && b.core.params().base == 220, "parâmetros inválidos: padrões");
  CHECK(b.core.calibrated(), "a calibração válida continua");

  noct::Params swapped = good;
  swapped.ldir = 0;
  Rig c;
  c.core.restore(swapped, mins, maxs, true);
  CHECK(c.core.params().ldir == 1 && c.core.params().kp == 0.0125, "sentido 0 não existe: padrões");

  for (int i = 0; i < 8; ++i) maxs[i] = 500;    // sem contraste
  Rig d;
  d.core.restore(good, mins, maxs, true);
  CHECK(!d.core.calibrated() && d.core.state() == noct::State::IDLE, "calibração sem contraste não vale");
  d.send("CMD 1 START");
  CHECK(d.out.has("NAK 1 code=NOCAL"), "e sem calibração não há partida");
}

int main() {
  test_protocol();
  test_limits();
  test_calibration_and_start();
  test_pd_and_estop();
  test_crossings_and_destination();
  test_lost_and_recovery();
  test_watchdog_policy();
  test_bench();
  test_interrupted_calibration();
  test_restore();
  if (failures) {
    fprintf(stderr, "%d verificação(ões) falharam\n", failures);
    return 1;
  }
  printf("OK: núcleo do firmware aprovado\n");
  return 0;
}
