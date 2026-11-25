const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');

Module._extensions['.ts'] = (module, filename) => {
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename,
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  });
  module._compile(outputText, filename);
};

const { requiresLiveSession, observeNavigationSession, resetLiveStackToLogin } =
  require('../src/components/sessionNavigationV4.ts');
const worker = { signedIn: true, role: 'WORKER', loginId: 'worker' };
const signedOut = { signedIn: false, role: null, loginId: null };

test('all dedicated live routes and live shared screens are guarded, mock and login remain available', () => {
  for (const file of fs.readdirSync(path.join(__dirname, '../src/app'))) {
    if (file.endsWith('-live.tsx')) assert.equal(requiresLiveSession(file.slice(0, -4)), true, file);
  }
  for (const name of ['monitoring', 'history', 'settings']) {
    assert.equal(requiresLiveSession(name, { mode: 'live' }), true);
    assert.equal(requiresLiveSession(name, { mode: 'mock' }), false);
    assert.equal(requiresLiveSession(name), false);
  }
  assert.equal(requiresLiveSession('index'), false);
});

function sessionHarness() {
  const reads = [];
  const seen = [];
  let notify;
  const stop = observeNavigationSession({
    restore: () => new Promise((resolve, reject) => reads.push({ resolve, reject })),
    subscribeSessionChange: (listener) => {
      notify = listener;
      return () => { notify = undefined; };
    },
  }, (value) => seen.push(value));
  return { reads, seen, stop, change: () => notify() };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

test('a stale vault read cannot restore protected content after logout', async () => {
  const h = sessionHarness();
  h.change();
  h.reads[1].resolve(signedOut);
  await flush();
  assert.equal(h.seen.at(-1), null);
  h.reads[0].resolve(worker);
  await flush();
  assert.equal(h.seen.at(-1), null);
  h.stop();
});

test('membership changes hide existing protected content until the new account is verified', async () => {
  const h = sessionHarness();
  h.reads[0].resolve(worker);
  await flush();
  assert.deepEqual(h.seen.at(-1), worker);
  h.change();
  assert.equal(h.seen.at(-1), undefined);
  h.reads[1].resolve({ ...worker, role: 'DEVICE' });
  await flush();
  assert.equal(h.seen.at(-1), null);
  h.change();
  h.reads[2].reject(new Error('storage unavailable'));
  await flush();
  assert.equal(h.seen.at(-1), null);
  h.change();
  h.stop();
  const states = h.seen.length;
  h.reads[3].resolve(worker);
  await flush();
  assert.equal(h.seen.length, states);
});

test('the installed Expo screen dispatches a concrete reset and native Back cannot reopen old routes', () => {
  const { StackRouter } = require('expo-router/build/react-navigation/routers/StackRouter');
  const { goBack } = require('expo-router/build/react-navigation/routers/CommonActions');
  const { RouterActionHandling } = require('expo-router/build/react-navigation/routers/types');
  const stack = StackRouter({});
  const state = {
    key: 'root', index: 2, type: 'stack', stale: false, routeKeySeq: 3,
    routeNames: ['index', 'monitoring', 'history', 'settings'],
    routes: [
      { key: 'monitoring:0', name: 'monitoring', params: { mode: 'live' } },
      { key: 'history:1', name: 'history', params: { mode: 'live' } },
      { key: 'settings:2', name: 'settings', params: { mode: 'live' } },
    ],
  };
  const config = { routeParamList: {}, routeGetIdList: {} };
  // Use the real screen-scoped bridge as well as the reducer. In SDK 58 the
  // bridge spreads its argument and adds a source, so dispatching a factory loses its type.
  const React = require('react');
  const { renderToStaticMarkup } = require('react-dom/server');
  const { useNavigationCache } = require('expo-router/build/react-navigation/core/useNavigationCache');
  let screenNavigation;
  let dispatched;
  function CaptureNavigation() {
    const forRoute = useNavigationCache({
      routes: state.routes,
      routeNames: state.routeNames,
      router: stack,
      navigation: { getState: () => state, dispatch: (action) => { dispatched = action; } },
      emitter: { create: () => ({}) },
    });
    screenNavigation = forRoute(state.routes[state.index], false);
    return null;
  }
  renderToStaticMarkup(React.createElement(CaptureNavigation));
  resetLiveStackToLogin(screenNavigation);
  assert.equal(dispatched.source, 'settings:2');
  assert.equal(dispatched.type, 'RESET');
  const { state: reset } = stack.getStateForAction(state, dispatched, config);
  assert.deepEqual(reset.routes.map(({ name }) => name), ['index']);
  assert.equal(stack.getStateForAction(reset, goBack(), config), RouterActionHandling.Unhandled);
});

// Render the Settings function with controllable focus, hooks, alerts and auth.
// Native confirmation callbacks can outlive both their screen and account.
function settingsFixture() {
  const slots = [];
  const alerts = [];
  let cursor = 0, epoch = 1, focusEffect, blur, completion;
  function slot(initial) {
    const index = cursor++;
    return slots[index] ??= { current: initial };
  }
  const authV4 = {
    restore: async () => worker,
    sessionEpoch: () => epoch,
    logout() {
      epoch++;
      return new Promise((resolve, reject) => { completion = { resolve, reject }; });
    },
  };
  const mocks = {
    react: {
      useRef: slot, useCallback: (callback) => callback,
      useState(initial) {
        const state = slot(initial);
        return [state.current, (value) => { state.current = value; }];
      },
    },
    'expo-router': {
      Stack: { Screen: 'Screen' }, useFocusEffect: (effect) => { focusEffect = effect; },
      useLocalSearchParams: () => ({ mode: 'live' }),
    },
    'react-native': {
      Alert: { alert: (...args) => alerts.push(args) }, StyleSheet: { create: (styles) => styles },
      ActivityIndicator: 'ActivityIndicator', View: 'View', Text: 'Text', ScrollView: 'ScrollView',
    },
    'react-native-safe-area-context': { SafeAreaView: 'SafeAreaView' },
    '../api/backendV4/authRuntime': { authV4 },
    '../components/TouchPressable': 'Pressable',
    '../components/LiveBottomNavV4': 'LiveBottomNavV4',
  };
  const filename = path.join(__dirname, '../src/app/settings.tsx');
  const screen = new Module(filename, module);
  screen.require = (id) => mocks[id] ?? require(id);
  const { outputText } = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    fileName: filename, compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  });
  screen._compile(outputText, filename);
  function render() { cursor = 0; return screen.exports.default(); }
  function logoutButton(node) {
    if (Array.isArray(node)) return node.map(logoutButton).find(Boolean);
    if (!node?.props) return;
    if (node.type === 'Pressable' && node.props.children?.props?.children === '로그아웃') return node;
    return logoutButton(node.props.children);
  }
  return {
    async focus() { render(); blur = focusEffect(); await flush(); },
    blur: () => blur(),
    confirm() {
      logoutButton(render()).props.onPress();
      return alerts.pop()[2].find((button) => button.style === 'destructive').onPress;
    },
    changeAccount: () => { epoch++; },
    get completion() { return completion; },
    alerts,
  };
}

test('a pending native logout confirmation loses authority on blur, refocus, or account change', async () => {
  const settings = settingsFixture();
  await settings.focus();
  const previousFocus = settings.confirm();
  settings.blur();
  previousFocus();
  assert.equal(settings.completion, undefined);
  await settings.focus();
  previousFocus();
  assert.equal(settings.completion, undefined);
  const previousAccount = settings.confirm();
  settings.changeAccount();
  previousAccount();
  assert.equal(settings.completion, undefined);
});

test('logout completion can notify after blur, but neither offline nor storage errors notify a newer account', async () => {
  for (const newerAccount of [false, true]) {
    for (const storageError of [false, true]) {
      const settings = settingsFixture();
      await settings.focus();
      settings.confirm()();
      settings.blur();
      if (newerAccount) settings.changeAccount();
      if (storageError) settings.completion.reject(new Error('vault unavailable'));
      else settings.completion.resolve({ remoteRevoked: false });
      await flush();
      assert.deepEqual(settings.alerts.map(([title]) => title), newerAccount ? [] :
        [storageError ? '로그아웃을 완료하지 못했습니다' : '이 기기에서 로그아웃됨']);
    }
  }
});
