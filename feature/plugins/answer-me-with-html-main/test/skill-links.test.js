import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const skill = readFileSync(new URL('../skills/answer-me-with-html/SKILL.md', import.meta.url), 'utf8');
const reply = skill.slice(skill.indexOf('5. Reply in the terminal'), skill.indexOf('\nWhen a page already exists'));
const lines = reply.split('\n');

test('page links: a served URL takes priority over host-specific local links', () => {
  const served = lines.findIndex((line) => line.includes('If the render output has a `link:` line'));
  const harness = lines.findIndex((line) => line.includes('Otherwise, in DeepSeek Harness'));
  const fallback = lines.findIndex((line) => line.includes('In other hosts'));
  assert.ok(served >= 0 && harness > served && fallback > harness, 'choose the served URL before either local-link branch');
  assert.match(lines[served], /skip.*local.*links/);
});

test('page links: Harness examples link directly to Windows and POSIX absolute paths', () => {
  const rule = lines.find((line) => line.includes('Otherwise, in DeepSeek Harness')) ?? '';
  const targets = [...rule.matchAll(/\[[^\]]+\]\(<([^>]+)>\)/g)].map((match) => match[1]);
  assert.ok(targets.some((path) => /^[A-Z]:\//i.test(path)), 'include a Windows absolute-path link');
  assert.ok(targets.some((path) => path.startsWith('/')), 'include a POSIX absolute-path link');
  for (const path of targets) {
    assert.doesNotMatch(path, /file:|\\/i, 'Harness destinations use paths with forward slashes');
  }
  assert.match(rule, /Document Preview/);
});

test('page links: other hosts retain file URLs and Harness retains its present card', () => {
  const fallback = lines.find((line) => line.includes('In other hosts')) ?? '';
  assert.match(fallback, /\[file:\/\/\/abs\/path\.html\]\(file:\/\/\/abs\/path\.html\)/);
  assert.match(fallback, /Codex, Antigravity/);
  const present = lines.find((line) => line.includes('`present` tool')) ?? '';
  assert.match(present, /absolute path.*before you reply/);
  assert.match(present, /Still end the reply with the link/);
});
