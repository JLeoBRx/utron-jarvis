// Noctário — núcleo do firmware (ver noct_core.h). Sem Arduino: compila no PC (g++) e na ESP32.
#include "noct_core.h"

#include <ctype.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace noct {

namespace {

const char* const STATE_NAMES[] = {"BOOT", "IDLE", "CAL", "READY", "RUN", "LOST", "STOPPING", "STOP", "DONE",
                                   "ESTOP", "FAULT", "TEST"};

bool isStopped(State s) {
  return s == State::IDLE || s == State::READY || s == State::STOP || s == State::DONE;
}

bool inRun(State s) { return s == State::RUN || s == State::LOST || s == State::STOPPING; }

// número no formato "%g" (o mesmo do PC: format(v, "g") em Python)
void fmtNumber(char* buf, size_t size, double v) { snprintf(buf, size, "%g", v); }

// inteiro estrito em ASCII (com sinal opcional); false se não for
bool parseInt(const char* text, long& out) {
  if (text == nullptr || *text == '\0') return false;
  const char* q = text;
  if (*q == '+' || *q == '-') q++;
  if (*q == '\0') return false;
  for (const char* c = q; *c; ++c) {
    if (!isdigit((unsigned char)*c)) return false;
  }
  if (strlen(q) > 9) return false;
  out = strtol(text, nullptr, 10);
  return true;
}

// número decimal (vírgula aceita como separador, como no PC)
bool parseNumber(const char* text, double& out) {
  char buf[40];
  size_t n = strlen(text);
  if (n == 0 || n >= sizeof(buf)) return false;
  for (size_t i = 0; i <= n; ++i) buf[i] = text[i] == ',' ? '.' : text[i];
  char* end = nullptr;
  double v = strtod(buf, &end);
  if (end == buf || *end != '\0' || isnan(v) || isinf(v)) return false;
  out = v;
  return true;
}

struct Spec {
  const char* key;
  char kind;      // 'f' float, 'i' int, 'c' choice (onlink)
  double low;
  double high;
  int c1, c2;     // escolhas permitidas para inteiros (ambas 0 = sem restrição)
  bool runtimeOnly;
};

// MESMA ordem e limites de ultron/noctario/protocol.py (PARAMS)
const Spec SPECS[] = {
    {"kp", 'f', 0.0, 0.2, 0, 0, false},       {"kd", 'f', 0.0, 2.0, 0, 0, false},
    {"base", 'i', 0, 255, 0, 0, false},       {"max", 'i', 0, 255, 0, 0, false},
    {"minpwm", 'i', -255, 255, 0, 0, false},  {"accel", 'i', 0, 5000, 0, 0, false},
    {"decel", 'i', 0, 5000, 0, 0, false},     {"adapt", 'f', 0.0, 1.0, 0, 0, false},
    {"cross", 'i', 0, 20, 0, 0, false},       {"deb", 'i', 20, 2000, 0, 0, false},
    {"xact", 'i', 0, 1, 0, 1, false},         {"thr", 'i', 0, 1000, 0, 0, false},
    {"lostms", 'i', 50, 3000, 0, 0, false},   {"loststop", 'i', 100, 10000, 0, 0, false},
    {"recov", 'i', 0, 255, 0, 0, false},      {"hb", 'i', 0, 10000, 0, 0, false},
    {"onlink", 'c', 0, 0, 0, 0, false},       {"tel", 'i', 0, 50, 0, 0, false},
    {"loop", 'i', 100, 2000, 0, 0, true},     {"white", 'i', 0, 1, 0, 1, true},
    {"flip", 'i', 0, 1, 0, 1, true},          {"ldir", 'i', -1, 1, -1, 1, true},
    {"rdir", 'i', -1, 1, -1, 1, true},
};
constexpr int SPEC_COUNT = sizeof(SPECS) / sizeof(SPECS[0]);

const Spec* findSpec(const char* key) {
  for (int i = 0; i < SPEC_COUNT; ++i) {
    if (strcmp(SPECS[i].key, key) == 0) return &SPECS[i];
  }
  return nullptr;
}

// valor de um parâmetro como texto (para PAR e ACK)
void paramText(const Params& p, const char* key, char* buf, size_t size) {
  if (strcmp(key, "kp") == 0) return fmtNumber(buf, size, p.kp);
  if (strcmp(key, "kd") == 0) return fmtNumber(buf, size, p.kd);
  if (strcmp(key, "adapt") == 0) return fmtNumber(buf, size, p.adapt);
  if (strcmp(key, "onlink") == 0) { snprintf(buf, size, "%s", p.onlinkStop ? "stop" : "continue"); return; }
  int v = 0;
  if (strcmp(key, "base") == 0) v = p.base;
  else if (strcmp(key, "max") == 0) v = p.max;
  else if (strcmp(key, "minpwm") == 0) v = p.minpwm;
  else if (strcmp(key, "accel") == 0) v = p.accel;
  else if (strcmp(key, "decel") == 0) v = p.decel;
  else if (strcmp(key, "cross") == 0) v = p.cross;
  else if (strcmp(key, "deb") == 0) v = p.deb;
  else if (strcmp(key, "xact") == 0) v = p.xact;
  else if (strcmp(key, "thr") == 0) v = p.thr;
  else if (strcmp(key, "lostms") == 0) v = p.lostms;
  else if (strcmp(key, "loststop") == 0) v = p.loststop;
  else if (strcmp(key, "recov") == 0) v = p.recov;
  else if (strcmp(key, "hb") == 0) v = p.hb;
  else if (strcmp(key, "tel") == 0) v = p.tel;
  else if (strcmp(key, "loop") == 0) v = p.loop;
  else if (strcmp(key, "white") == 0) v = p.white;
  else if (strcmp(key, "flip") == 0) v = p.flip;
  else if (strcmp(key, "ldir") == 0) v = p.ldir;
  else if (strcmp(key, "rdir") == 0) v = p.rdir;
  snprintf(buf, size, "%d", v);
}

void setParam(Params& p, const char* key, double number, bool stop) {
  if (strcmp(key, "kp") == 0) p.kp = number;
  else if (strcmp(key, "kd") == 0) p.kd = number;
  else if (strcmp(key, "adapt") == 0) p.adapt = number;
  else if (strcmp(key, "onlink") == 0) p.onlinkStop = stop;
  else if (strcmp(key, "base") == 0) p.base = (int)number;
  else if (strcmp(key, "max") == 0) p.max = (int)number;
  else if (strcmp(key, "minpwm") == 0) p.minpwm = (int)number;
  else if (strcmp(key, "accel") == 0) p.accel = (int)number;
  else if (strcmp(key, "decel") == 0) p.decel = (int)number;
  else if (strcmp(key, "cross") == 0) p.cross = (int)number;
  else if (strcmp(key, "deb") == 0) p.deb = (int)number;
  else if (strcmp(key, "xact") == 0) p.xact = (int)number;
  else if (strcmp(key, "thr") == 0) p.thr = (int)number;
  else if (strcmp(key, "lostms") == 0) p.lostms = (int)number;
  else if (strcmp(key, "loststop") == 0) p.loststop = (int)number;
  else if (strcmp(key, "recov") == 0) p.recov = (int)number;
  else if (strcmp(key, "hb") == 0) p.hb = (int)number;
  else if (strcmp(key, "tel") == 0) p.tel = (int)number;
  else if (strcmp(key, "loop") == 0) p.loop = (int)number;
  else if (strcmp(key, "white") == 0) p.white = (int)number;
  else if (strcmp(key, "flip") == 0) p.flip = (int)number;
  else if (strcmp(key, "ldir") == 0) p.ldir = (int)number;
  else if (strcmp(key, "rdir") == 0) p.rdir = (int)number;
}

int roundHalfEven(double v) { return (int)nearbyint(v); }  // igual ao round() do Python

}  // namespace

