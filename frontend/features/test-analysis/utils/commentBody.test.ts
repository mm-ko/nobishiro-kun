import { describe, expect, test } from "vitest";

import {
  isActionSentence,
  splitCommentBody,
  splitFormula,
} from "./commentBody";

// モック（Issue #134 の②-2）と同じ本文
const MOCK_BODY =
  "テストの確認、お疲れさまです。今回は、わり算のあまりを求める問題で、答えの数字に違いが見られました。17÷5の問題では、商の3は合っていて、あまりが3と書かれていました。この答案だけでは、違いが出た理由は分かりません。一度の結果だけで判断せず、一緒に確かめていけば大丈夫です。確かめるときは、「割る数×商＋あまり」が元の数と同じになるかを見てみましょう。5×3+3=18となり、17とは合いません。17−5×3=2として、あまりを一緒に確かめてみてください。あまりは割る数より小さいことも、あわせて確認できます。焦らず、一問ずつ親子で見直していきましょう。";

function joinParts(body: string): string {
  const { greeting, sentences } = splitCommentBody(body);
  return (greeting ?? "") + sentences.join("");
}

describe("splitCommentBody", () => {
  test("最初の「。」までを労いの1文、残りを「。」ごとの1文に分ける", () => {
    const { greeting, sentences } = splitCommentBody(MOCK_BODY);

    expect(greeting).toBe("テストの確認、お疲れさまです。");
    expect(sentences).toHaveLength(9);
    expect(sentences[0]).toBe(
      "今回は、わり算のあまりを求める問題で、答えの数字に違いが見られました。",
    );
    expect(sentences[8]).toBe("焦らず、一問ずつ親子で見直していきましょう。");
  });

  test("労いが2文のときは、2文目を残りの文に入れる", () => {
    const { greeting, sentences } = splitCommentBody(
      "テストの確認、お疲れさまです。毎日よくがんばっていますね。今回は商を求めるところまでできています。",
    );

    expect(greeting).toBe("テストの確認、お疲れさまです。");
    expect(sentences).toEqual([
      "毎日よくがんばっていますね。",
      "今回は商を求めるところまでできています。",
    ]);
  });

  test("カギカッコの中の「。」では区切らない", () => {
    const { sentences } = splitCommentBody(
      "お疲れさまです。確かめるときは、「割る数×商＋あまり。」を見てみましょう。『よし。』と声をかけてください。",
    );

    expect(sentences).toEqual([
      "確かめるときは、「割る数×商＋あまり。」を見てみましょう。",
      "『よし。』と声をかけてください。",
    ]);
  });

  test("「。」がないときは労いを切り出さず、全文を残りの文にする", () => {
    const body =
      "テストの確認お疲れさまです今回は商を求めるところまでできています";

    expect(splitCommentBody(body)).toEqual({
      greeting: null,
      sentences: [body],
    });
  });

  test("最後の「。」のあとに文字が残ったときは、最後の1文にする", () => {
    const { sentences } = splitCommentBody(
      "お疲れさまです。一緒に確かめましょう。がんばろう！",
    );

    expect(sentences).toEqual(["一緒に確かめましょう。", "がんばろう！"]);
  });

  test.each([
    ["労いが1文", MOCK_BODY],
    [
      "労いが2文",
      "テストの確認、お疲れさまです。毎日よくがんばっていますね。今回は商を求めるところまでできています。",
    ],
    [
      "カギカッコの中に「。」",
      "お疲れさまです。「あまり。」を見てみましょう。",
    ],
    [
      "閉じていないカギカッコ",
      "お疲れさまです。「あまりを見てみましょう。続けましょう。",
    ],
    ["「。」がない", "テストの確認お疲れさまです"],
    ["空白や改行を含む", "お疲れさまです。\n今回は できています。 "],
  ])("分けた文をつなげると元の本文と同じになる（%s）", (_, body) => {
    expect(joinParts(body)).toBe(body);
  });
});

describe("isActionSentence", () => {
  test.each([
    ["見直していきましょう。", true],
    ["あまりを一緒に確かめてみてください。", true],
    ["違いが出た理由は分かりません。", false],
    ["一緒に確かめましょう", false],
  ])("「%s」は %s", (sentence, expected) => {
    expect(isActionSentence(sentence)).toBe(expected);
  });
});

describe("splitFormula", () => {
  test("式とそれ以外に分ける", () => {
    expect(splitFormula("5×3+3=18となり、17とは合いません。")).toEqual([
      { text: "5×3+3=18", isFormula: true },
      { text: "となり、17とは合いません。", isFormula: false },
    ]);
    expect(
      splitFormula("17−5×3=2として、あまりを一緒に確かめてみてください。"),
    ).toEqual([
      { text: "17−5×3=2", isFormula: true },
      {
        text: "として、あまりを一緒に確かめてみてください。",
        isFormula: false,
      },
    ]);
  });

  test("文の途中や、1つの文に2つある式も見つける", () => {
    expect(splitFormula("まず17÷5=3、次に5×3=15です。")).toEqual([
      { text: "まず", isFormula: false },
      { text: "17÷5=3", isFormula: true },
      { text: "、次に", isFormula: false },
      { text: "5×3=15", isFormula: true },
      { text: "です。", isFormula: false },
    ]);
  });

  test("＝の右側のあとの「あまり＋数」も式に含める", () => {
    expect(splitFormula("17÷5=3あまり2です。")).toEqual([
      { text: "17÷5=3あまり2", isFormula: true },
      { text: "です。", isFormula: false },
    ]);
    expect(splitFormula("17÷5=3 あまり 2 になります。")).toEqual([
      { text: "17÷5=3 あまり 2", isFormula: true },
      { text: " になります。", isFormula: false },
    ]);
  });

  test("「あまり」のすぐ後ろが数でないときは、式に含めない", () => {
    expect(splitFormula("17÷5=3あまりは2です。")).toEqual([
      { text: "17÷5=3", isFormula: true },
      { text: "あまりは2です。", isFormula: false },
    ]);
  });

  test("式がないときは、文全体を1つのまま返す", () => {
    const sentence = "17÷5の問題では、商の3は合っていました。";

    expect(splitFormula(sentence)).toEqual([
      { text: sentence, isFormula: false },
    ]);
  });
});
