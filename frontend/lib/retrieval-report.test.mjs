import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import test from 'node:test';
import ts from 'typescript';

async function loadModule() {
  const sourcePath = new URL('./retrieval-report.ts', import.meta.url);
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
  const outputPath = new URL(`retrieval-report-${Date.now()}.mjs`, tempDir);
  await writeFile(outputPath, output.outputText, 'utf8');
  return import(pathToFileURL(outputPath.pathname).href);
}

test('normalizes prior_art_references with backend url first', async () => {
  const { getRetrievalPatentReferences } = await loadModule();
  const references = getRetrievalPatentReferences({
    prior_art_references: [
      {
        reference_id: 'CN112233445A',
        title: '一种智能检索方法',
        source: 'CNIPA',
        url: 'https://example.test/original-cn',
        similarity_score: 0.87,
      },
    ],
    similar_patents: [],
  });

  assert.equal(references.length, 1);
  assert.equal(references[0].patentId, 'CN112233445A');
  assert.equal(references[0].url, 'https://example.test/original-cn');
  assert.equal(references[0].similarityScore, 0.87);
});

test('builds fallback patent url when url is missing', async () => {
  const { getRetrievalPatentReferences } = await loadModule();
  const references = getRetrievalPatentReferences({
    prior_art_references: [
      {
        reference_id: 'US 1234567 B2',
        source: 'USPTO',
        title: 'Search system',
      },
    ],
  });

  assert.equal(references.length, 1);
  assert.equal(references[0].url, 'https://patents.google.com/patent/US1234567B2');
});

test('falls back to legacy similar_patents and preserves comparison fields', async () => {
  const { getRetrievalPatentReferences } = await loadModule();
  const references = getRetrievalPatentReferences({
    similar_patents: [
      {
        patent_id: 'EP1234567A1',
        title: 'Legacy patent',
        source: 'EPO',
        applicant: 'Example Applicant',
        publication_date: '2025-01-01',
        similarity_score: 88,
        key_similarities: ['特征 A 相同'],
        key_differences: ['区别 B'],
      },
    ],
  });

  assert.equal(references.length, 1);
  assert.equal(references[0].patentId, 'EP1234567A1');
  assert.equal(references[0].title, 'Legacy patent');
  assert.equal(references[0].source, 'EPO');
  assert.equal(references[0].applicant, 'Example Applicant');
  assert.equal(references[0].publicationDate, '2025-01-01');
  assert.equal(references[0].similarityScore, 0.88);
  assert.deepEqual(references[0].similarities, ['特征 A 相同']);
  assert.deepEqual(references[0].differences, ['区别 B']);
  assert.equal(references[0].url, 'https://worldwide.espacenet.com/patent/search?q=EP1234567A1');
});