const char* stateName(State s) { return STATE_NAMES[(int)s]; }

Core::Core(Output& out, const char* fw) : out_(out), fw_(fw) {
  for (int i = 0; i < SENSORS; ++i) {
    mins_[i] = 4095;
    maxs_[i] = 0;
    values_[i] = 0;
  }
  line_[0] = '\0';
}

// ------------------------------------------------------------------ saída
void Core::emit(const char* text) {
  char buf[MAX_LINE + 1];
  snprintf(buf, sizeof(buf), "%s", text);
  out_.line(buf);
}

void Core::emitf(const char* fmt, ...) {
  char buf[MAX_LINE + 1];
  va_list args;
  va_start(args, fmt);
  vsnprintf(buf, sizeof(buf), fmt, args);
  va_end(args);
  out_.line(buf);
}

void Core::emitSta() {
  emitf("STA st=%s cal=%d x=%d xt=%d lap=%lld why=%s fw=%s tel=%d onlink=%s hb=%d", stateName(state_), cal_ ? 1 : 0,
        crossings_, p_.cross, (long long)lapMs_, stopReason_[0] ? stopReason_ : "-", fw_, p_.tel,
        p_.onlinkStop ? "stop" : "continue", p_.hb);
}

void Core::emitPar() {
  char line[MAX_LINE + 1];
  char value[32];
  for (int start = 0; start < SPEC_COUNT; start += 12) {
    size_t used = (size_t)snprintf(line, sizeof(line), "PAR");
    for (int i = start; i < SPEC_COUNT && i < start + 12; ++i) {
      paramText(p_, SPECS[i].key, value, sizeof(value));
      used += (size_t)snprintf(line + used, sizeof(line) - used, " %s=%s", SPECS[i].key, value);
      if (used >= sizeof(line)) break;
    }
    emit(line);
  }
}

