import tempfile, os
import memory
import memory_engine

fd, path = tempfile.mkstemp(suffix=".sqlite3"); os.close(fd)
try:
    memory.set_db_path(path)
    memory_engine.init()
    memory_engine.record_strategy("corrigir erro no projeto", "IDE + traceback", "examinar traceback antes de editar", "verified", .95)
    got = memory_engine.recall_strategies("corrigir erro no projeto")
    assert got and got[0]["score"] >= .95
    memory_engine.record_episode("corrigir erro no projeto", "adaptive", "verified", "teste passou")
    assert "verified" in memory_engine.compact_summary()
    print("FASE8 TESTS OK")
finally:
    try: os.remove(path)
    except OSError: pass
