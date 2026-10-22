// SÓ PARA TESTE NO PC: assinaturas do arduino-esp32 (2.x e 3.x) para conferir tipos e sintaxe do
// src/main.cpp sem o toolchain da ESP32. Não é o framework real e não substitui o primeiro `pio run`.
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#define HIGH 0x1
#define LOW 0x0
#define INPUT 0x01
#define OUTPUT 0x03
typedef enum { ADC_0db, ADC_2_5db, ADC_6db, ADC_11db } adc_attenuation_t;
void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, uint8_t val);
int digitalRead(uint8_t pin);
uint16_t analogRead(uint8_t pin);
void analogReadResolution(uint8_t bits);
void analogSetPinAttenuation(uint8_t pin, adc_attenuation_t attenuation);
unsigned long millis();
unsigned long micros();
#if defined(ESP_ARDUINO_VERSION_MAJOR) && ESP_ARDUINO_VERSION_MAJOR >= 3
bool ledcAttach(uint8_t pin, uint32_t freq, uint8_t resolution);
bool ledcWrite(uint8_t pin, uint32_t duty);
#else
double ledcSetup(uint8_t channel, double freq, uint8_t resolution_bits);
void ledcAttachPin(uint8_t pin, uint8_t channel);
void ledcWrite(uint8_t channel, uint32_t duty);
#endif
class String {
 public:
  String(const char* s = "") { (void)s; }
};
class Print {
 public:
  size_t print(const char* s);
  size_t print(char c);
};
class HardwareSerial : public Print {
 public:
  void begin(unsigned long baud);
};
extern HardwareSerial Serial;
