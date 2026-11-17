import { describe, expect, it } from 'vitest';
import { cameraErrorState } from './CameraCapture';

describe('erros da câmera', () => {
  it('traduz os erros do navegador em orientações claras', () => {
    const err = (name: string) => Object.assign(new Error(name), { name });
    expect(cameraErrorState(err('NotAllowedError'))).toBe('negada');
    expect(cameraErrorState(err('SecurityError'))).toBe('negada');
    expect(cameraErrorState(err('NotFoundError'))).toBe('indisponivel');
    expect(cameraErrorState(err('OverconstrainedError'))).toBe('indisponivel');
    expect(cameraErrorState(err('NotReadableError'))).toBe('em_uso');
    expect(cameraErrorState(err('QualquerOutro'))).toBe('erro');
    expect(cameraErrorState(undefined)).toBe('erro');
  });
});
