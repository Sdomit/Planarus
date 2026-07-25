import parser from '@babel/eslint-parser'
import reactHooks from 'eslint-plugin-react-hooks'

// #101: the web half of the lint gate.
//
// Scope — deliberately narrow. `tsc -b --noEmit` already runs in CI with strict
// + noUnusedLocals + noUnusedParameters, so a general TS/JS rule set would mostly
// re-report what typecheck already gates. What tsc cannot see is hook
// correctness, so that is all this job adds. The rest of
// eslint-plugin-react-hooks v7's `recommended-latest` (the React Compiler rules:
// purity, immutability, set-state-in-effect, static-components) is a separate
// opt-in cleanup, not a gate to switch on under an existing codebase in one go.
//
// Parser — Babel, not @typescript-eslint/parser, because this repo is on
// TypeScript 7.0 and typescript-eslint 8.x refuses to load against it
// ("typescript-eslint does not support TS 7.0"); see
// https://github.com/typescript-eslint/typescript-eslint/issues/10940. Babel
// only parses here — no type information is used, and these two rules need
// none — so the TS version is irrelevant to it. Switch back to
// typescript-eslint once it supports TS >= 7.1.
export default [
  { ignores: ['dist/**', 'coverage/**', '*.tsbuildinfo'] },
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      parser,
      parserOptions: {
        requireConfigFile: false,
        // Parsing only — no transform. preset-typescript strips the type
        // syntax and resolves the .ts/.tsx ambiguity by file extension;
        // syntax-jsx is what actually lets `<div/>` through (Babel 8 dropped
        // the old isTSX/allExtensions options that used to imply it).
        babelOptions: {
          presets: ['@babel/preset-typescript'],
          plugins: ['@babel/plugin-syntax-jsx'],
        },
      },
    },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'error',
    },
  },
]
