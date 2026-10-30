// Noctário — núcleo do firmware SEM hardware (compila no PC para os testes e na ESP32 pelo main.cpp).
//
// Tudo o que decide o comportamento do robô está aqui: protocolo NOCT/1, máquina de estados, posição da
// linha (8 QTR analógicos, linha branca em pista preta), PD com velocidade adaptativa e rampas, contagem
// de cruzamentos com filtro, perda de linha e recuperação limitada, cão de guarda do link com a política
// "stop"/"continue", parada de emergência pelo byte '!' e teste de bancada dos motores.
//
// O simulador do JARVIS (ultron/noctario/simulator.py, FirmwareModel) implementa a MESMA lógica; um teste
// alimenta os dois com as mesmas entradas e compara as saídas linha a linha.
//
// Reconciliação com os sketches originais na Biblioteca: linha branca, sensor de cruzamento ativo em LOW
// (xact=0) e laço de 100 Hz (loop=100) estão confirmados. A variante de 28/10 usa 6 cruzamentos;
// o perfil JARVIS mantido aqui usa 4. Ordem física QTR e sentidos reais dos motores exigem bancada.
// O cão de guarda de link é uma proteção adicional deste firmware, não existia no sketch original.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace noct {

constexpr int SENSORS = 8;
constexpr int CENTER = 3500;
constexpr size_t MAX_LINE = 240;
constexpr int CAL_MIN_SPAN = 200;          // contraste mínimo (ADC bruto, 12 bits) para aceitar a calibração
constexpr int64_t NEVER = -1000000000LL;
constexpr int64_t NONE = -1;               // "sem valor" para instantes (tempo em ms é sempre >= 0)

enum class State : uint8_t { BOOT, IDLE, CAL, READY, RUN, LOST, STOPPING, STOP, DONE, ESTOP, FAULT, TEST };
const char* stateName(State s);

// Parâmetros na MESMA ordem do protocolo (ultron/noctario/protocol.py → PARAMS): a linha PAR depende dela.
struct Params {
  double kp = 0.0125;
  double kd = 0.1;
  int base = 220;
  int max = 220;
  int minpwm = 0;
  int accel = 600;
  int decel = 900;
  double adapt = 0.35;
  int cross = 4;
  int deb = 150;
  int xact = 0;
  int thr = 200;
  int lostms = 300;
  int loststop = 1500;
  int recov = 120;
  int hb = 1500;
  bool onlinkStop = true;                  // "stop" | "continue"
  int tel = 20;
  int loop = 100;
  int white = 1;
  int flip = 0;
  int ldir = 1;
  int rdir = 1;
};

// Destino das linhas que o robô envia (Bluetooth na ESP32; um vetor nos testes).
class Output {
 public:
  virtual ~Output() {}
  virtual void line(const char* text) = 0;
};

class Core {
 public:
  Core(Output& out, const char* fw);

  // ligação com o PC
  void connect(int64_t now);
  void disconnect();
  void feed(uint8_t byte, int64_t now);    // '!' = parada imediata, antes de qualquer análise

  // um ciclo do laço de controle: leitura bruta dos 8 sensores (0..4095) e do pino de cruzamento →
  // PWM com sinal (−255..255) já com o sentido de cada motor
  void tick(int64_t now, const uint16_t raw[SENSORS], bool crossPin, int& left, int& right);

  // persistência (a camada Arduino grava na NVS quando pedido); restore() confere os limites de cada parâmetro
  // e o contraste da calibração — o que não passar volta ao padrão / sem calibração
  bool takeSaveRequest();
  void restore(const Params& stored, const uint16_t* mins, const uint16_t* maxs, bool calibrated);

  // leitura
  State state() const { return state_; }
  bool calibrated() const { return cal_; }
  bool motorsEnabled() const;              // nível do STBY do TB6612FNG
  const Params& params() const { return p_; }
  const uint16_t* mins() const { return mins_; }
  const uint16_t* maxs() const { return maxs_; }
  double linkScale = 1.0;                  // só o simulador acelerado usa (>1); no robô é sempre 1

 private:
  void emit(const char* text);
  void emitf(const char* fmt, ...);
  void emitSta();
  void emitPar();
  void setState(State s, const char* reason = nullptr);
  void estop(const char* source);
  void handle(char* line);
  void nak(int seq, const char* code, const char* msg);
  void readLine(const uint16_t raw[SENSORS]);
  bool applySet(int seq, char** keys, char** values, int count);
  bool parseParam(const char* key, const char* value, Params& target, char* err, size_t errSize);

  Output& out_;
  const char* fw_;
  Params p_;
  Params saved_;
  State state_ = State::IDLE;
  bool cal_ = false;
  uint16_t mins_[SENSORS];
  uint16_t maxs_[SENSORS];
  char line_[MAX_LINE + 1];
  size_t len_ = 0;
  bool overflow_ = false;
  int64_t now_ = 0;
  int64_t lastRx_ = 0;
  int crossings_ = 0;
  int64_t lastCross_ = NEVER;
  bool crossPrev_ = false;
  bool crossRaw_ = false;                  // nível lido no pino de cruzamento (para conferir o xact na bancada)
  int64_t lostSince_ = NONE;
  int lastErr_ = 0;
  double ramp_ = 0.0;
  int64_t lapStart_ = 0;
  int64_t lapMs_ = 0;
  char stopReason_[12] = "";
  int64_t telLast_ = NEVER;
  int64_t calUntil_ = 0;
  bool calAuto_ = false;
  int testL_ = 0, testR_ = 0;
  int64_t testUntil_ = 0;
  int values_[SENSORS];
  int pos_ = CENTER;
  int err_ = 0;
  double corr_ = 0.0;
  int pwmL_ = 0, pwmR_ = 0;
  bool seen_ = false;
  bool connected_ = false;
  bool saveRequested_ = false;
};

}  // namespace noct
