// Noctário — camada Arduino (ESP32 DevKit + TB6612FNG + 8 QTR analógicos + sensor de cruzamento + LED).
//
// PINAGEM conferida com os sketches originais Noctario_JARVIS (20/10) e Nefarious_6 (28/10):
//   motor DIREITO  (canal A do TB6612FNG): PWMA 21, AIN1 18, AIN2 19
//   motor ESQUERDO (canal B do TB6612FNG): PWMB 23, BIN1 4,  BIN2 22
//   STBY 5 · sensor de cruzamento 34 · LED 15
//   QTR: pinos na ordem do sketch; orientação física esquerda/direita ainda exige ensaio na bancada.
//
// Cuidados de hardware (ver README.md): GPIO 25/26/27/14/12/13 são ADC2 (o Wi-Fi nunca é ligado aqui);
// GPIO 12 é pino de strapping (nível alto no boot pode impedir a partida); GPIO 34 não tem pull-up
// interno; GPIO 5 e 15 podem pulsar no boot — o STBY vai a nível BAIXO antes de qualquer outra coisa.
// A parada pelo Bluetooth NÃO substitui um botão físico que corte a alimentação dos motores.
#include <Arduino.h>
#include <BluetoothSerial.h>
#include <Preferences.h>

#include <initializer_list>

#include "noct_core.h"

namespace {

constexpr int PIN_PWMA = 21, PIN_AIN1 = 18, PIN_AIN2 = 19;   // motor direito
constexpr int PIN_PWMB = 23, PIN_BIN1 = 4, PIN_BIN2 = 22;    // motor esquerdo
constexpr int PIN_STBY = 5;
constexpr int PIN_CROSS = 34;
constexpr int PIN_LED = 15;
constexpr int PIN_QTR[noct::SENSORS] = {32, 33, 25, 26, 27, 14, 12, 13};
constexpr uint32_t PWM_HZ = 20000;                           // TB6612FNG aceita até 100 kHz; 20 kHz é inaudível
constexpr uint8_t PWM_BITS = 8;
constexpr int CH_A = 0, CH_B = 1;
constexpr uint16_t NVS_VERSION = 1;                          // muda se a estrutura Params mudar

BluetoothSerial bt;
Preferences nvs;

class BtOutput : public noct::Output {
 public:
  void line(const char* text) override {
    if (bt.hasClient()) {
      bt.print(text);
      bt.print('\n');
    }
  }
};

BtOutput output;
noct::Core core(output, "noctario-1.0");
bool linked = false;
uint32_t lastTickUs = 0;

void pwmSetup() {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(PIN_PWMA, PWM_HZ, PWM_BITS);
  ledcAttach(PIN_PWMB, PWM_HZ, PWM_BITS);
#else
  ledcSetup(CH_A, PWM_HZ, PWM_BITS);
  ledcSetup(CH_B, PWM_HZ, PWM_BITS);
  ledcAttachPin(PIN_PWMA, CH_A);
  ledcAttachPin(PIN_PWMB, CH_B);
#endif
}

void pwmWrite(int pin, int channel, uint32_t duty) {
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
  (void)channel;
  ledcWrite(pin, duty);
#else
  (void)pin;
  ledcWrite(channel, duty);
#endif
}

// um canal do TB6612FNG: sinal = sentido, módulo = PWM; zero = livre (IN1 = IN2 = baixo)
void driveChannel(int pwm, int in1, int in2, int pwmPin, int channel) {
  digitalWrite(in1, pwm > 0 ? HIGH : LOW);
  digitalWrite(in2, pwm < 0 ? HIGH : LOW);
  pwmWrite(pwmPin, channel, (uint32_t)abs(pwm));
}

void drive(int left, int right, bool enabled) {
  if (!enabled) left = right = 0;
  driveChannel(right, PIN_AIN1, PIN_AIN2, PIN_PWMA, CH_A);
  driveChannel(left, PIN_BIN1, PIN_BIN2, PIN_PWMB, CH_B);
  digitalWrite(PIN_STBY, enabled ? HIGH : LOW);
}

void led(noct::State state, uint32_t ms) {
  bool on = true;
  switch (state) {
    case noct::State::IDLE: on = (ms / 500) % 2 == 0; break;          // 1 Hz: sem calibração
    case noct::State::CAL: on = (ms / 100) % 2 == 0; break;           // 5 Hz: calibrando
    case noct::State::LOST: on = (ms / 80) % 2 == 0; break;           // recuperando a linha
    case noct::State::ESTOP: on = (ms / 50) % 2 == 0; break;          // 10 Hz: emergência
    case noct::State::DONE: {                                          // piscada dupla a cada 1,2 s
      uint32_t phase = ms % 1200;
      on = phase < 150 || (phase >= 300 && phase < 450);
      break;
    }
    case noct::State::STOP: on = (ms / 1000) % 2 == 0; break;
    case noct::State::TEST: on = (ms / 120) % 2 == 0; break;
    default: on = true; break;                                         // pronto ou em percurso: aceso
  }
  digitalWrite(PIN_LED, on ? HIGH : LOW);
}

void loadNvs() {
  nvs.begin("noctario", true);
  if (nvs.getUShort("ver", 0) == NVS_VERSION && nvs.getBytesLength("params") == sizeof(noct::Params)) {
    noct::Params stored;
    uint16_t mins[noct::SENSORS], maxs[noct::SENSORS];
    nvs.getBytes("params", &stored, sizeof(stored));
    bool cal = nvs.getBool("cal", false) && nvs.getBytes("mins", mins, sizeof(mins)) == sizeof(mins) &&
               nvs.getBytes("maxs", maxs, sizeof(maxs)) == sizeof(maxs);
    core.restore(stored, cal ? mins : nullptr, cal ? maxs : nullptr, cal);
  }
  nvs.end();
}

void saveNvs() {
  nvs.begin("noctario", false);
  nvs.putUShort("ver", NVS_VERSION);
  nvs.putBytes("params", &core.params(), sizeof(noct::Params));
  nvs.putBytes("mins", core.mins(), sizeof(uint16_t) * noct::SENSORS);
  nvs.putBytes("maxs", core.maxs(), sizeof(uint16_t) * noct::SENSORS);
  nvs.putBool("cal", core.calibrated());
  nvs.end();
}

}  // namespace

