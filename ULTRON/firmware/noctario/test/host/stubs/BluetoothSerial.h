// SÓ PARA TESTE NO PC: assinaturas do arduino-esp32 (2.x e 3.x) para conferir tipos e sintaxe do
// src/main.cpp sem o toolchain da ESP32. Não é o framework real e não substitui o primeiro `pio run`.
#pragma once
#include "Arduino.h"
class BluetoothSerial : public Print {
 public:
  bool begin(String localName = String(), bool isMaster = false);
  bool hasClient(void);
  int available(void);
  int read(void);
};
