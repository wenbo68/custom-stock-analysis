import { describe, expect, it } from 'vitest';
import { parseCallError } from '../transcriptError';

const GEMINI_503 =
  'litellm.ServiceUnavailableError: GeminiException - {\n  "error": {\n    "code": 503,\n    "message": "The service is currently unavailable.",\n    "status": "UNAVAILABLE"\n  }\n}\n';

describe('parseCallError', () => {
  it('reads code, status and message, in that order, out of a Gemini error body', () => {
    expect(parseCallError(GEMINI_503)).toEqual([
      ['code', 503],
      ['status', 'UNAVAILABLE'],
      ['message', 'The service is currently unavailable.'],
    ]);
  });

  it('reads a flat body and leaves out the facts it lacks', () => {
    expect(parseCallError('Boom - {"message": "quota exceeded", "code": 429}')).toEqual([
      ['code', 429],
      ['message', 'quota exceeded'],
    ]);
  });

  it('turns a text with no error body into one message fact', () => {
    expect(parseCallError("RuntimeError('boom')\n")).toEqual([['message', "RuntimeError('boom')"]]);
    expect(parseCallError('odd {not json}')).toEqual([['message', 'odd {not json}']]);
    expect(parseCallError('{"error": "flat string"}')).toEqual([['message', '{"error": "flat string"}']]);
  });
});
