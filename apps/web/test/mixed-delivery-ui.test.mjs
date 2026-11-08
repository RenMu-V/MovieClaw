import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('mixed library wizard advertises supported delivery and watch import', () => {
  const source = readFileSync(new URL('../components/library-form-dialog.tsx', import.meta.url), 'utf8');
  assert.ok(!source.includes('一期仅扫描已有目录，暂不支持订阅自动路由或监听导入'));
  assert.ok(source.includes('支持订阅自动路由与监听导入'));
});

test('member target picker accepts mixed movie and tv without a mismatch warning', () => {
  const source = readFileSync(new URL('../components/download-target-dialog.tsx', import.meta.url), 'utf8');
  assert.ok(source.includes('library.kind === "mixed"'));
});
