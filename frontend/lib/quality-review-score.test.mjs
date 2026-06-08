import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import test from 'node:test';
import ts from 'typescript';

async function loadModule() {
  const sourcePath = new URL('./quality-review-score.ts', import.meta.url);
  const source = await readFile(sourcePath, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ES2022,
      target: ts.ScriptTarget.ES2022,
      strict: true,
    },
  });
  const tempDir = new URL('./.test-output/', import.meta.url);
  await mkdir(tempDir, { recursive: true });
  const outputPath = new URL(`quality-review-score-${Date.now()}.mjs`, tempDir);
  await writeFile(outputPath, output.outputText, 'utf8');
  return import(pathToFileURL(outputPath.pathname).href);
}

test('normalizes zero-to-one score to percentage display', async () => {
  const { normalizeQualityScoreForDisplay } = await loadModule();
  assert.equal(normalizeQualityScoreForDisplay(0.78), 78);
});

test('preserves percentage score input', async () => {
  const { normalizeQualityScoreForDisplay } = await loadModule();
  assert.equal(normalizeQualityScoreForDisplay(78), 78);
});

test('returns null for invalid values', async () => {
  const { normalizeQualityScoreForDisplay } = await loadModule();
  assert.equal(normalizeQualityScoreForDisplay('0.78'), null);
  assert.equal(normalizeQualityScoreForDisplay(180), null);
});
