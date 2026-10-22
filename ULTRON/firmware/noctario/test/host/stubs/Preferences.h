// SÓ PARA TESTE NO PC: assinaturas do arduino-esp32 (2.x e 3.x) para conferir tipos e sintaxe do
// src/main.cpp sem o toolchain da ESP32. Não é o framework real e não substitui o primeiro `pio run`.
#pragma once
#include "Arduino.h"
class Preferences {
 public:
  bool begin(const char* name, bool readOnly = false, const char* partition_label = NULL);
  void end();
  uint16_t getUShort(const char* key, uint16_t defaultValue = 0);
  size_t getBytesLength(const char* key);
  size_t getBytes(const char* key, void* buf, size_t maxLen);
  bool getBool(const char* key, bool defaultValue = false);
  size_t putUShort(const char* key, uint16_t value);
  size_t putBytes(const char* key, const void* value, size_t len);
  size_t putBool(const char* key, bool value);
};