void Core::setState(State s, const char* reason) {
  if (s == state_) return;
  state_ = s;
  if (reason != nullptr && reason[0]) snprintf(stopReason_, sizeof(stopReason_), "%s", reason);
  emitSta();
}

void Core::nak(int seq, const char* code, const char* msg) { emitf("NAK %d code=%s msg=%s", seq, code, msg); }

// ------------------------------------------------------------------ entrada
void Core::connect(int64_t /*now*/) {
  connected_ = true;
  lastRx_ = now_;
  emitf("HELLO fw=%s proto=1 st=%s cal=%d name=Noctario", fw_, stateName(state_), cal_ ? 1 : 0);
  emitSta();
  emitPar();
}

void Core::disconnect() { connected_ = false; }

void Core::feed(uint8_t byte, int64_t /*now*/) {
  if (byte == '!') {                       // parada de emergência, antes de qualquer análise
    len_ = 0;
    overflow_ = false;
    estop("bt");
    return;
  }
  if (byte == '\n' || byte == '\r') {
    if (overflow_) {                       // linha longa demais: descartada inteira
      overflow_ = false;
      len_ = 0;
      lastRx_ = now_;
      emit("NAK 0 code=SYNTAX msg=linha_longa_demais");
    } else if (len_ > 0) {
      line_[len_] = '\0';
      len_ = 0;
      lastRx_ = now_;
      handle(line_);
    }
    return;
  }
  if (overflow_) return;
  if (len_ < MAX_LINE) {
    line_[len_++] = (char)byte;
  } else {
    overflow_ = true;
    len_ = 0;
  }
}

void Core::estop(const char* source) {
  pwmL_ = pwmR_ = 0;
  ramp_ = 0.0;
  if (inRun(state_)) lapMs_ = now_ - lapStart_;
  snprintf(stopReason_, sizeof(stopReason_), "estop");
  if (state_ != State::ESTOP) {
    state_ = State::ESTOP;
    emitf("EVT estop src=%s", source);
    emitSta();
  }
}

