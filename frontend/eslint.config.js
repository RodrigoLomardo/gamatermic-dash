import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import reactHooks from "eslint-plugin-react-hooks";

export default [
  { ignores: ["dist", "src/shared/api/schema.d.ts"] },
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: { parser: tsParser, parserOptions: { ecmaFeatures: { jsx: true } } },
    plugins: { "@typescript-eslint": tsPlugin, "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "no-restricted-imports": ["error", { patterns: [{ group: ["@/features/*/*"], message: "Importe apenas via API pública da feature." }] }],
    },
  },
  // features nao importam outras features (exceto composicao em app/ e pages/); a regra acima cobre imports profundos
  { files: ["src/app/**", "src/features/**"], rules: { "no-restricted-imports": "off" } },
];
