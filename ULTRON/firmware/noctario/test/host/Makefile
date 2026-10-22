# Testes do núcleo do firmware no PC (não precisa da ESP32): make && ./test_core
CXX ?= g++
CXXFLAGS ?= -std=c++17 -O1 -Wall -Wextra -Werror -ffp-contract=off
SRC = ../../src/noct_core.cpp

all: test_core replay

test_core: test_core.cpp $(SRC) ../../src/noct_core.h
	$(CXX) $(CXXFLAGS) -o $@ test_core.cpp $(SRC) -lm

replay: replay.cpp $(SRC) ../../src/noct_core.h
	$(CXX) $(CXXFLAGS) -o $@ replay.cpp $(SRC) -lm

clean:
	rm -f test_core replay