void Core::handle(char* line) {
  char* tokens[40];
  int count = 0;
  for (char* tok = strtok(line, " \t"); tok != nullptr; tok = strtok(nullptr, " \t")) {
    if (count == 40) {                     // mais campos do que qualquer comando válido tem
      emit("NAK 0 code=SYNTAX msg=campos_demais");
      return;
    }
    tokens[count++] = tok;
  }
  if (count == 0) return;
  if (strcmp(tokens[0], "HB") == 0) return;
  long seqValue = 0;
  bool digits = count >= 2 && tokens[1][0] != '+' && tokens[1][0] != '-' && parseInt(tokens[1], seqValue);
  if (strcmp(tokens[0], "CMD") != 0 || count < 3 || !digits) {
    emit("NAK 0 code=SYNTAX msg=linha_malformada");
    return;
  }
  int seq = (int)seqValue;
  char verb[16];
  snprintf(verb, sizeof(verb), "%s", tokens[2]);
  for (char* c = verb; *c; ++c) *c = (char)toupper((unsigned char)*c);
  char* keys[37];
  char* values[37];
  int args = 0;
  for (int i = 3; i < count; ++i) {
    char* eq = strchr(tokens[i], '=');
    if (eq == nullptr || eq == tokens[i]) {
      nak(seq, "SYNTAX", "argumento_malformado");
      return;
    }
    *eq = '\0';
    keys[args] = tokens[i];
    values[args] = eq + 1;
    args++;
  }
  auto arg = [&](const char* key) -> const char* {
    for (int i = args - 1; i >= 0; --i) {
      if (strcmp(keys[i], key) == 0) return values[i];
    }
    return nullptr;
  };

  if (strcmp(verb, "PING") == 0) {
    emitf("ACK %d pong=1 t=%lld", seq, (long long)now_);
  } else if (strcmp(verb, "INFO") == 0) {
    emitf("ACK %d fw=%s proto=1 sensors=%d cal=%d", seq, fw_, SENSORS, cal_ ? 1 : 0);
  } else if (strcmp(verb, "STATUS") == 0) {
    emitf("ACK %d st=%s", seq, stateName(state_));
    emitSta();
  } else if (strcmp(verb, "START") == 0) {
    if (state_ == State::ESTOP) return nak(seq, "ESTOP", "em_parada_de_emergencia:_use_CLEAR");
    if (!cal_) return nak(seq, "NOCAL", "sensores_nao_calibrados:_use_CAL");
    if (!(state_ == State::READY || state_ == State::STOP || state_ == State::DONE)) {
      return nak(seq, "STATE", "nao_e_possivel_partir_neste_estado");
    }
    crossings_ = 0;
    lastCross_ = NEVER;
    lostSince_ = NONE;
    lastErr_ = 0;
    ramp_ = 0.0;
    lapStart_ = now_;
    lapMs_ = 0;
    stopReason_[0] = '\0';
    setState(State::RUN);
    emitf("ACK %d st=RUN", seq);
  } else if (strcmp(verb, "STOP") == 0) {
    if (state_ == State::RUN || state_ == State::LOST) {
      setState(State::STOPPING, "cmd");    // percurso: freia pela rampa
    } else if (state_ == State::TEST || state_ == State::CAL) {
      setState(cal_ ? State::READY : State::IDLE);   // bancada ou calibração: para na hora (não é volta)
    }
    emitf("ACK %d st=%s", seq, stateName(state_));
  } else if (strcmp(verb, "CLEAR") == 0) {
    if (state_ == State::ESTOP) setState(cal_ ? State::READY : State::IDLE);
    emitf("ACK %d st=%s", seq, stateName(state_));
  } else if (strcmp(verb, "CAL") == 0) {
    if (state_ == State::ESTOP) return nak(seq, "ESTOP", "em_parada_de_emergencia:_use_CLEAR");
    if (!isStopped(state_)) return nak(seq, "STATE", "calibracao_so_com_o_robo_parado");
    long duration = 3000, autoMode = 0;
    const char* ms = arg("ms");
    const char* au = arg("auto");
    if ((ms != nullptr && !parseInt(ms, duration)) || (au != nullptr && !parseInt(au, autoMode))) {
      return nak(seq, "SYNTAX", "ms_e_auto_devem_ser_inteiros");
    }
    if (duration < 500 || duration > 20000 || (autoMode != 0 && autoMode != 1)) {
      return nak(seq, "RANGE", "ms_de_500_a_20000;_auto_0_ou_1");
    }
    for (int i = 0; i < SENSORS; ++i) {
      mins_[i] = 4095;
      maxs_[i] = 0;
    }
    cal_ = false;                          // a calibração anterior deixa de valer: interrompida, não há partida
    calUntil_ = now_ + duration;
    calAuto_ = autoMode == 1;
    setState(State::CAL);
    emitf("ACK %d st=CAL ms=%ld auto=%ld", seq, duration, autoMode);
  } else if (strcmp(verb, "SET") == 0) {
    if (args == 0) return nak(seq, "SYNTAX", "nada_para_ajustar");
    applySet(seq, keys, values, args);
  } else if (strcmp(verb, "PARAMS") == 0) {
    emitf("ACK %d", seq);
    emitPar();
  } else if (strcmp(verb, "SAVE") == 0) {
    saved_ = p_;
    saveRequested_ = true;
    emitf("ACK %d saved=1", seq);
  } else if (strcmp(verb, "DEFAULTS") == 0) {
    if (!isStopped(state_) && state_ != State::ESTOP) return nak(seq, "STATE", "padroes_so_com_o_robo_parado");
    p_ = Params();
    emitf("ACK %d defaults=1", seq);
    emitPar();
  } else if (strcmp(verb, "RESETX") == 0) {
    crossings_ = 0;
    emitf("ACK %d x=0", seq);
  } else if (strcmp(verb, "TEL") == 0) {
    const char* hz = arg("hz");
    if (hz == nullptr) return nak(seq, "SYNTAX", "use_TEL_hz=0..50");
    Params candidate = p_;
    char err[80];
    if (!parseParam("tel", hz, candidate, err, sizeof(err))) return nak(seq, "RANGE", err);
    p_ = candidate;
    emitf("ACK %d tel=%d", seq, p_.tel);
  } else if (strcmp(verb, "SENS") == 0) {
    emitf("ACK %d", seq);
    emitf("SEN cal=%d,%d,%d,%d,%d,%d,%d,%d pos=%d line=%d x=%d xin=%d", values_[0], values_[1], values_[2],
          values_[3], values_[4], values_[5], values_[6], values_[7], pos_, seen_ ? 1 : 0, crossings_,
          crossRaw_ ? 1 : 0);
  } else if (strcmp(verb, "MOTOR") == 0) {
    if (!isStopped(state_)) return nak(seq, "STATE", "teste_de_motores_so_com_o_robo_parado");
    long l = 0, r = 0, ms = 500;
    const char* tl = arg("l");
    const char* tr = arg("r");
    const char* tm = arg("ms");
    if ((tl && !parseInt(tl, l)) || (tr && !parseInt(tr, r)) || (tm && !parseInt(tm, ms))) {
      return nak(seq, "SYNTAX", "l,_r_e_ms_devem_ser_inteiros");
    }
    if (l < -255 || l > 255 || r < -255 || r > 255 || ms < 100 || ms > 3000) {
      return nak(seq, "RANGE", "l_e_r_de_-255_a_255;_ms_de_100_a_3000");
    }
    testL_ = (int)l;
    testR_ = (int)r;
    testUntil_ = now_ + ms;
    setState(State::TEST);
    emitf("ACK %d st=TEST", seq);
  } else {
    nak(seq, "UNKNOWN", "verbo_desconhecido");
  }
}

