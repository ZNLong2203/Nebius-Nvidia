/**
 * A small syntax highlighter.
 *
 * Deliberately not a dependency: a full grammar engine is hundreds of kilobytes
 * for something that only ever renders short patches. This covers Python well
 * (what the demo patches) and degrades to something reasonable for anything
 * C-like, which is the honest trade.
 */

export type TokenKind =
  | "plain"
  | "comment"
  | "string"
  | "keyword"
  | "builtin"
  | "number"
  | "func"
  | "decorator";

export interface Token {
  kind: TokenKind;
  text: string;
}

const KEYWORDS = new Set([
  // python
  "def", "class", "return", "if", "elif", "else", "for", "while", "in", "not",
  "and", "or", "import", "from", "as", "with", "try", "except", "finally",
  "raise", "lambda", "None", "True", "False", "self", "cls", "yield", "assert",
  "pass", "break", "continue", "global", "nonlocal", "async", "await", "del",
  "is", "match", "case",
  // js/ts, so a non-python patch is not rendered as flat text
  "const", "let", "var", "function", "new", "typeof", "instanceof", "export",
  "default", "interface", "type", "extends", "implements", "public", "private",
  "readonly", "null", "undefined", "this", "switch", "throw", "void",
]);

const BUILTINS = new Set([
  "print", "len", "range", "str", "int", "float", "bool", "list", "dict", "set",
  "tuple", "sum", "min", "max", "abs", "round", "sorted", "enumerate", "zip",
  "isinstance", "type", "super", "open", "map", "filter", "any", "all",
  "Decimal", "ROUND_HALF_UP", "Exception", "ValueError", "TypeError",
  "console", "Math", "JSON", "Object", "Array", "Promise",
]);

const TRIPLE = /^\s*("""|''')/;

/**
 * Tokenise one line. `inBlockString` carries the open triple-quote across
 * lines, because a docstring in a diff hunk routinely spans several.
 */
export function tokenizeLine(
  line: string,
  inBlockString: string | null,
): { tokens: Token[]; inBlockString: string | null } {
  const tokens: Token[] = [];
  let open = inBlockString;
  let i = 0;

  const push = (kind: TokenKind, text: string) => {
    if (!text) return;
    const last = tokens[tokens.length - 1];
    if (last && last.kind === kind) last.text += text;
    else tokens.push({ kind, text });
  };

  // Still inside a docstring: the whole line is string until the closer.
  if (open) {
    const close = line.indexOf(open);
    if (close === -1) return { tokens: [{ kind: "string", text: line }], inBlockString: open };
    push("string", line.slice(0, close + open.length));
    i = close + open.length;
    open = null;
  }

  while (i < line.length) {
    const rest = line.slice(i);

    const triple = rest.match(/^("""|''')/);
    if (triple) {
      const marker = triple[1];
      const close = rest.indexOf(marker, marker.length);
      if (close === -1) {
        push("string", rest);
        return { tokens, inBlockString: marker };
      }
      push("string", rest.slice(0, close + marker.length));
      i += close + marker.length;
      continue;
    }

    const comment = rest.match(/^(#|\/\/).*/);
    if (comment) {
      push("comment", comment[0]);
      break;
    }

    const string = rest.match(/^(?:[frbu]{0,2})("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)/);
    if (string) {
      push("string", string[0]);
      i += string[0].length;
      continue;
    }

    const decorator = rest.match(/^@[\w.]+/);
    if (decorator) {
      push("decorator", decorator[0]);
      i += decorator[0].length;
      continue;
    }

    const number = rest.match(/^\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b/);
    if (number) {
      push("number", number[0]);
      i += number[0].length;
      continue;
    }

    const word = rest.match(/^[A-Za-z_]\w*/);
    if (word) {
      const value = word[0];
      const callsNext = /^\s*\(/.test(rest.slice(value.length));
      push(
        KEYWORDS.has(value)
          ? "keyword"
          : BUILTINS.has(value)
            ? "builtin"
            : callsNext
              ? "func"
              : "plain",
        value,
      );
      i += value.length;
      continue;
    }

    push("plain", line[i]);
    i += 1;
  }

  return { tokens, inBlockString: open };
}

/** Tokenise a block, carrying docstring state between lines. */
export function tokenizeBlock(source: string): Token[][] {
  let open: string | null = null;
  return source.split("\n").map((line) => {
    const result = tokenizeLine(line, open);
    open = result.inBlockString;
    return result.tokens;
  });
}

/** True when the line opens an unterminated triple-quoted string. */
export function opensDocstring(line: string): boolean {
  return TRIPLE.test(line);
}
