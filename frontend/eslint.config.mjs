import tsParser from '@typescript-eslint/parser'

/** @type {import('eslint').Linter.Config[]} */
export default [
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
      },
    },
    rules: {
      'no-undef': 'off',
    },
  },
  // A.10 lint gate — Decimal transport safety
  // postgres-js returns NUMERIC columns as `string`. Using bare Number() on these
  // values silently returns NaN for invalid input, causing Recharts/D3 charts to
  // render at width 0 with no visible error. Use toNumber(x) or toNumberOr(x, fallback)
  // from @/lib/v6/decimal instead — they throw TypeError on invalid input.
  {
    files: [
      'src/components/v6/**/*.{ts,tsx}',
      'src/lib/queries/v6/**/*.{ts,tsx}',
    ],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector: "CallExpression[callee.name='Number']",
          message:
            "Do not use Number() to convert Postgres NUMERIC strings in v6 paths — use toNumber(x) or toNumberOr(x, fallback) from @/lib/v6/decimal instead. Number() silently returns NaN on invalid input; toNumber() throws TypeError so chart failures are visible.",
        },
      ],
    },
  },
]