bool Core::parseParam(const char* key, const char* value, Params& target, char* err, size_t errSize) {
  const Spec* spec = findSpec(key);
  if (spec == nullptr) {
    snprintf(err, errSize, "parametro_desconhecido:%s", key);
    return false;
  }
  if (spec->kind == 'c') {
    char low[16];
    snprintf(low, sizeof(low), "%s", value);
    for (char* c = low; *c; ++c) *c = (char)tolower((unsigned char)*c);
    if (strcmp(low, "stop") != 0 && strcmp(low, "continue") != 0) {
      snprintf(err, errSize, "%s:_use_stop_ou_continue", key);
      return false;
    }
    setParam(target, key, 0, strcmp(low, "stop") == 0);
    return true;
  }
  double number = 0;
  if (!parseNumber(value, number)) {
    snprintf(err, errSize, "%s:_nao_e_numero", key);
    return false;
  }
  if (spec->kind == 'i' && number != floor(number)) {
    snprintf(err, errSize, "%s:_use_inteiro", key);
    return false;
  }
  if (number < spec->low || number > spec->high) {
    snprintf(err, errSize, "%s:_fora_do_limite", key);
    return false;
  }
  if ((spec->c1 != 0 || spec->c2 != 0) && (int)number != spec->c1 && (int)number != spec->c2) {
    snprintf(err, errSize, "%s:_valor_nao_permitido", key);
    return false;
  }
  setParam(target, key, number, false);
  return true;
}

