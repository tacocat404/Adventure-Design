"""발표 리허설 뒤 시연 데이터 되돌리기 (11.05)

    cd backend
    .venv\\Scripts\\python demo_reset.py

- cushion.db를 cushion.db.bak-날짜시각 으로 먼저 백업한다
- parent1(박지영)이 보낸 메시지 중 지난 대화 4건이 아닌 것(리허설에서 보낸 것)을 지운다
- 장면 데이터(쿠션 요약 · 긴급 · 돌려보낸 위협 사건 등)를 지금 시각 기준으로 다시 넣는다
- 다른 계정 · 톡방 · 알림장 · 설문 · 상담 데이터는 건드리지 않는다
서버를 끈 뒤 돌리는 게 안전하다.
"""
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
db = Path(os.environ.get("CUSHION_DB", HERE / "cushion.db"))
if db.exists():
    bak = db.with_name(f"{db.name}.bak-{datetime.now():%m%d-%H%M%S}")
    shutil.copy2(db, bak)
    print("백업:", bak.name)

from app.api import demo_data  # noqa: E402  (불러오면 처음 한 번 채우기는 알아서 돈다)

demo_data.seed_present(force=True)
print("시연 데이터를 지금 시각 기준으로 다시 넣었어요.")
