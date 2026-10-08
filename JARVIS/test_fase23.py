import human_in_loop

def main():
    assert human_in_loop.classify('analisar o erro').mode == 'AUTO'
    assert human_in_loop.classify('editar o arquivo').mode == 'SUPERVISE'
    assert human_in_loop.classify('apagar o arquivo').mode == 'CONFIRM'
    assert human_in_loop.classify('me mostre a senha').mode == 'BLOCK'
    a = human_in_loop.policy_for_tool('delete_path', 'organizar arquivos')
    assert a.mode == 'CONFIRM'
    print('FASE23_SMOKE_OK')

if __name__ == '__main__': main()