bool Core::applySet(int seq, char** keys, char** values, int count) {
  bool moving = !isStopped(state_) && state_ != State::ESTOP;
  if (moving) {
    for (int i = 0; i < count; ++i) {
      const Spec* spec = findSpec(keys[i]);
      if (spec != nullptr && spec->runtimeOnly) {
        nak(seq, "STATE", "parametro_so_com_o_robo_parado");
        return false;
      }
    }
  }
  Params candidate = p_;
  char err[80];
  for (int i = 0; i < count; ++i) {
    if (!parseParam(keys[i], values[i], candidate, err, sizeof(err))) {
      nak(seq, "RANGE", err);
      return false;
    }
  }
  if (candidate.base > candidate.max) {
    nak(seq, "RANGE", "PWM_base_maior_que_o_PWM_maximo");
    return false;
  }
  if (candidate.minpwm > candidate.base) {
    nak(seq, "RANGE", "PWM_minimo_maior_que_o_PWM_base");
    return false;
  }
  p_ = candidate;
  char line[MAX_LINE + 1];
  char value[32];
  size_t used = (size_t)snprintf(line, sizeof(line), "ACK %d", seq);
  for (int i = 0; i < count && used < sizeof(line); ++i) {
    bool repeated = false;                 // chave repetida: vale o último valor, na posição da primeira
    for (int j = 0; j < i; ++j) repeated = repeated || strcmp(keys[j], keys[i]) == 0;
    if (repeated) continue;
    paramText(p_, keys[i], value, sizeof(value));
    used += (size_t)snprintf(line + used, sizeof(line) - used, " %s=%s", keys[i], value);
  }
  emit(line);
  emitPar();
  return true;
}

// ------------------------------------------------------------------ laço de controle
void Core::readLine(const uint16_t raw[SENSORS]) {
  int values[SENSORS];
  for (int i = 0; i < SENSORS; ++i) {
    int span = (int)maxs_[i] - (int)mins_[i];
    int c = 0;
    if (span > 0) {
      long scaled = ((long)raw[i] - (long)mins_[i]) * 1000L / span;
      c = scaled < 0 ? 0 : (scaled > 1000 ? 1000 : (int)scaled);
    }
    values[i] = p_.white ? 1000 - c : c;
  }
  for (int i = 0; i < SENSORS; ++i) values_[i] = p_.flip ? values[SENSORS - 1 - i] : values[i];
  int best = 0;
  for (int i = 0; i < SENSORS; ++i) best = values_[i] > best ? values_[i] : best;
  seen_ = best >= p_.thr;
  if (seen_) {
    long long weighted = 0, total = 0;
    for (int i = 0; i < SENSORS; ++i) {
      if (values_[i] >= 50) {
        weighted += (long long)i * 1000 * values_[i];
        total += values_[i];
      }
    }
    pos_ = total ? (int)(weighted / total) : CENTER;
  } else {
    pos_ = lastErr_ < 0 ? 0 : 2 * CENTER;
  }
  err_ = pos_ - CENTER;
}

