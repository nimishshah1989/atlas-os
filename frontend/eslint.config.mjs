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
  // CONVENTION (not lint-enforced): postgres-js returns NUMERIC columns as `string`.
  // Prefer toNumber(x) / toNumberOr(x, fallback) from @/lib/decimal over bare Number()
  // in the query layer — Number() silently returns NaN on bad input (invisible broken
  // charts), toNumber() throws. The old path-scoped lint rule was retired when the v6
  // dirs were flattened (it fired false positives on legit Number() in components).
]
