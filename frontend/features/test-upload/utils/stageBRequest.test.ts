import { describe, expect, test } from "vitest";

import type { StageAResponse } from "@/types/api";

import { buildStageBRequest } from "./stageBRequest";

const stageAResult: StageAResponse = {
  analysis_request_id: "analysis-1",
  status: "awaiting_confirmation",
  read_score: 8,
  read_unit_name: "わり算",
  expires_at: "2026-10-12T00:00:00Z",
  questions: [
    {
      question_id: "q1",
      image_index: 1,
      question_number: "1",
      problem_text: "12÷3",
      student_answer: null,
      calculation_process: null,
      grading: "unknown",
    },
    {
      question_id: "q2",
      image_index: 1,
      question_number: "2",
      problem_text: "17÷5",
      student_answer: "3あまり2",
      calculation_process: "17-15=2",
      grading: "incorrect",
    },
  ],
};

describe("buildStageBRequest", () => {
  test("空欄回答と確定した正誤だけをStage Bリクエストへ含める", () => {
    const request = buildStageBRequest(stageAResult, 8, 10, {
      q1: {
        answerConfirmation: "differs",
        correctedAnswer: "",
        isBlankAnswer: true,
        gradingConfirmation: "differs",
        correctedGrading: "incorrect",
      },
      q2: {
        answerConfirmation: "matches",
        correctedAnswer: "",
        isBlankAnswer: false,
        gradingConfirmation: "matches",
        correctedGrading: null,
      },
    });

    expect(request).toEqual({
      score: 8,
      max_score: 10,
      read_unit_name: "わり算",
      confirmed_questions: [
        {
          question_id: "q1",
          image_index: 1,
          question_number: "1",
          problem_text: "12÷3",
          student_answer: "",
          calculation_process: null,
          grading: "incorrect",
        },
        {
          question_id: "q2",
          image_index: 1,
          question_number: "2",
          problem_text: "17÷5",
          student_answer: "3あまり2",
          calculation_process: "17-15=2",
          grading: "incorrect",
        },
      ],
    });
    expect("user_id" in request).toBe(false);
    expect("images" in request).toBe(false);
  });

  test("修正した解答の前後の空白を除いて送る", () => {
    const request = buildStageBRequest(stageAResult, 8, 10, {
      q1: {
        answerConfirmation: "differs",
        correctedAnswer: " 3あまり0 ",
        isBlankAnswer: false,
        gradingConfirmation: "differs",
        correctedGrading: "correct",
      },
      q2: {
        answerConfirmation: "matches",
        correctedAnswer: "",
        isBlankAnswer: false,
        gradingConfirmation: "matches",
        correctedGrading: null,
      },
    });

    expect(request.confirmed_questions[0].student_answer).toBe("3あまり0");
    expect(request.confirmed_questions[0].grading).toBe("correct");
  });
});