void setup() {
  pinMode(PIN_STBY, OUTPUT);
  digitalWrite(PIN_STBY, LOW);                                  // motores desligados antes de qualquer coisa
  for (int pin : {PIN_AIN1, PIN_AIN2, PIN_BIN1, PIN_BIN2}) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
  pwmSetup();
  drive(0, 0, false);
  pinMode(PIN_LED, OUTPUT);
  pinMode(PIN_CROSS, INPUT);                                    // GPIO 34: só entrada, sem pull-up interno
  analogReadResolution(12);
  for (int pin : PIN_QTR) analogSetPinAttenuation(pin, ADC_11db);
  Serial.begin(115200);
  loadNvs();
  bt.begin("Noctario");                                         // Bluetooth Clássico (SPP); o Wi-Fi fica desligado
  lastTickUs = micros();
}

void loop() {
  bool client = bt.hasClient();
  if (client && !linked) {
    linked = true;
    core.connect(millis());
  } else if (!client && linked) {
    linked = false;
    core.disconnect();                                          // a política sem link (onlink) é do núcleo
  }
  while (bt.available() > 0) core.feed((uint8_t)bt.read(), millis());
  if (!core.motorsEnabled()) drive(0, 0, false);                // parada de emergência: corte imediato
  uint32_t period = 1000000UL / (uint32_t)core.params().loop;
  uint32_t nowUs = micros();
  if (nowUs - lastTickUs >= period) {
    lastTickUs += period;
    if (nowUs - lastTickUs > 4 * period) lastTickUs = nowUs;   // atrasou muito: não tenta "recuperar" ciclos
    uint16_t raw[noct::SENSORS];
    for (int i = 0; i < noct::SENSORS; ++i) raw[i] = (uint16_t)analogRead(PIN_QTR[i]);
    bool cross = digitalRead(PIN_CROSS) == HIGH; // core aplica xact=0: LOW ativo, borda de descida
    int left = 0, right = 0;
    core.tick(millis(), raw, cross, left, right);
    drive(left, right, core.motorsEnabled());
    led(core.state(), millis());
  }
  if (core.takeSaveRequest()) saveNvs();
}
