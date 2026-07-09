/** @type {import('prettier').Config} */
export default {
  // 每行最大字符数，超出自动换行
  printWidth: 120,
  // 缩进空格数
  tabWidth: 2,
  // 语句末尾加分号
  semi: true,
  // 字符串使用单引号
  singleQuote: true,
  // 对象属性引号：仅在需要时添加（如含特殊字符）
  quoteProps: 'as-needed',
  // JSX 中使用单引号
  jsxSingleQuote: true,
  // 多行结构（对象、数组等）末尾添加逗号，便于 diff
  trailingComma: 'all',
  // 对象字面量大括号内侧保留空格，如 { foo: bar }
  bracketSpacing: true,
  // 多行 JSX/HTML 标签的 > 单独换行，不跟在最后一属性同一行
  bracketSameLine: false,
  // 箭头函数单参数也保留括号，如 (x) => x
  arrowParens: 'always',
  // Markdown 等散文本换行方式：保持原有换行
  proseWrap: 'preserve',
  // HTML 空白符敏感度：遵循 CSS display 默认值
  htmlWhitespaceSensitivity: 'css',
  // Vue 文件中 <script> 和 <style> 块不额外缩进
  vueIndentScriptAndStyle: false,
  // 换行符：自动适配当前系统（LF / CRLF）
  endOfLine: 'auto',
  // 格式化嵌入代码块（如 Markdown 中的代码块）
  embeddedLanguageFormatting: 'auto',
  // HTML/Vue 多个属性不强制每行一个
  singleAttributePerLine: false,
};
