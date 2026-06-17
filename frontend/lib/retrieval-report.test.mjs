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
        reference_id: 'US20240123456A1',
        title: '一种智能检索方法',
        source: 'google_patents',
        url: 'https://patents.google.com/patent/US20240123456A1',
        similarity_score: 0.87,
      },
    ],
    similar_patents: [],
  });

  assert.equal(references.length, 1);
  assert.equal(references[0].patentId, 'US20240123456A1');
  assert.equal(references[0].url, 'https://patents.google.com/patent/US20240123456A1');
  assert.equal(references[0].similarityScore, 0.87);
});

test('builds patent url when url is missing', async () => {
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

test('normalizes similar_patents and preserves comparison fields', async () => {
  const { getRetrievalPatentReferences } = await loadModule();
  const references = getRetrievalPatentReferences({
    similar_patents: [
      {
        patent_id: 'US2023123456A1',
        title: 'Adaptive display patent',
        source: 'google_patents',
        applicant: 'Verified Applicant',
        publication_date: '2025-01-01',
        similarity_score: 88,
        key_similarities: ['特征 A 相同'],
        key_differences: ['区别 B'],
      },
    ],
  });

  assert.equal(references.length, 1);
  assert.equal(references[0].patentId, 'US2023123456A1');
  assert.equal(references[0].title, 'Adaptive display patent');
  assert.equal(references[0].source, 'google_patents');
  assert.equal(references[0].applicant, 'Verified Applicant');
  assert.equal(references[0].publicationDate, '2025-01-01');
  assert.equal(references[0].similarityScore, 0.88);
  assert.deepEqual(references[0].similarities, ['特征 A 相同']);
  assert.deepEqual(references[0].differences, ['区别 B']);
  assert.equal(references[0].url, 'https://patents.google.com/patent/US2023123456A1');
});

test('normalizes tool-style key_references and search_results', async () => {
  const { getRetrievalPatentReferences } = await loadModule();
  const references = getRetrievalPatentReferences({
    key_references: [
      {
        publication_number: 'US10987654B2',
        name: '多屏画面处理系统',
        database: 'uspto',
        assignee: 'Verified Applicant',
        publicationDate: '2024-05-01',
        score: 76,
        key_features: ['多屏显示', '画面映射'],
        distinguishing_features: ['未公开姿态补偿'],
      },
    ],
    search_results: ['US7654321B2'],
  });

  assert.equal(references.length, 2);
  assert.equal(references[0].patentId, 'US10987654B2');
  assert.equal(references[0].title, '多屏画面处理系统');
  assert.equal(references[0].applicant, 'Verified Applicant');
  assert.equal(references[0].similarityScore, 0.76);
  assert.deepEqual(references[0].similarities, ['多屏显示', '画面映射']);
  assert.deepEqual(references[0].differences, ['未公开姿态补偿']);
  assert.equal(references[1].patentId, 'US7654321B2');
});
