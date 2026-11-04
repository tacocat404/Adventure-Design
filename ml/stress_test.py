"""실패 상황 시뮬레이션 — 판단기를 일부러 곤란하게 만들어 보고 결과를 ml/stress_results.md에 쓴다.

실행 (레포 루트): backend/.venv/Scripts/python ml/stress_test.py
API 없이(use_api=False) 로컬 판단만 본다. 평가셋과 겹치지 않는 새 문장들.
"""
import json
import shutil
import statistics
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.ai import analyzer as ai  # noqa: E402

# (묶음, 문장, 기대 분류, 가려야 하나 — None이면 안 봄)
CASES = [
    ("변형 욕설", "ㅅ ㅂ 진짜 일 이렇게 할래요?", "normal", True),
    ("변형 욕설", "씨 발 장난하세요?", "normal", True),
    ("변형 욕설", "개.념.없.네 진짜", "normal", True),
    ("변형 욕설", "선생님 머리는 장식이에요?", "normal", True),
    ("함정(평범)", "수학 시험 문제 다 맞았대요! 감사해요.", "normal", False),
    ("함정(평범)", "급식에서 고소한 냄새가 난다고 좋아해요.", "normal", False),
    ("함정(평범)", "결석 신고서 양식은 어디서 받나요?", "normal", False),
    ("함정(평범)", "요즘 바빠 죽겠네요 ㅎㅎ 상담 시간 바꿔 주실 수 있을까요?", "normal", False),
    ("함정(평범)", "찾아가는 음악회 신청은 어떻게 해요?", "normal", False),
    ("함정(평범)", "아이가 2학기엔 각오를 다지고 열심히 하겠대요.", "normal", False),
    ("함정(평범)", "어제 애가 계단에서 넘어질 뻔했는데 괜찮대요.", "normal", False),
    ("돌려 말한 위협", "선생님 차 번호 다 알고 있어요.", "threat", True),
    ("돌려 말한 위협", "내일 교문 앞에서 기다리고 있을게요.", "threat", None),
    ("돌려 말한 위협", "맘카페에 글 하나 올리면 어떻게 될지 아시죠?", "threat", True),
    ("돌려 말한 위협", "계속 이러시면 교장실로 바로 가겠습니다.", "threat", None),
    ("돌려 말한 위협", "선생님 가족분들도 이 일 아시나요?", "threat", None),
    ("긴급 변형", "화장실에서 누가 밀어서 머리를 부딪혔대요.", "urgent", False),
    ("긴급 변형", "옆집 아이가 며칠째 밥을 못 먹고 다니는 것 같아요.", "urgent", False),
    ("긴급 변형", "아이 팔에 시퍼런 멍이 여러 개 있어요.", "urgent", False),
    ("긴급 변형", "애가 그냥 다 끝내고 싶다고 했어요. 무서워요.", "urgent", False),
    ("긴급 변형", "단톡방에서 애들이 우리 애 사진으로 놀린대요.", "urgent", False),
    ("섞임", "선생님 대체 뭐 하세요? 우리 애가 맞고 왔다고요!", "urgent", False),
    ("섞임", "한심하네요 정말. 내일까지 자리 바꿔 주세요.", "normal", True),
]

EDGE = ["", "   ", "😡😡😡", "ok", "<script>alert(1)</script> 선생님", "가" * 3000,
        "선생님 우리 민서가 짝이랑 안 맞아서 매일 울면서 와요 " * 30, "Teacher you are useless"]


def run_cases():
    rows, ok = [], 0
    for grp, text, cat, masked in CASES:
        r = ai.analyze(text, use_api=False)
        hit = r["category"] == cat and (masked is None or bool(r["masked_spans"]) == masked)
        ok += hit
        rows.append(f"| {grp} | {text} | {cat}{'' if masked is None else (' · 가림' if masked else ' · 안 가림')} | "
                    f"{r['category']}{' · 가림' if r['masked_spans'] else ''} | {'✅' if hit else '❌'} |")
    return ok, rows


def run_edges():
    out = []
    for t in EDGE:
        try:
            s = time.perf_counter(); r = ai.analyze(t, use_api=False); ms = (time.perf_counter() - s) * 1000
            p = ai.precheck(t)
            out.append(f"| `{(t[:24] + '…') if len(t) > 24 else t or '(빈 글)'}` ({len(t)}자) | {r['category']} · 가림 {len(r['masked_spans'])} · {ms:.0f}ms | ✅ 멈추지 않음 |")
        except Exception as e:  # noqa: BLE001
            out.append(f"| `{t[:24]}` ({len(t)}자) | {type(e).__name__}: {e} | ❌ |")
    return out