void Core::tick(int64_t now, const uint16_t raw[SENSORS], bool crossPin, int& left, int& right) {
  int64_t elapsed = now - now_;
  double dt = (elapsed > 0 ? (double)elapsed : 0.0) / 1000.0;
  now_ = now;
  const Params& p = p_;
  if (state_ == State::CAL) {
    for (int i = 0; i < SENSORS; ++i) {
      if (raw[i] < mins_[i]) mins_[i] = raw[i];
      if (raw[i] > maxs_[i]) maxs_[i] = raw[i];
    }
  }
  readLine(raw);
  crossRaw_ = crossPin;
  bool active = crossPin == (p.xact != 0);
  if (active && !crossPrev_ && inRun(state_) && now - lastCross_ >= p.deb) {
    crossings_++;
    lastCross_ = now;
    emitf("EVT cross n=%d t=%lld", crossings_, (long long)now);
  }
  crossPrev_ = active;
  int l = 0, r = 0;
  State state = state_;
  if (state == State::ESTOP) {
    l = r = 0;
  } else if (state == State::CAL) {
    if (calAuto_) {
      int swing = ((now / 600) % 2 == 0) ? 1 : -1;
      l = 80 * swing;
      r = -80 * swing;
    }
    if (now >= calUntil_) {
      bool ok = true;
      for (int i = 0; i < SENSORS; ++i) ok = ok && ((int)maxs_[i] - (int)mins_[i] >= CAL_MIN_SPAN);
      cal_ = ok;
      emit(ok ? "EVT cal ok=1" : "EVT cal ok=0 msg=sensores_sem_contraste");
      setState(ok ? State::READY : State::IDLE);
      l = r = 0;
    }
  } else if (state == State::TEST) {
    l = testL_;
    r = testR_;
    if (now >= testUntil_) {
      l = r = 0;
      setState(cal_ ? State::READY : State::IDLE);
    }
  } else if (inRun(state)) {
    if (p.hb && (double)(now - lastRx_) > p.hb * linkScale && p.onlinkStop && state != State::STOPPING) {
      setState(State::STOPPING, "link");
      state = State::STOPPING;
    }
    if (p.cross && crossings_ >= p.cross && state != State::STOPPING) {
      setState(State::STOPPING, "done");
      state = State::STOPPING;
    }
    if (state == State::RUN) {
      if (!seen_) {
        if (lostSince_ == NONE) lostSince_ = now;
        if (now - lostSince_ >= p.lostms) {
          emit("EVT lost");
          setState(State::LOST);
          state = State::LOST;
        }
      } else {
        lostSince_ = NONE;
      }
    } else if (state == State::LOST) {
      int64_t since = lostSince_ != NONE ? lostSince_ : now;
      if (seen_) {
        emitf("EVT found ms=%lld", (long long)(now - since));
        lostSince_ = NONE;
        setState(State::RUN);
        state = State::RUN;
      } else if (now - since >= p.lostms + p.loststop) {
        setState(State::STOPPING, "lost");
        state = State::STOPPING;
      }
    }
    double ratio = (double)(err_ < 0 ? -err_ : err_) / CENTER;
    double target = state == State::STOPPING ? 0.0 : p.base * (1.0 - p.adapt * (ratio < 1.0 ? ratio : 1.0));
    int rate = target > ramp_ ? p.accel : p.decel;
    if (rate <= 0) {
      ramp_ = target;
    } else {
      double step = rate * dt;
      if (target > ramp_) ramp_ = (ramp_ + step < target) ? ramp_ + step : target;
      else ramp_ = (ramp_ - step > target) ? ramp_ - step : target;
    }
    corr_ = p.kp * err_ + p.kd * (err_ - lastErr_);
    lastErr_ = err_;
    if (state == State::LOST) {
      int side = err_ > 0 ? 1 : -1;
      l = p.recov * side;
      r = -p.recov * side;
    } else {
      l = roundHalfEven(ramp_ + corr_);
      r = roundHalfEven(ramp_ - corr_);
    }
    l = l < p.minpwm ? p.minpwm : (l > p.max ? p.max : l);
    r = r < p.minpwm ? p.minpwm : (r > p.max ? p.max : r);
    if (state == State::STOPPING && ramp_ <= 0.5) {
      l = r = 0;
      lapMs_ = now - lapStart_;
      const char* reason = stopReason_[0] ? stopReason_ : "cmd";
      if (strcmp(reason, "done") == 0) {
        emitf("EVT done lap_ms=%lld x=%d", (long long)lapMs_, crossings_);
        setState(State::DONE);
      } else {
        char why[12];
        snprintf(why, sizeof(why), "%s", reason);
        emitf("EVT stop reason=%s", why);
        setState(State::STOP);
      }
    } else {
      lapMs_ = now - lapStart_;
    }
  }
  pwmL_ = l * p.ldir;
  pwmR_ = r * p.rdir;
  left = pwmL_;
  right = pwmR_;
  if (p.tel && connected_ && now - telLast_ >= 1000 / p.tel) {
    telLast_ = now;
    emitf("TEL t=%lld st=%s pos=%d err=%d corr=%.2f l=%d r=%d x=%d lost=%d b=%d s=%d,%d,%d,%d,%d,%d,%d,%d",
          (long long)now, stateName(state_), pos_, err_, corr_, pwmL_, pwmR_, crossings_, seen_ ? 0 : 1, (int)ramp_,
          values_[0], values_[1], values_[2], values_[3], values_[4], values_[5], values_[6], values_[7]);
  }
}

