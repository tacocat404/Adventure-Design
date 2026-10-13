# CLAUDE.md

## 상황별 스킬 (`.claude/skills/`)

| 상황 | 스킬 |
|---|---|
| 디자인할 때 | `supanova-design-engine`(새 페이지) · `supanova-premium-aesthetic`(고급 마감) · `supanova-redesign-engine`(기존 페이지 개선) · `supanova-full-output`(생략 없는 전체 출력) |
| 개발할 때 | `ponytail`(최소 변경) · `ponytail-review`(변경 리뷰) · `ponytail-audit`(전체 점검) · `ponytail-debt`(`shortcut:` 목록) |
| 글을 쓸 때 (AI 티 제거) | `humanize-scan`(먼저 점검) → `humanize-korean` / `/humanize`(윤문) · `/humanize-redo`(2차 윤문) |
| 하는 일을 설명하거나 사용자가 이해를 위해 물을 때 | `eli5` |
| 기획 단계에서 PRD를 구체화할 때 | `idea2planning`(1-pager → PRD → 와이어프레임) |
| 항상 | 아래 Karpathy 지침 (`karpathy-guidelines` 스킬과 같은 내용) |

### Windows 실행 메모
- 이 PC에는 `python3`가 없다. humanize 스크립트는 `py`로 실행한다: `py .claude/skills/humanize-korean/scripts/<script>.py ...`
- 한글 출력이 깨지지 않게 `PYTHONIOENCODING=utf-8`을 설정하고 실행한다.

---

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
