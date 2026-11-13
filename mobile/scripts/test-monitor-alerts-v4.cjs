/**
 * Server-free regression tests for the actual API v4 polling controller.
 * Run: npm run test:monitor-alerts
 *
 * Uses the TypeScript dependency already present in mobile/node_modules.
 * No network, iOS device, Expo Push or policy/inspection writes.
 */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

// Load the repository's actual .ts implementation without adding a runtime dependency.
Module._extensions['.ts'] = (module, filename) => {
  const source = fs.readFileSync(filename, 'utf8');
  const js = ts.transpileModule(source, {
    fileName: filename,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  module._compile(js, filename);
};

const {
  createMonitoringPollControllerV4,
  MONITOR_POLL_INTERVAL_V4,
} = require(path.join(__dirname, '../src/api/backendV4/monitoringPollCore.ts'));

function queueItem(id, displayState = 'REVIEW_PENDING') {
  return {
    inspectionId: `00000000-0000-4000-8000-${String(id).padStart(12, '0')}`,
    inspectionNo: `INS-${String(id).padStart(6, '0')}`,
    partCode: 'COWL_COVER',
    displayState,
    predictedQuality: 'GOOD',
    reviewReason: displayState === 'REVIEW_PENDING' ? 'ABOVE_THRESHOLD' : null,
    errorCode: null,
    receivedAt: '2026-11-11T09:00:00Z',
  };
}

function harness(initialQueue = []) {
  let queue = initialQueue;
  let broken = false;
  let nowMs = 0;
  let nextHandle = 1;
  const timers = new Map();
  const receivedEvents = [];
  const source = 'API';
  const scheduler = {
    setTimeout(callback, delayMs) {
      const id = nextHandle++;
      timers.set(id, { callback, at: nowMs + delayMs });
      return id;
    },
    clearTimeout(id) { timers.delete(id); },
    now() { return nowMs; },
  };
  const reader = {
    source,
    async parts() { return { source, value: [] }; },
    async queue() {
      if (broken) throw new Error('temporary network failure');
      return { source, value: { items: queue, nextCursor: null } };
    },
  };
  const controller = createMonitoringPollControllerV4({
    reader,
    scheduler,
    onAlert: (alerts) => receivedEvents.push(...alerts),
  });
  return {
    controller,
    receivedEvents,
    updateQueue(next) { queue = next; },
    failQueue(shouldFail) { broken = shouldFail; },
    timerCount() { return timers.size; },
    nextDelay() {
      const timer = [...timers.values()].sort((a, b) => a.at - b.at)[0];
      return timer ? timer.at - nowMs : null;
    },
    async tick() {
      const next = [...timers.entries()].sort((a, b) => a[1].at - b[1].at)[0];
      assert.ok(next, 'expected a scheduled poll');
      const [handle, task] = next;
      timers.delete(handle);
      nowMs = task.at;
      task.callback();
      // Run all promise continuations from parts(), queue(), readFullQueue(), poll().
      await new Promise((resolve) => setImmediate(resolve));
    },
  };
}

test('initial baseline suppresses old REVIEW and FAILED; 5s interval is unchanged', async () => {
  const h = harness([queueItem(1), queueItem(2, 'FAILED')]);
  h.controller.start();
  await h.tick();
  assert.equal(h.controller.getSnapshot().status, 'ready');
  assert.equal(h.receivedEvents.length, 0);
  assert.equal(h.controller.getSnapshot().successfulPolls, 1);
  assert.equal(h.nextDelay(), MONITOR_POLL_INTERVAL_V4);
  await h.tick();
  assert.equal(h.receivedEvents.length, 0);
  h.controller.stop();
});

test('new REVIEW creates one event only; no duplicates on subsequent polls', async () => {
  const h = harness([queueItem(1)]);
  h.controller.start();
  await h.tick();
  h.updateQueue([queueItem(1), queueItem(3)]);
  await h.tick();
  assert.equal(h.receivedEvents.length, 1);
  assert.equal(h.receivedEvents[0].kind, 'REVIEW_REQUIRED');
  assert.equal(h.receivedEvents[0].inspectionId, queueItem(3).inspectionId);
  assert.equal(h.controller.getSnapshot().alerts.length, 1);
  await h.tick();
  assert.equal(h.receivedEvents.length, 1);
  assert.equal(h.controller.getSnapshot().alerts.length, 0);
  h.controller.stop();
});

test('new FAILED creates ANALYSIS_FAILED; same ID state change is a new alert', async () => {
  const h = harness([queueItem(1)]);
  h.controller.start();
  await h.tick();
  h.updateQueue([queueItem(1), queueItem(4, 'FAILED')]);
  await h.tick();
  assert.equal(h.receivedEvents.at(-1).kind, 'ANALYSIS_FAILED');
  assert.equal(h.receivedEvents.at(-1).inspectionNo, 'INS-000004');
  h.updateQueue([queueItem(1), queueItem(4, 'FAILED'), queueItem(5)]);
  await h.tick();
  assert.equal(h.receivedEvents.at(-1).kind, 'REVIEW_REQUIRED');
  h.controller.stop();
});

test('failed initial fetch does not mistake existing queue for fresh alerts after recovery', async () => {
  const h = harness([queueItem(1)]);
  h.failQueue(true);
  h.controller.start();
  await h.tick();
  assert.equal(h.controller.getSnapshot().status, 'error');
  h.failQueue(false);
  await h.tick();
  assert.equal(h.controller.getSnapshot().status, 'ready');
  assert.equal(h.receivedEvents.length, 0);
  h.updateQueue([queueItem(1), queueItem(2)]);
  await h.tick();
  assert.equal(h.receivedEvents.length, 1);
  h.controller.stop();
});

test('foreground pause cancels polls and resumed poll only notifies newly added IDs', async () => {
  const h = harness([queueItem(1)]);
  h.controller.start();
  await h.tick();
  h.controller.setForeground(false);
  assert.equal(h.timerCount(), 0);
  assert.equal(h.controller.getSnapshot().status, 'paused');
  h.updateQueue([queueItem(1), queueItem(2)]);
  assert.equal(h.receivedEvents.length, 0);
  h.controller.setForeground(true);
  assert.equal(h.nextDelay(), 0);
  await h.tick();
  assert.equal(h.receivedEvents.length, 1);
  assert.equal(h.receivedEvents[0].inspectionNo, 'INS-000002');
  h.controller.stop();
  assert.equal(h.timerCount(), 0);
});

test('one successful poll can notify more than one new item without a second request', async () => {
  const h = harness();
  h.controller.start();
  await h.tick();
  h.updateQueue([queueItem(1), queueItem(2, 'FAILED'), queueItem(3)]);
  await h.tick();
  assert.equal(h.receivedEvents.length, 3);
  assert.deepEqual(h.receivedEvents.map((e) => e.kind), [
    'REVIEW_REQUIRED', 'ANALYSIS_FAILED', 'REVIEW_REQUIRED',
  ]);
  h.controller.stop();
});