bool Core::motorsEnabled() const {
  return state_ == State::RUN || state_ == State::LOST || state_ == State::STOPPING || state_ == State::TEST ||
         (state_ == State::CAL && calAuto_);
}

bool Core::takeSaveRequest() {
  bool requested = saveRequested_;
  saveRequested_ = false;
  return requested;
}

void Core::restore(const Params& stored, const uint16_t* mins, const uint16_t* maxs, bool calibrated) {
  // o que vem da NVS passa pelos MESMOS limites do SET: memória corrompida não vira PWM 255 nem laço a 0 Hz
  char value[32];
  char err[80];
  Params probe;
  bool valid = true;
  for (int i = 0; i < SPEC_COUNT && valid; ++i) {
    paramText(stored, SPECS[i].key, value, sizeof(value));
    valid = parseParam(SPECS[i].key, value, probe, err, sizeof(err));
  }
  valid = valid && stored.base <= stored.max && stored.minpwm <= stored.base;
  p_ = valid ? stored : Params();          // inválidos: padrões (o PC vê no PAR)
  saved_ = p_;
  bool cal = calibrated && mins != nullptr && maxs != nullptr;
  for (int i = 0; cal && i < SENSORS; ++i) cal = maxs[i] <= 4095 && (int)maxs[i] - (int)mins[i] >= CAL_MIN_SPAN;
  if (cal) {
    for (int i = 0; i < SENSORS; ++i) {
      mins_[i] = mins[i];
      maxs_[i] = maxs[i];
    }
  }
  cal_ = cal;
  state_ = cal ? State::READY : State::IDLE;
}

}  // namespace noct