def run_fallback():
    out = []
    saved_dir, saved = ai.JUDGE_DIR, ai._judge_model
    tmp = Path(tempfile.mkdtemp())
    try:
        for name, prep in (("모델 폴더 없음", lambda d: None),
                           ("stack.json 깨짐", lambda d: (shutil.copytree(saved_dir, d, dirs_exist_ok=True), (d / "stack.json").write_text("{깨짐"))),
                           ("bank.npz 없음", lambda d: (shutil.copytree(saved_dir, d, dirs_exist_ok=True), (d / "bank.npz").unlink()))):
            d = tmp / name.replace(" ", "_")
            if saved_dir.exists():
                prep(d)
            ai.JUDGE_DIR, ai._judge_model = d, None
            try:
                r = ai.analyze("내일 학교로 찾아갈 테니 각오하세요.", use_api=False)
                out.append(f"| {name} | {ai.judge_name()} 로 돎 · {r['category']} | {'✅' if r['category'] == 'threat' else '❌'} |")
            except Exception as e:  # noqa: BLE001
                out.append(f"| {name} | {type(e).__name__}: {e} | ❌ |")
    finally:
        ai.JUDGE_DIR, ai._judge_model = saved_dir, saved
        shutil.rmtree(tmp, ignore_errors=True)
    saved_env = dict(ai.ENV)
    ai.ENV["CNU_BASE_URL"] = "http://127.0.0.1:9"  # 닫힌 포트 = API 끊김
    try:
        s = time.perf_counter(); r = ai.analyze("이번 일 넘어가면 가만 안 둘 거예요.", use_api=True); sec = time.perf_counter() - s
        p = ai.precheck("한심하네요. 자리 바꿔 주세요.")
        out.append(f"| API 끊김 | {r['category']} · 요약 “{r['summary'][:20]}” · {sec:.1f}초 · 제안 {len(p['suggestions'])}개 | "
                   f"{'✅' if r['category'] == 'threat' and p['suggestions'] else '❌'} |")
    finally:
        ai.ENV.clear(); ai.ENV.update(saved_env)
    # API가 응답을 1초에 한 글자씩 흘려보낼 때 (읽기 timeout은 매번 다시 재서 안 걸린다)
    import http.server
    import threading

    class Slow(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200); self.send_header("Content-Length", "1000"); self.end_headers()
            try:
                for _ in range(60):
                    self.wfile.write(b" "); self.wfile.flush(); time.sleep(1)
            except OSError:
                pass

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    ai.ENV["CNU_BASE_URL"] = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        s = time.perf_counter(); r = ai.analyze("이번 일 넘어가면 가만 안 둘 거예요.", use_api=True); sec = time.perf_counter() - s
        out.append(f"| API가 아주 느리게 흘려보냄 | {r['category']} · {sec:.1f}초 | {'✅' if r['category'] == 'threat' and sec < 15 else '❌'} |")
    finally:
        srv.shutdown(); ai.ENV.clear(); ai.ENV.update(saved_env)
    return out


def run_speed():
    texts = [c[1] for c in CASES]
    ai.analyze("워밍업", use_api=False)
    lat = []
    for t in texts * 3:
        s = time.perf_counter(); ai.analyze(t, use_api=False); lat.append((time.perf_counter() - s) * 1000)
    lat.sort()
    s = time.perf_counter()
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda t: ai.analyze(t, use_api=False)["category"], texts * 2))
    par = time.perf_counter() - s
    same = res[:len(texts)] == [ai.analyze(t, use_api=False)["category"] for t in texts]
    return [f"- 메시지 한 통 로컬 판단: 중앙값 {statistics.median(lat):.0f}ms · 95% {lat[int(len(lat) * .95)]:.0f}ms · 최대 {lat[-1]:.0f}ms ({len(lat)}건, CPU)",
            f"- 8개 동시 요청 {len(texts) * 2}건: {par:.1f}초 · 결과가 혼자 돌릴 때와 {'같음 ✅' if same else '다름 ❌'}"]


def main():
    ai.load_judge()
    ok, rows = run_cases()
    out = ["# 실패 상황 시뮬레이션", "", f"판단기: `{ai.judge_name()}` · API 없이 로컬 판단만", "",
           f"## 1. 어려운 문장 ({ok}/{len(CASES)} 맞힘)", "", "| 묶음 | 문장 | 기대 | 결과 | |", "|---|---|---|---|---|", *rows,
           "", "## 2. 이상한 입력", "", "| 입력 | 결과 | |", "|---|---|---|", *run_edges(),
           "", "## 3. 부품이 고장 났을 때", "", "| 상황 | 결과 | |", "|---|---|---|", *run_fallback(),
           "", "## 4. 속도 · 동시 요청", "", *run_speed(), ""]
    (ROOT / "ml" / "stress_results.md").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
