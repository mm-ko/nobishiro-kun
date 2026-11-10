// AIコメントの本文（comment_body）を、表示用に区切る処理（UI-007・Issue #134）
// 文字は削ったり変えたりせず、区切るだけにする（つなげると元の本文に戻る）

export type CommentBodyParts = {
  greeting: string | null;
  sentences: string[];
};

export type SentencePart = {
  text: string;
  isFormula: boolean;
};

const OPEN_BRACKETS = ["「", "『"];
const CLOSE_BRACKETS = ["」", "』"];
const ACTION_ENDINGS = ["ましょう。", "ください。"];

// 「5×3+3=18」「17−5×3=2」のような、＝を含む式
// 「17÷5=3あまり2」のように、＝の右側のあとに「あまり＋数」があれば、それも式に含める
const NUMBER = "[0-9０-９]+(?:[.．][0-9０-９]+)?";
const OPERATOR = "[+＋\\-−－×÷]";
const EXPRESSION = `${NUMBER}(?:\\s*${OPERATOR}\\s*${NUMBER})*`;
const FORMULA_PATTERN = new RegExp(
  `${EXPRESSION}\\s*[=＝]\\s*${EXPRESSION}(?:\\s*あまり\\s*${NUMBER})?`,
  "g",
);

// 「。」ごとに1文に分ける。カギカッコの中の「。」では区切らない
function splitSentences(body: string): string[] {
  const sentences: string[] = [];
  let current = "";
  let bracketDepth = 0;

  for (const char of body) {
    current += char;

    if (OPEN_BRACKETS.includes(char)) {
      bracketDepth += 1;
    } else if (CLOSE_BRACKETS.includes(char) && bracketDepth > 0) {
      bracketDepth -= 1;
    } else if (char === "。" && bracketDepth === 0) {
      sentences.push(current);
      current = "";
    }
  }

  if (current !== "") {
    sentences.push(current);
  }

  return sentences;
}

// 最初の1文を労いとして切り出す。「。」がないときは、労いを切り出さない
export function splitCommentBody(body: string): CommentBodyParts {
  const sentences = splitSentences(body);

  if (sentences.length === 0 || !sentences[0].endsWith("。")) {
    return { greeting: null, sentences };
  }

  return { greeting: sentences[0], sentences: sentences.slice(1) };
}

// 「〜ましょう。」「〜ください。」で終わる文か
export function isActionSentence(sentence: string): boolean {
  const trimmed = sentence.trimEnd();
  return ACTION_ENDINGS.some((ending) => trimmed.endsWith(ending));
}

// 文を「式」と「それ以外」に分ける
export function splitFormula(sentence: string): SentencePart[] {
  const parts: SentencePart[] = [];
  let lastIndex = 0;

  for (const match of sentence.matchAll(FORMULA_PATTERN)) {
    if (match.index > lastIndex) {
      parts.push({
        text: sentence.slice(lastIndex, match.index),
        isFormula: false,
      });
    }
    parts.push({ text: match[0], isFormula: true });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < sentence.length) {
    parts.push({ text: sentence.slice(lastIndex), isFormula: false });
  }

  return parts;
}
